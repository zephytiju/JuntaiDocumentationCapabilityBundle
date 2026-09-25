"""Framework-neutral loading and provenance checks for exact bundle pins."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .canonical import deterministic_tar, digest_json, sha256_bytes
from .errors import CapabilityError
from .meridian import REFERENCE_SCHEMA, validate_directory
from .schema_validation import validate_schema


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CapabilityError(f"cannot read {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise CapabilityError(f"{path.name} must contain an object")
    return value


def load_capability_set(
    output: str | Path,
    *,
    pin: Mapping[str, Any],
    runtime_build_id: str,
    runtime_openapi_digest: str,
    runtime_mcp_descriptor_digest: str,
) -> dict[str, Any]:
    root = Path(output).resolve()
    graph = _read_json(root / "content-graph.json")
    human = _read_json(root / "human-projection.json")
    mcp = _read_json(root / "mcp-projection.json")
    validate_schema("content-graph", graph)
    required_pin = {
        "coordinate",
        "producerBuildId",
        "openapiDigest",
        "mcpDescriptorDigest",
        "contentGraphDigest",
        "humanProjectionDigest",
        "mcpProjectionDigest",
    }
    if set(pin) != required_pin:
        raise CapabilityError("CapabilityBundlePin is incomplete", code="BUNDLE_INPUT_NOT_EXACT")
    reference = pin["coordinate"].get("artifactRef")
    if isinstance(reference, Mapping) and reference.get("schemaVersion") == REFERENCE_SCHEMA:
        validate_directory(root, pin)
    elif not isinstance(reference, Mapping) or not {
        "artifact_id",
        "version_id",
        "manifest_digest",
    }.issubset(reference):
        raise CapabilityError("pin does not contain an exact Artifact SDK reference")
    elif reference["manifest_digest"] != pin["coordinate"]["digest"]:
        raise CapabilityError("pin coordinate and Artifact reference digests differ")
    exact_runtime = {
        "producerBuildId": runtime_build_id,
        "openapiDigest": runtime_openapi_digest,
        "mcpDescriptorDigest": runtime_mcp_descriptor_digest,
    }
    for field, value in exact_runtime.items():
        if pin[field] != value:
            raise CapabilityError(
                f"runtime {field} differs from the exact bundle pin", code="BUNDLE_INCOMPATIBLE"
            )
    if sha256_bytes((root / "content-graph.json").read_bytes()) != pin["contentGraphDigest"]:
        raise CapabilityError("content graph digest mismatch", code="PROJECTION_DIGEST_MISMATCH")
    if human["projectionDigest"] != pin["humanProjectionDigest"]:
        raise CapabilityError("human projection digest mismatch", code="PROJECTION_DIGEST_MISMATCH")
    if mcp["projectionDigest"] != pin["mcpProjectionDigest"]:
        raise CapabilityError("MCP projection digest mismatch", code="PROJECTION_DIGEST_MISMATCH")
    if graph["contracts"]["mcpDescriptorDigest"] != pin["mcpDescriptorDigest"]:
        raise CapabilityError("graph and pin descriptor digests differ")
    graph_units = {unit["unitId"]: unit for unit in graph["units"]}
    for resource in mcp["resources"]:
        if any(unit_id not in graph_units for unit_id in resource["unitIds"]):
            raise CapabilityError("MCP resource references an unknown unit")
    exact_tools: dict[str, dict[str, Any]] = {}
    for unit in graph["units"]:
        for tool in unit["toolReferences"]:
            previous = exact_tools.setdefault(tool["toolId"], tool)
            if previous != tool:
                raise CapabilityError("content graph contains inconsistent exact tool references")
    for prompt in mcp["prompts"]:
        if prompt["workflowUnitId"] not in graph_units:
            raise CapabilityError("MCP prompt references an unknown workflow")
        for tool in prompt["toolRefs"]:
            if exact_tools.get(tool["toolId"]) != tool:
                raise CapabilityError("MCP prompt tool differs from the canonical graph")
    units = [
        {
            "bundleDigest": pin["coordinate"]["digest"],
            "unitId": unit["unitId"],
            "kind": unit["kind"],
            "contentDigest": unit["contentDigest"],
        }
        for unit in sorted(graph["units"], key=lambda item: item["unitId"])
    ]
    return {
        "pin": dict(pin),
        "units": units,
        "resources": mcp["resources"],
        "prompts": mcp["prompts"],
        "tools": [exact_tools[key] for key in sorted(exact_tools)],
        "compatibility": graph["provenance"].get("compatibility", {}),
        "safetyPolicyUnitIds": [
            unit["unitId"] for unit in graph["units"] if unit["kind"] in {"safety", "policy"}
        ],
    }


def create_derived_projection(
    capability_set: Mapping[str, Any],
    *,
    adapter_id: str,
    adapter_version: str,
    kind: str,
    files: Mapping[str, bytes],
) -> dict[str, Any]:
    allowed = {"mcp-binding", "skill-package", "instruction-file", "retrieval-index"}
    if kind not in allowed or not files:
        raise CapabilityError("framework projection kind or files are invalid")
    archive = deterministic_tar(files)
    return {
        "bundleDigest": capability_set["pin"]["coordinate"]["digest"],
        "mcpDescriptorDigest": capability_set["pin"]["mcpDescriptorDigest"],
        "adapterId": adapter_id,
        "adapterVersion": adapter_version,
        "kind": kind,
        "derivedDigest": sha256_bytes(archive),
        "toolReferencesDigest": digest_json(capability_set["tools"]),
    }


def verify_derived_projection(
    projection: Mapping[str, Any], capability_set: Mapping[str, Any]
) -> None:
    expected = {
        "bundleDigest": capability_set["pin"]["coordinate"]["digest"],
        "mcpDescriptorDigest": capability_set["pin"]["mcpDescriptorDigest"],
        "toolReferencesDigest": digest_json(capability_set["tools"]),
    }
    if any(projection.get(field) != value for field, value in expected.items()):
        raise CapabilityError("derived framework projection changed tools, pin or provenance")
