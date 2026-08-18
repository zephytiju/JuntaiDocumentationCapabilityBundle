"""Resolve, validate and deterministically package capability bundles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .canonical import (
    canonical_json_bytes,
    checked_relative_file,
    deterministic_tar,
    digest_json,
    normalized_text_bytes,
    sha256_bytes,
)
from .constants import MEDIA_TYPES, PACKAGE_VERSION
from .descriptor import (
    validate_exact_tool_reference,
    validate_fuseapi_descriptor,
    validate_fuseapi_descriptor_document,
)
from .errors import CapabilityError
from .render import render_human, render_mcp
from .schema_validation import validate_schema

_LOCK_VERSION = "capability.juntai.io/content-lock/v1"
_PROHIBITED = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}"), "bearer token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (
        re.compile(
            r"(?i)(?:password|client_secret|api_key)\s*[:=]\s*['\"]?(?!<|\{|example|redacted)[^\s'\"]{12,}"
        ),
        "credential",
    ),
)


@dataclass(frozen=True)
class BuildResult:
    output: Path
    graph: dict[str, Any]
    human_projection: dict[str, Any]
    mcp_projection: dict[str, Any]
    manifest: dict[str, Any]


def _read_json_bytes(path: Path) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    try:
        return raw, json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CapabilityError(f"exact contract is not UTF-8 JSON: {path}") from error


def _privacy_check(text: str, *, unit_id: str) -> None:
    lowered = text.lower()
    if "chain-of-thought" in lowered and "do not" not in lowered:
        raise CapabilityError(
            f"unit {unit_id!r} appears to contain chain-of-thought material",
            code="PRIVACY_FILTER_REJECTED",
        )
    for pattern, kind in _PROHIBITED:
        if pattern.search(text):
            raise CapabilityError(
                f"unit {unit_id!r} contains prohibited {kind}", code="PRIVACY_FILTER_REJECTED"
            )


def resolve_manifest(
    manifest_path: str | Path,
    *,
    lock_path: str | Path | None = None,
) -> dict[str, Any]:
    """Freeze exact producer-owned inputs into an offline deterministic lock."""

    manifest_file = Path(manifest_path).resolve()
    try:
        manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise CapabilityError(f"cannot read manifest: {error}") from error
    validate_schema("manifest", manifest)
    base = manifest_file.parent

    openapi_path = checked_relative_file(base, manifest["contracts"]["openapi"]["path"])
    openapi_raw, openapi = _read_json_bytes(openapi_path)
    openapi_digest = sha256_bytes(openapi_raw)
    if openapi_digest != manifest["contracts"]["openapi"]["digest"]:
        raise CapabilityError("OpenAPI digest differs from manifest", code="BUNDLE_INPUT_NOT_EXACT")

    mcp_path = checked_relative_file(base, manifest["contracts"]["mcp"]["path"])
    descriptor_digest = manifest["contracts"]["mcp"]["descriptorDigest"]
    if manifest["contracts"]["mcp"]["digest"] != descriptor_digest:
        raise CapabilityError(
            "MCP input digest and descriptorDigest must be identical",
            code="BUNDLE_INPUT_NOT_EXACT",
        )
    checked_descriptor = validate_fuseapi_descriptor(
        mcp_path,
        expected_digest=descriptor_digest,
        expected_openapi_digest=openapi_digest,
    )

    schema_inputs: list[dict[str, Any]] = []
    for declaration in manifest["contracts"].get("schemas", []):
        path = checked_relative_file(base, declaration["path"])
        raw, document = _read_json_bytes(path)
        if sha256_bytes(raw) != declaration["digest"]:
            raise CapabilityError(
                f"schema {declaration['schemaId']!r} digest differs from manifest",
                code="BUNDLE_INPUT_NOT_EXACT",
            )
        schema_inputs.append({**declaration, "document": document, "raw": raw.decode("utf-8")})

    source_root = (base / manifest["sources"]["root"]).resolve()
    if source_root != base and base not in source_root.parents:
        raise CapabilityError("documentation source root escapes the manifest directory")
    if not source_root.is_dir():
        raise CapabilityError("documentation source root does not exist")
    units: list[dict[str, Any]] = []
    for declaration in manifest["sources"]["units"]:
        source = checked_relative_file(source_root, declaration["sourcePath"])
        content = normalized_text_bytes(source).decode("utf-8")
        _privacy_check(content, unit_id=declaration["unitId"])
        units.append(
            {
                **declaration,
                "toolReferences": declaration.get("toolReferences", []),
                "schemaReferences": declaration.get("schemaReferences", []),
                "content": content,
                "contentDigest": sha256_bytes(content.encode("utf-8")),
            }
        )

    core = {
        "lockVersion": _LOCK_VERSION,
        "manifest": manifest,
        "resolved": {
            "openapi": {
                "document": openapi,
                "raw": openapi_raw.decode("utf-8"),
                "digest": openapi_digest,
            },
            "mcp": {
                "descriptor": checked_descriptor["descriptor"],
                "digest": descriptor_digest,
            },
            "schemas": schema_inputs,
            "units": units,
        },
    }
    lock = {**core, "lockDigest": digest_json(core)}
    validate_lock(lock)
    if lock_path is not None:
        destination = Path(lock_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(canonical_json_bytes(lock))
    return lock


def load_lock(lock: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(lock, dict):
        return lock
    try:
        loaded = json.loads(Path(lock).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CapabilityError(f"cannot read capability lock: {error}") from error
    if not isinstance(loaded, dict):
        raise CapabilityError("capability lock must be an object")
    return loaded


def validate_lock(lock: dict[str, Any] | str | Path) -> dict[str, Any]:
    lock = load_lock(lock)
    if lock.get("lockVersion") != _LOCK_VERSION:
        raise CapabilityError("unsupported capability lock version", code="BUNDLE_INCOMPATIBLE")
    core = {key: value for key, value in lock.items() if key != "lockDigest"}
    if digest_json(core) != lock.get("lockDigest"):
        raise CapabilityError("capability lock digest mismatch", code="BUNDLE_INPUT_NOT_EXACT")
    manifest = lock.get("manifest")
    validate_schema("manifest", manifest)
    resolved = lock.get("resolved")
    if not isinstance(resolved, dict):
        raise CapabilityError("capability lock has no resolved inputs")
    openapi = resolved["openapi"]
    if sha256_bytes(openapi["raw"].encode("utf-8")) != openapi["digest"]:
        raise CapabilityError("locked OpenAPI bytes changed", code="BUNDLE_INPUT_NOT_EXACT")
    mcp = resolved["mcp"]
    checked_descriptor = validate_fuseapi_descriptor_document(
        mcp["descriptor"],
        expected_digest=mcp["digest"],
        expected_openapi_digest=openapi["digest"],
    )

    schemas = {item["schemaId"]: item for item in resolved.get("schemas", [])}
    if len(schemas) != len(resolved.get("schemas", [])):
        raise CapabilityError("duplicate schema identity")
    for schema in schemas.values():
        if sha256_bytes(schema["raw"].encode("utf-8")) != schema["digest"]:
            raise CapabilityError("locked schema bytes changed", code="BUNDLE_INPUT_NOT_EXACT")

    units = resolved.get("units")
    if not isinstance(units, list) or not units:
        raise CapabilityError("capability lock contains no documentation units")
    by_id: dict[str, dict[str, Any]] = {}
    for unit in units:
        unit_id = unit["unitId"]
        if unit_id in by_id:
            raise CapabilityError(f"duplicate document unit {unit_id!r}", code="GRAPH_INVALID")
        if sha256_bytes(unit["content"].encode("utf-8")) != unit["contentDigest"]:
            raise CapabilityError(f"document unit {unit_id!r} digest mismatch")
        _privacy_check(unit["content"], unit_id=unit_id)
        if "agent" in unit["audiences"] and "resourceId" not in unit.get("mcp", {}):
            raise CapabilityError(
                f"agent unit {unit_id!r} requires an authored MCP resourceId",
                code="GRAPH_INVALID",
            )
        if "promptId" in unit.get("mcp", {}) and (
            unit["kind"] != "workflow" or unit["mcp"].get("userInvoked") is not True
        ):
            raise CapabilityError("MCP Prompts must be explicit user-invoked workflow units")
        by_id[unit_id] = unit

    _validate_parent_graph(by_id)
    for unit in units:
        for reference in unit.get("toolReferences", []):
            validate_exact_tool_reference(
                reference,
                descriptor_digest=mcp["digest"],
                tools=checked_descriptor["tools"],
            )
            approval_id = reference.get("approvalPolicyUnitId")
            if approval_id is not None and (
                approval_id not in by_id or by_id[approval_id]["kind"] not in {"policy", "safety"}
            ):
                raise CapabilityError(
                    f"tool approval reference {approval_id!r} is not an authored policy unit",
                    code="GRAPH_INVALID",
                )
        for reference in unit.get("schemaReferences", []):
            locked = schemas.get(reference["schemaId"])
            if locked is None or locked["digest"] != reference["digest"]:
                raise CapabilityError(
                    f"unknown or drifted schema reference {reference['schemaId']!r}",
                    code="BUNDLE_INPUT_NOT_EXACT",
                )
        if unit["kind"] == "example":
            _validate_example(unit, checked_descriptor["tools"])
    return lock


def _validate_parent_graph(by_id: dict[str, dict[str, Any]]) -> None:
    for unit_id, unit in by_id.items():
        seen = {unit_id}
        parent = unit.get("parentUnitId")
        while parent is not None:
            if parent not in by_id:
                raise CapabilityError(
                    f"unknown parent unit {parent!r}", code="DOCUMENT_UNIT_NOT_FOUND"
                )
            if parent in seen:
                raise CapabilityError("document hierarchy contains a cycle", code="GRAPH_INVALID")
            seen.add(parent)
            parent = by_id[parent].get("parentUnitId")


def _validate_example(unit: dict[str, Any], tools: dict[str, dict[str, Any]]) -> None:
    try:
        example = json.loads(unit["content"])
    except json.JSONDecodeError as error:
        raise CapabilityError(
            f"example {unit['unitId']!r} must be structured JSON", code="GRAPH_INVALID"
        ) from error
    if not isinstance(example, dict) or set(example) != {
        "input",
        "expectedToolCalls",
        "expectedOutcome",
    }:
        raise CapabilityError(
            f"example {unit['unitId']!r} must declare input, expectedToolCalls and expectedOutcome"
        )
    if not isinstance(example["expectedToolCalls"], list):
        raise CapabilityError("expectedToolCalls must be an array")
    for call in example["expectedToolCalls"]:
        if not isinstance(call, dict) or set(call) != {"toolId", "arguments"}:
            raise CapabilityError("each expected tool call must contain toolId and arguments")
        tool = tools.get(call["toolId"])
        if tool is None:
            raise CapabilityError(
                f"example references unknown tool {call['toolId']!r}",
                code="TOOL_REFERENCE_NOT_FOUND",
            )
        errors = sorted(
            Draft202012Validator(tool["inputSchema"]).iter_errors(call["arguments"]),
            key=lambda item: list(item.absolute_path),
        )
        if errors:
            raise CapabilityError(
                f"example arguments do not match {call['toolId']!r}: {errors[0].message}"
            )


def _content_graph(lock: dict[str, Any]) -> dict[str, Any]:
    manifest = lock["manifest"]
    resolved = lock["resolved"]
    units = sorted(resolved["units"], key=lambda item: item["unitId"])
    edges: list[dict[str, Any]] = []
    for unit in units:
        if "parentUnitId" in unit:
            edges.append(
                {
                    "fromUnitId": unit["unitId"],
                    "relation": "references",
                    "toUnitId": unit["parentUnitId"],
                }
            )
        for reference in unit.get("toolReferences", []):
            edges.append(
                {
                    "fromUnitId": unit["unitId"],
                    "relation": "invokes-tool",
                    "tool": reference,
                }
            )
        for reference in unit.get("schemaReferences", []):
            edges.append(
                {
                    "fromUnitId": unit["unitId"],
                    "relation": "uses-schema",
                    "schema": reference,
                }
            )
    provenance = {
        **manifest["provenance"],
        "producerBuildId": manifest["metadata"]["producerBuildId"],
        "openapiDigest": resolved["openapi"]["digest"],
        "mcpDescriptorDigest": resolved["mcp"]["digest"],
        "sourceDigests": {unit["unitId"]: unit["contentDigest"] for unit in units},
        "lifecycle": manifest["compatibility"]["lifecycle"],
        "compatibility": manifest["compatibility"],
    }
    graph = {
        "schemaVersion": "1",
        "bundle": {
            "ownerKey": manifest["metadata"]["ownerKey"],
            "bundleId": manifest["metadata"]["bundleId"],
            "version": manifest["metadata"]["version"],
            "schemaMajor": 1,
        },
        "units": units,
        "edges": sorted(
            edges,
            key=lambda item: (
                item["fromUnitId"],
                item["relation"],
                item.get("toUnitId", ""),
                item.get("tool", {}).get("toolId", ""),
                item.get("schema", {}).get("schemaId", ""),
            ),
        ),
        "contracts": {
            "openapiDigest": resolved["openapi"]["digest"],
            "mcpDescriptorDigest": resolved["mcp"]["digest"],
            "mcpServiceId": resolved["mcp"]["descriptor"]["serviceId"],
            "mcpBuildId": resolved["mcp"]["descriptor"]["buildId"],
            "fuseApiVersion": resolved["mcp"]["descriptor"]["fuseApiVersion"],
        },
        "provenance": provenance,
    }
    validate_schema("content-graph", graph)
    return graph


def build_bundle(lock: dict[str, Any] | str | Path, *, out: str | Path) -> BuildResult:
    lock = validate_lock(lock)
    graph = _content_graph(lock)
    graph_bytes = canonical_json_bytes(graph)
    human_projection, human_archive, _ = render_human(graph)
    mcp_projection, mcp_bytes = render_mcp(graph)
    provenance_bytes = canonical_json_bytes(graph["provenance"])
    bundle_files = {
        "content-graph.json": graph_bytes,
        "manifest.json": canonical_json_bytes(lock["manifest"]),
        "contracts/mcp-descriptor.json": canonical_json_bytes(
            lock["resolved"]["mcp"]["descriptor"]
        ),
        **{
            f"units/{unit['unitId']}.md": unit["content"].encode("utf-8") for unit in graph["units"]
        },
    }
    bundle_archive = deterministic_tar(bundle_files)
    agent_archive = deterministic_tar(
        {**bundle_files, "mcp-projection.json": mcp_bytes, "provenance.json": provenance_bytes}
    )
    artifact_bytes = {
        "capability-bundle.tar": bundle_archive,
        "agent-capability-bundle.tar": agent_archive,
        "documentation-human.tar": human_archive,
        "documentation-mcp.json": mcp_bytes,
        "provenance.json": provenance_bytes,
    }
    artifact_media_types = {
        "capability-bundle.tar": MEDIA_TYPES["bundle"],
        "agent-capability-bundle.tar": MEDIA_TYPES["agent_bundle"],
        "documentation-human.tar": MEDIA_TYPES["human"],
        "documentation-mcp.json": MEDIA_TYPES["mcp"],
        "provenance.json": MEDIA_TYPES["provenance"],
    }
    output = Path(out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "content-graph.json").write_bytes(graph_bytes)
    (output / "human-projection.json").write_bytes(canonical_json_bytes(human_projection))
    (output / "mcp-projection.json").write_bytes(mcp_bytes)
    for name, payload in artifact_bytes.items():
        (output / name).write_bytes(payload)
    build_core = {
        "schemaVersion": "capability.juntai.io/build-result/v1",
        "packageVersion": PACKAGE_VERSION,
        "ownerKey": graph["bundle"]["ownerKey"],
        "bundleId": graph["bundle"]["bundleId"],
        "version": graph["bundle"]["version"],
        "producerBuildId": graph["provenance"]["producerBuildId"],
        "openapiDigest": graph["contracts"]["openapiDigest"],
        "mcpDescriptorDigest": graph["contracts"]["mcpDescriptorDigest"],
        "contentGraphDigest": sha256_bytes(graph_bytes),
        "humanProjectionDigest": human_projection["projectionDigest"],
        "mcpProjectionDigest": mcp_projection["projectionDigest"],
        "publication": lock["manifest"]["publication"],
        "provenance": graph["provenance"],
        "artifacts": {
            name: {
                "digest": sha256_bytes(payload),
                "byteLength": len(payload),
                "mediaType": artifact_media_types[name],
            }
            for name, payload in sorted(artifact_bytes.items())
        },
    }
    build_manifest = {**build_core, "buildResultDigest": digest_json(build_core)}
    (output / "build-result.json").write_bytes(canonical_json_bytes(build_manifest))
    return BuildResult(
        output=output,
        graph=graph,
        human_projection=human_projection,
        mcp_projection=mcp_projection,
        manifest=build_manifest,
    )
