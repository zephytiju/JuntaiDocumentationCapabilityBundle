"""Discriminated v2 HTTP capability publication over the public Meridian API."""

from __future__ import annotations

import io
import re
import tarfile
from collections.abc import Mapping
from typing import Any

from .canonical import canonical_json_bytes, deterministic_tar, digest_json, sha256_bytes
from .errors import CapabilityError
from .meridian import MAX_ARCHIVE_BYTES, REFERENCE_SCHEMA, _read_exact, _types
from .openapi import _pairs, compile_openapi_tools

CONTRACT = "capability.juntai.io/openapi-bundle/v2"
MEDIA_TYPE = "application/vnd.juntai.openapi-capability.v2+tar"
FILES = frozenset({"bundle.json", "openapi.json"})
PIN_FIELDS = frozenset(
    {
        "contractVersion",
        "coordinate",
        "producerBuildId",
        "serviceId",
        "openapiDigest",
        "manifestDigest",
        "sourceDigest",
    }
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _closed(value, fields, label):
    if not isinstance(value, Mapping) or set(value) != set(fields):
        raise CapabilityError(f"{label} has missing or unknown fields")


def _identity(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", value):
        raise CapabilityError(f"invalid {label}")


def validate_openapi_pin(pin: Mapping[str, Any]) -> None:
    """Validate the v2 discriminator without accepting v1 substitutions."""
    _closed(pin, PIN_FIELDS, "OpenAPI capability pin")
    if pin["contractVersion"] != CONTRACT:
        raise CapabilityError("unsupported OpenAPI capability contract")
    coordinate = pin["coordinate"]
    _closed(
        coordinate,
        {"ownerKey", "bundleId", "version", "schemaMajor", "digest", "artifactRef"},
        "OpenAPI coordinate",
    )
    if type(coordinate["schemaMajor"]) is not int or coordinate["schemaMajor"] != 2:
        raise CapabilityError("OpenAPI coordinate requires schema major 2")
    for field in ("ownerKey", "bundleId", "version"):
        _identity(coordinate[field], field)
    reference = coordinate["artifactRef"]
    _closed(reference, {"schemaVersion", "resource", "digest"}, "Meridian reference")
    resource = reference["resource"]
    _closed(
        resource,
        {"resourceId", "namespace", "kind", "name", "version", "profile", "digest"},
        "Meridian resource",
    )
    if (
        reference["schemaVersion"] != REFERENCE_SCHEMA
        or resource["profile"] != "artifact"
        or resource["version"] != coordinate["version"]
        or not isinstance(coordinate["digest"], str)
        or not _DIGEST.fullmatch(coordinate["digest"])
        or reference["digest"] != coordinate["digest"]
        or resource["digest"] != coordinate["digest"]
    ):
        raise CapabilityError("inconsistent exact Meridian coordinate")
    for field in ("resourceId", "namespace", "kind", "name"):
        if not isinstance(resource[field], str) or not resource[field]:
            raise CapabilityError("incomplete Meridian resource identity")
    for field in ("openapiDigest", "manifestDigest", "sourceDigest"):
        if not isinstance(pin[field], str) or not _DIGEST.fullmatch(pin[field]):
            raise CapabilityError(f"invalid exact {field}")
    for field in ("producerBuildId", "serviceId"):
        _identity(pin[field], field)


def _validate_manifest(manifest: Mapping[str, Any], openapi: bytes) -> list[dict]:
    _closed(
        manifest,
        {
            "contractVersion",
            "ownerKey",
            "bundleId",
            "version",
            "producerBuildId",
            "serviceId",
            "source",
            "openapiDigest",
            "units",
            "selections",
            "tools",
        },
        "OpenAPI bundle manifest",
    )
    if manifest["contractVersion"] != CONTRACT or manifest["openapiDigest"] != sha256_bytes(
        openapi
    ):
        raise CapabilityError("OpenAPI contract or original byte digest mismatch")
    for field in ("ownerKey", "bundleId", "version", "producerBuildId", "serviceId"):
        _identity(manifest[field], field)
    source = manifest["source"]
    _closed(source, {"repository", "sourceCommit", "artifactDigest", "artifactPath"}, "source")
    if (
        not isinstance(source["repository"], str)
        or not source["repository"].startswith("https://")
        or not isinstance(source["sourceCommit"], str)
        or not re.fullmatch(r"[0-9a-f]{40}", source["sourceCommit"])
        or not isinstance(source["artifactDigest"], str)
        or not _DIGEST.fullmatch(source["artifactDigest"])
        or not isinstance(source["artifactPath"], str)
        or not source["artifactPath"]
        or source["artifactPath"].startswith("/")
        or ".." in source["artifactPath"].split("/")
    ):
        raise CapabilityError("incomplete exact source provenance")
    units = manifest["units"]
    if not isinstance(units, list) or not units:
        raise CapabilityError("bundle must contain capability units")
    policies, seen = set(), set()
    for unit in units:
        _closed(unit, {"unitId", "kind", "content"}, "capability unit")
        _identity(unit["unitId"], "unitId")
        if unit["unitId"] in seen:
            raise CapabilityError("duplicate capability unit")
        seen.add(unit["unitId"])
        if unit["kind"] not in {"document", "workflow", "evaluation", "safety", "policy"}:
            raise CapabilityError("unsupported capability unit kind")
        if not isinstance(unit["content"], str) or not unit["content"].strip():
            raise CapabilityError("empty capability unit content")
        if unit["kind"] in {"safety", "policy"}:
            policies.add(unit["unitId"])
    if not isinstance(manifest["selections"], list):
        raise CapabilityError("operation selections must be an array")
    tools = compile_openapi_tools(
        openapi, service_id=manifest["serviceId"], selections=manifest["selections"]
    )
    if manifest["tools"] != [tool["reference"] for tool in tools]:
        raise CapabilityError("exact tool references differ from released OpenAPI operations")
    for tool in tools:
        approval = tool["reference"]["approvalPolicyUnitId"]
        if approval is not None and approval not in policies:
            raise CapabilityError("approval policy is absent from exact bundle")
    return tools


def build_openapi_bundle(openapi: bytes, *, metadata: Mapping[str, Any]) -> bytes:
    """Build an immutable snapshot; source authenticity is verified by the caller.

    The explicit source binding is hashed into the manifest and returned pin. It
    is not a substitute for release signature verification at build admission.
    """
    _closed(
        metadata,
        {
            "ownerKey",
            "bundleId",
            "version",
            "producerBuildId",
            "serviceId",
            "source",
            "units",
            "selections",
        },
        "OpenAPI build metadata",
    )
    tools = compile_openapi_tools(
        openapi, service_id=metadata["serviceId"], selections=metadata["selections"]
    )
    manifest = {
        **metadata,
        "contractVersion": CONTRACT,
        "openapiDigest": sha256_bytes(openapi),
        "tools": [tool["reference"] for tool in tools],
    }
    _validate_manifest(manifest, openapi)
    archive = deterministic_tar(
        {"bundle.json": canonical_json_bytes(manifest), "openapi.json": openapi}
    )
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise CapabilityError("OpenAPI bundle exceeds archive limit")
    return archive


def inspect_openapi_bundle(payload: bytes) -> tuple[dict, bytes]:
    """Safely inspect without filesystem extraction; preserve descriptor bytes."""
    import json

    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_ARCHIVE_BYTES:
        raise CapabilityError("invalid OpenAPI bundle size")
    files, total = {}, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            for member in archive:
                total += member.size
                if (
                    member.name not in FILES
                    or member.name in files
                    or not member.isfile()
                    or member.sparse is not None
                    or member.size < 0
                    or total > MAX_ARCHIVE_BYTES
                ):
                    raise CapabilityError("invalid OpenAPI bundle archive member")
                stream = archive.extractfile(member)
                if stream is None:
                    raise CapabilityError("missing OpenAPI bundle member")
                with stream:
                    files[member.name] = stream.read()
        if set(files) != FILES:
            raise CapabilityError("incomplete OpenAPI bundle archive")
        manifest = json.loads(files["bundle.json"], object_pairs_hook=_pairs)
        if canonical_json_bytes(manifest) != files["bundle.json"]:
            raise CapabilityError("bundle manifest must be canonical JSON")
        _validate_manifest(manifest, files["openapi.json"])
        if deterministic_tar(files) != payload:
            raise CapabilityError("OpenAPI bundle archive is not the exact deterministic encoding")
        return manifest, files["openapi.json"]
    except (tarfile.TarError, OSError, ValueError, TypeError, KeyError) as error:
        raise CapabilityError(f"invalid OpenAPI capability bundle: {error}") from error


def _pin(manifest: Mapping[str, Any], coordinate: Mapping[str, Any]) -> dict:
    return {
        "contractVersion": CONTRACT,
        "coordinate": dict(coordinate),
        **{key: manifest[key] for key in ("producerBuildId", "serviceId", "openapiDigest")},
        "manifestDigest": digest_json(manifest),
        "sourceDigest": digest_json(manifest["source"]),
    }


def load_openapi_bundle_meridian(*, resource_store: Any, pin: Mapping[str, Any]) -> dict:
    """Read the exact published v2 object and independently rederive every tool."""
    validate_openapi_pin(pin)
    payload = _read_exact(resource_store, pin["coordinate"], MEDIA_TYPE, schema_major=2)
    manifest, _ = inspect_openapi_bundle(payload)
    if _pin(manifest, pin["coordinate"]) != pin or any(
        manifest[key] != pin["coordinate"][key] for key in ("ownerKey", "bundleId", "version")
    ):
        raise CapabilityError("OpenAPI capability pin differs from published source or identity")
    return {
        "openapiBinding": {"bundleDigest": pin["coordinate"]["digest"], "manifest": manifest},
        "pin": dict(pin),
        "tools": manifest["tools"],
        "resources": [],
        "prompts": [],
        "units": [
            {
                "bundleDigest": pin["coordinate"]["digest"],
                "unitId": unit["unitId"],
                "kind": unit["kind"],
                "contentDigest": sha256_bytes(unit["content"].encode()),
            }
            for unit in manifest["units"]
        ],
        "safetyPolicyUnitIds": [
            u["unitId"] for u in manifest["units"] if u["kind"] in {"safety", "policy"}
        ],
    }


def validate_openapi_bindings(
    capability: Mapping[str, Any], descriptors: Mapping[str, bytes]
) -> list[dict]:
    """Revalidate Delivery's versioned bindings at Harness and Runtime admission.

    The signed Delivery/Harness lineage supplies the trusted pins; neither a
    nonstandard OpenAPI serviceId nor a bare descriptor hash supplies identity.
    """
    if capability.get("contractVersion") != "v2":
        raise CapabilityError("OpenAPI bindings require resolved capability v2")
    pins = capability.get("bundlePins")
    bindings = capability.get("openapiBindings")
    if not isinstance(pins, list) or not isinstance(bindings, list) or not pins:
        raise CapabilityError("missing versioned OpenAPI bundle bindings")
    by_digest = {}
    for pin in pins:
        validate_openapi_pin(pin)
        digest = pin["coordinate"]["digest"]
        if digest in by_digest:
            raise CapabilityError("duplicate OpenAPI bundle pin")
        by_digest[digest] = pin
    seen, tools = set(), []
    expected_descriptors = []
    for binding in bindings:
        _closed(binding, {"bundleDigest", "manifest"}, "OpenAPI source binding")
        digest = binding["bundleDigest"]
        if digest not in by_digest or digest in seen:
            raise CapabilityError("absent or duplicate OpenAPI bundle binding")
        seen.add(digest)
        pin, manifest = by_digest[digest], binding["manifest"]
        payload = descriptors.get(pin["openapiDigest"])
        if payload is None:
            raise CapabilityError("exact original OpenAPI bytes are absent")
        compiled = _validate_manifest(manifest, payload)
        if _pin(manifest, pin["coordinate"]) != pin or any(
            manifest[key] != pin["coordinate"][key] for key in ("ownerKey", "bundleId", "version")
        ):
            raise CapabilityError("OpenAPI source or service binding differs from pin")
        # Reconstructing the small deterministic archive also binds the manifest
        # to its published object digest, without a storage/network read here.
        archive = deterministic_tar(
            {"bundle.json": canonical_json_bytes(manifest), "openapi.json": payload}
        )
        if sha256_bytes(archive) != digest:
            raise CapabilityError("OpenAPI binding differs from published bundle bytes")
        tools.extend(compiled)
        expected_descriptors.append(
            {"protocol": "openapi", "serviceId": pin["serviceId"], "digest": pin["openapiDigest"]}
        )
    if seen != set(by_digest):
        raise CapabilityError("incomplete OpenAPI bundle bindings")

    def ordered(values):
        return sorted(values, key=canonical_json_bytes)

    if ordered(expected_descriptors) != ordered(capability.get("descriptorPins", [])):
        raise CapabilityError("descriptor identities differ from exact OpenAPI bundle bindings")
    references = [tool["reference"] for tool in tools]
    identities = {(r["serviceId"], r["operationId"]) for r in references}
    if len(identities) != len(references):
        raise CapabilityError("ambiguous OpenAPI operation across bundle bindings")
    if ordered(references) != ordered(capability.get("exactTools", [])):
        raise CapabilityError("exact tools differ from source-bound OpenAPI operations")
    for boundary in capability.get("maximumToolBoundary", []):
        _closed(
            boundary,
            {"protocol", "serviceId", "operationId", "openapiDigest"},
            "OpenAPI maximum boundary",
        )
        if not any(
            all(reference[key] == value for key, value in boundary.items())
            for reference in references
        ):
            raise CapabilityError("OpenAPI maximum boundary exceeds exact tool inventory")
    return tools


def publish_openapi_bundle_meridian(
    payload: bytes, *, resource_store: Any, namespace: str, kind: str, name: str, actor: str
) -> dict:
    """Publish one complete v2 snapshot and verify committed exact readback."""
    manifest, _ = inspect_openapi_bundle(payload)
    identity_type, _ = _types()
    identity = identity_type(namespace, kind, name, manifest["version"])
    digest = sha256_bytes(payload)
    receipt = resource_store.artifacts.publish(
        **identity.to_dict(),
        payload=payload,
        actor=actor,
        media_type_value=MEDIA_TYPE,
        expected_digest=digest,
        expected_length=len(payload),
        annotations={
            "capability.owner-key": manifest["ownerKey"],
            "capability.bundle-id": manifest["bundleId"],
            "capability.manifest-digest": digest_json(manifest),
        },
    )
    if (
        not receipt.object_committed
        or not receipt.metadata_committed
        or receipt.ref.identity != identity
        or receipt.ref.digest != digest
    ):
        raise CapabilityError("Meridian did not commit the exact OpenAPI bundle")
    coordinate = {
        **{key: manifest[key] for key in ("ownerKey", "bundleId", "version")},
        "schemaMajor": 2,
        "digest": digest,
        "artifactRef": {
            "schemaVersion": REFERENCE_SCHEMA,
            "resource": receipt.ref.to_dict(),
            "digest": digest,
        },
    }
    pin = _pin(manifest, coordinate)
    load_openapi_bundle_meridian(resource_store=resource_store, pin=pin)
    return {"schemaVersion": "capability.juntai.io/publication-result/v2", "pin": pin}
