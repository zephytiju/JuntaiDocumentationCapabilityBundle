"""Capability publication using a caller-owned Meridian ResourceStore.

No engine, credentials, transport, or runtime is constructed here. Meridian
references identify payload bytes; they are never represented as OCI manifests.
"""

from __future__ import annotations

import io
import json
import tarfile
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .canonical import canonical_json_bytes, deterministic_tar, digest_json, sha256_bytes
from .errors import CapabilityError

REFERENCE_SCHEMA = "capability.juntai.io/meridian-artifact-reference/v1"
ARCHIVE_MEDIA_TYPE = "application/vnd.juntai.capability-build.v1+tar"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
BUILD_FILES = frozenset(
    {
        "build-result.json",
        "content-graph.json",
        "human-projection.json",
        "mcp-projection.json",
        "capability-bundle.tar",
        "agent-capability-bundle.tar",
        "documentation-human.tar",
        "documentation-mcp.json",
        "provenance.json",
    }
)
PIN_FIELDS = (
    "producerBuildId",
    "openapiDigest",
    "mcpDescriptorDigest",
    "contentGraphDigest",
    "humanProjectionDigest",
    "mcpProjectionDigest",
)


def _types():
    try:
        from meridian_storage.plugins.config_artifact import ResourceIdentity, StoredResourceRef
    except ImportError as error:
        raise CapabilityError(
            "Meridian publication requires the meridian extra and Python 3.12+"
        ) from error
    return ResourceIdentity, StoredResourceRef


def exact_reference(coordinate: Mapping[str, Any]):
    """Validate the discriminator, public reference, profile, and exact digest."""
    _, reference_type = _types()
    try:
        if set(coordinate) != {
            "ownerKey",
            "bundleId",
            "version",
            "schemaMajor",
            "digest",
            "artifactRef",
        }:
            raise ValueError("unexpected coordinate fields")
        if coordinate["schemaMajor"] != 1:
            raise ValueError("unsupported coordinate schema")
        ref = coordinate["artifactRef"]
        if set(ref) != {"schemaVersion", "resource", "digest"}:
            raise ValueError("unexpected reference fields")
        if ref["schemaVersion"] != REFERENCE_SCHEMA:
            raise ValueError("unsupported reference schema")
        resource = ref["resource"]
        if set(resource) != {
            "resourceId",
            "namespace",
            "kind",
            "name",
            "version",
            "profile",
            "digest",
        }:
            raise ValueError("unexpected resource reference fields")
        parsed = reference_type(
            resource_id=resource["resourceId"],
            namespace=resource["namespace"],
            kind=resource["kind"],
            name=resource["name"],
            version=resource["version"],
            profile=resource["profile"],
            digest=resource["digest"],
        )
        if parsed.profile != "artifact" or parsed.version != coordinate["version"]:
            raise ValueError("reference profile or version mismatch")
        if parsed.digest != ref["digest"] or parsed.digest != coordinate["digest"]:
            raise ValueError("reference and coordinate digests differ")
        return parsed
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise CapabilityError(f"invalid exact Meridian reference: {error}") from error


def build_archive(output: str | Path) -> tuple[bytes, dict[str, Any]]:
    """Bind the complete directory consumed by Delivery into one immutable payload."""
    root = Path(output)
    files = {}
    total = 0
    try:
        for name in sorted(BUILD_FILES):
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise CapabilityError(f"build file must be a regular file: {name}")
            with path.open("rb") as stream:
                payload = stream.read(MAX_ARCHIVE_BYTES - total + 1)
            total += len(payload)
            if total > MAX_ARCHIVE_BYTES:
                raise CapabilityError("capability build exceeds archive limit")
            files[name] = payload
        build = json.loads(files["build-result.json"])
        core = {key: value for key, value in build.items() if key != "buildResultDigest"}
        if digest_json(core) != build["buildResultDigest"]:
            raise CapabilityError("build result digest mismatch")
        expected = BUILD_FILES - {
            "build-result.json",
            "content-graph.json",
            "human-projection.json",
            "mcp-projection.json",
        }
        if set(build["artifacts"]) != expected:
            raise CapabilityError("build artifact inventory mismatch")
        for name, artifact in build["artifacts"].items():
            if (
                sha256_bytes(files[name]) != artifact["digest"]
                or len(files[name]) != artifact["byteLength"]
            ):
                raise CapabilityError(f"built artifact changed before publication: {name}")
        archive = deterministic_tar(files)
        if len(archive) > MAX_ARCHIVE_BYTES:
            raise CapabilityError("capability build exceeds archive limit")
        return archive, build
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise CapabilityError(f"cannot read capability build: {error}") from error


def validate_directory(output: str | Path, pin: Mapping[str, Any]) -> None:
    reference = exact_reference(pin["coordinate"])
    archive, build = build_archive(output)
    if sha256_bytes(archive) != reference.digest:
        raise CapabilityError("directory differs from the exact Meridian payload")
    if any(pin[field] != build[field] for field in PIN_FIELDS) or any(
        pin["coordinate"][field] != build[field] for field in ("ownerKey", "bundleId", "version")
    ):
        raise CapabilityError("pin differs from the published build lineage")


