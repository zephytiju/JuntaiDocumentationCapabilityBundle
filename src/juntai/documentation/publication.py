"""Direct backend Artifact SDK publication with exact immutable results."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_json_bytes, sha256_bytes
from .errors import CapabilityError


class ArtifactClientPort(Protocol):
    def publish(self, **kwargs: Any) -> object: ...


def _load_build(output: str | Path) -> tuple[Path, dict[str, Any]]:
    root = Path(output).resolve()
    try:
        build = json.loads((root / "build-result.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CapabilityError(f"cannot read build result: {error}") from error
    for name, artifact in build["artifacts"].items():
        payload = (root / name).read_bytes()
        if sha256_bytes(payload) != artifact["digest"] or len(payload) != artifact["byteLength"]:
            raise CapabilityError(f"built artifact changed before publication: {name}")
    return root, build


def _reference(value: object) -> dict[str, Any]:
    reference = getattr(value, "reference", None)
    if reference is None:
        raise CapabilityError("Artifact SDK returned no exact reference")
    to_dict = getattr(reference, "to_dict", None)
    mapped = to_dict() if callable(to_dict) else reference
    if not isinstance(mapped, Mapping):
        raise CapabilityError("Artifact SDK returned an invalid exact reference")
    result = dict(mapped)
    required = {"artifact_id", "version_id", "manifest_digest", "version", "name", "kind"}
    if not required.issubset(result) or result["manifest_digest"] == "":
        raise CapabilityError("Artifact SDK exact reference is incomplete")
    return result


def _idempotency(build_id: str, part: str) -> str:
    bounded = re.sub(r"[^A-Za-z0-9_.-]", "-", f"capability-{build_id}-{part}")
    return bounded[:128]


def _coordinate(build: Mapping[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    return {
        "ownerKey": build["ownerKey"],
        "bundleId": build["bundleId"],
        "version": build["version"],
        "artifactRef": reference,
        "digest": reference["manifest_digest"],
        "schemaMajor": 1,
    }


def publish_bundle(
    output: str | Path,
    *,
    artifact_client: ArtifactClientPort,
    result_path: str | Path | None = None,
) -> dict[str, Any]:
    """Publish bytes through `juntai-artifact-client==1.0.2` only.

    The Artifact SDK performs direct OCI upload and generic gRPC metadata
    registration. This function never constructs a Registry, OCI, browser, or
    service transport.
    """

    try:
        from juntai.artifact import ArtifactLayer
    except ImportError as error:
        raise CapabilityError(
            "publication requires the juntai-documentation-capability[artifact] extra"
        ) from error

    root, build = _load_build(output)
    publication = build["publication"]
    provenance = {
        "producer_identity": f"build/{build['ownerKey']}",
        "source_revision": build["provenance"]["sourceCommit"],
        "build_id": build["producerBuildId"],
        "created_at": build["provenance"]["builtAt"],
    }
    common = {
        "namespace": publication["namespace"],
        "kind": publication["kind"],
        "version": build["version"],
        "provenance": provenance,
        "labels": {
            "capability.bundle-id": build["bundleId"],
            "capability.owner-key": build["ownerKey"],
            "capability.schema-major": "1",
            "capability.visibility": publication["visibility"],
        },
        "annotations": {
            "capability.content-graph-digest": build["contentGraphDigest"],
            "capability.mcp-descriptor-digest": build["mcpDescriptorDigest"],
        },
    }
    base_name = publication["name"]
    definitions = {
        "bundle": (
            base_name,
            ["capability-bundle.tar", "agent-capability-bundle.tar"],
        ),
        "humanProjection": (f"{base_name}-human", ["documentation-human.tar"]),
        "mcpProjection": (f"{base_name}-mcp", ["documentation-mcp.json"]),
        "provenance": (f"{base_name}-provenance", ["provenance.json"]),
    }
    coordinates: dict[str, dict[str, Any]] = {}
    for part, (name, filenames) in definitions.items():
        layers = [
            ArtifactLayer(
                media_type=build["artifacts"][filename]["mediaType"],
                data=(root / filename).read_bytes(),
                annotations={"capability.filename": filename},
            )
            for filename in filenames
        ]
        published = artifact_client.publish(
            **common,
            name=name,
            layers=layers,
            idempotency_key=_idempotency(build["producerBuildId"], part),
        )
        coordinates[part] = _coordinate(build, _reference(published))

    pin = {
        "coordinate": coordinates["bundle"],
        "producerBuildId": build["producerBuildId"],
        "openapiDigest": build["openapiDigest"],
        "mcpDescriptorDigest": build["mcpDescriptorDigest"],
        "contentGraphDigest": build["contentGraphDigest"],
        "humanProjectionDigest": build["humanProjectionDigest"],
        "mcpProjectionDigest": build["mcpProjectionDigest"],
    }
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


def application_documentation_link(
    publication_result: Mapping[str, Any],
    *,
    contribution_key: str,
    route_key: str,
) -> dict[str, Any]:
    """Create association input only from a completed exact publication result."""

    pin = publication_result.get("pin")
    if not isinstance(pin, Mapping):
        raise CapabilityError("publish-before-associate requires a publication result")
    reference = pin.get("coordinate", {}).get("artifactRef")
    if not isinstance(reference, Mapping) or not {
        "artifact_id",
        "version_id",
        "manifest_digest",
    }.issubset(reference):
        raise CapabilityError("application association requires an exact Artifact reference")
    return {
        "presentationRole": "application.documentation",
        "contributionKey": contribution_key,
        "ownerKey": pin["coordinate"]["ownerKey"],
        "routeKey": route_key,
        "pin": pin,
    }