def _read_exact(store: Any, coordinate: Mapping[str, Any], media_type: str) -> bytes:
    reference = exact_reference(coordinate)
    resolved = store.artifacts.exact(reference.identity)
    resource = resolved.resource
    if (
        resource.ref != reference
        or resource.state != "PUBLISHED"
        or resource.media_type != media_type
        or not 0 < resource.byte_length <= MAX_ARCHIVE_BYTES
    ):
        raise CapabilityError("Meridian exact read returned different or unpublished metadata")
    payload = store.artifacts.read(resolved)
    if len(payload) != resource.byte_length or sha256_bytes(payload) != reference.digest:
        raise CapabilityError("Meridian exact read payload digest or length mismatch")
    return payload


def publish_bundle_meridian(
    output: str | Path,
    *,
    resource_store: Any,
    actor: str,
    result_path: str | Path | None = None,
) -> dict[str, Any]:
    """Publish all four parts and read each exact reference before returning a pin.

    Partial failure returns no result. Existing immutable parts may be reused by
    retrying identical input through ResourceStore's publication contract.
    """
    identity_type, _ = _types()
    archive, build = build_archive(output)
    publication = build["publication"]
    name = publication["name"]
    # Take all parts from the same validated snapshot, even if the producer
    # directory changes while the storage calls are in progress.
    parts = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as snapshot:
        for filename in build["artifacts"]:
            stream = snapshot.extractfile(filename)
            if stream is None:
                raise CapabilityError("missing validated publication part")
            with stream:
                parts[filename] = stream.read()
    definitions = {
        "bundle": (name, archive, ARCHIVE_MEDIA_TYPE),
        **{
            part: (
                f"{name}-{suffix}",
                parts[filename],
                build["artifacts"][filename]["mediaType"],
            )
            for part, suffix, filename in (
                ("humanProjection", "human", "documentation-human.tar"),
                ("mcpProjection", "mcp", "documentation-mcp.json"),
                ("provenance", "provenance", "provenance.json"),
            )
        },
    }
    coordinates = {}
    for part, (part_name, payload, media_type) in definitions.items():
        identity = identity_type(
            publication["namespace"], publication["kind"], part_name, build["version"]
        )
        digest = sha256_bytes(payload)
        receipt = resource_store.artifacts.publish(
            **identity.to_dict(),
            payload=payload,
            actor=actor,
            media_type_value=media_type,
            expected_digest=digest,
            expected_length=len(payload),
            annotations={
                "capability.owner-key": build["ownerKey"],
                "capability.bundle-id": build["bundleId"],
                "capability.build-result-digest": build["buildResultDigest"],
            },
        )
        if not receipt.object_committed or not receipt.metadata_committed:
            raise CapabilityError("Meridian publication did not commit both object and metadata")
        if receipt.ref.identity != identity or receipt.ref.digest != digest:
            raise CapabilityError("Meridian publication returned a different exact reference")
        coordinate = {
            "ownerKey": build["ownerKey"],
            "bundleId": build["bundleId"],
            "version": build["version"],
            "schemaMajor": 1,
            "digest": digest,
            "artifactRef": {
                "schemaVersion": REFERENCE_SCHEMA,
                "resource": receipt.ref.to_dict(),
                "digest": digest,
            },
        }
        if _read_exact(resource_store, coordinate, media_type) != payload:
            raise CapabilityError("Meridian publication readback differs from submitted bytes")
        coordinates[part] = coordinate
    pin = {"coordinate": coordinates["bundle"], **{field: build[field] for field in PIN_FIELDS}}
    from .loader import load_capability_set

    load_capability_set(
        output,
        pin=pin,
        runtime_build_id=pin["producerBuildId"],
        runtime_openapi_digest=pin["openapiDigest"],
        runtime_mcp_descriptor_digest=pin["mcpDescriptorDigest"],
    )
    result = {
        "schemaVersion": "capability.juntai.io/publication-result/v1",
        **coordinates,
        "pin": pin,
    }
    if result_path is not None:
        destination = Path(result_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(canonical_json_bytes(result))
    return result


def load_capability_set_meridian(
    *,
    resource_store: Any,
    pin: Mapping[str, Any],
    runtime_build_id: str,
    runtime_openapi_digest: str,
    runtime_mcp_descriptor_digest: str,
) -> dict[str, Any]:
    """Read exact published bytes, safely unpack, and validate runtime lineage."""
    from .loader import load_capability_set

    payload = _read_exact(resource_store, pin["coordinate"], ARCHIVE_MEDIA_TYPE)
    with TemporaryDirectory(prefix="capability-meridian-") as directory:
        root = Path(directory)
        seen: set[str] = set()
        total = 0
        try:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
                for member in archive:
                    if member.name not in BUILD_FILES or member.name in seen or not member.isfile():
                        raise CapabilityError("invalid capability archive member")
                    total += member.size
                    if member.size < 0 or total > MAX_ARCHIVE_BYTES:
                        raise CapabilityError("capability archive exceeds size limit")
                    seen.add(member.name)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise CapabilityError("missing capability archive member")
                    with stream:
                        (root / member.name).write_bytes(stream.read())
            if seen != BUILD_FILES:
                raise CapabilityError("incomplete capability archive")
        except (tarfile.TarError, OSError) as error:
            raise CapabilityError(f"invalid capability archive: {error}") from error
        return load_capability_set(
            root,
            pin=pin,
            runtime_build_id=runtime_build_id,
            runtime_openapi_digest=runtime_openapi_digest,
            runtime_mcp_descriptor_digest=runtime_mcp_descriptor_digest,
        )
