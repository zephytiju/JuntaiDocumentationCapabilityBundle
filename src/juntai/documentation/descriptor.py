"""Exact consumer for explicitly supported FuseAPI MCP descriptor releases."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, digest_json, sha256_bytes
from .constants import FUSE_DESCRIPTOR_VERSION, FUSE_MCP_PROFILE, SUPPORTED_FUSE_API_VERSIONS
from .errors import CapabilityError

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOOL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")


def _require_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise CapabilityError(f"{field} must be a SHA-256 digest", code="BUNDLE_INPUT_NOT_EXACT")
    return value


def validate_fuseapi_descriptor(
    path: str | Path,
    *,
    expected_digest: str,
    expected_openapi_digest: str,
) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    try:
        descriptor = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CapabilityError("MCP descriptor must be UTF-8 canonical JSON") from error
    canonical = canonical_json_bytes(descriptor)
    if raw != canonical:
        raise CapabilityError(
            "MCP descriptor bytes are not the canonical FuseAPI release form",
            code="BUNDLE_INPUT_NOT_EXACT",
        )
    if sha256_bytes(raw) != expected_digest:
        raise CapabilityError(
            "MCP descriptor digest differs from the exact manifest pin",
            code="BUNDLE_INPUT_NOT_EXACT",
        )
    return validate_fuseapi_descriptor_document(
        descriptor,
        expected_digest=expected_digest,
        expected_openapi_digest=expected_openapi_digest,
    )


def validate_fuseapi_descriptor_document(
    descriptor: object,
    *,
    expected_digest: str,
    expected_openapi_digest: str,
) -> dict[str, Any]:
    if not isinstance(descriptor, dict):
        raise CapabilityError("MCP descriptor must be an object", code="BUNDLE_INPUT_NOT_EXACT")
    _require_digest(expected_digest, "expected descriptor digest")
    _require_digest(expected_openapi_digest, "expected OpenAPI digest")
    if digest_json(descriptor) != expected_digest:
        raise CapabilityError(
            "MCP descriptor canonical digest differs from the exact manifest pin",
            code="BUNDLE_INPUT_NOT_EXACT",
        )
    required = {
        "schemaVersion",
        "serviceId",
        "serviceVersion",
        "buildId",
        "sourceCommit",
        "fuseApiVersion",
        "profile",
        "endpointCatalogSha256",
        "openapiSha256",
        "compatibility",
        "tools",
    }
    if set(descriptor) != required:
        changed_fields = sorted(set(descriptor) ^ required)
        raise CapabilityError(
            f"MCP descriptor fields differ from the supported FuseAPI contract: {changed_fields}",
            code="BUNDLE_INPUT_NOT_EXACT",
        )
    if descriptor["schemaVersion"] != FUSE_DESCRIPTOR_VERSION:
        raise CapabilityError(
            "unsupported FuseAPI MCP descriptor version", code="BUNDLE_INCOMPATIBLE"
        )
    if descriptor["fuseApiVersion"] not in SUPPORTED_FUSE_API_VERSIONS:
        raise CapabilityError(
            f"supported exact FuseAPI versions: {', '.join(SUPPORTED_FUSE_API_VERSIONS)}",
            code="BUNDLE_INCOMPATIBLE",
        )
    if descriptor["profile"] != FUSE_MCP_PROFILE:
        raise CapabilityError(
            "descriptor is not the production MCP profile", code="BUNDLE_INCOMPATIBLE"
        )
    if descriptor["compatibility"] != {"descriptorMajor": 1, "mcpProfileMajor": 1}:
        raise CapabilityError(
            "unsupported FuseAPI compatibility declaration", code="BUNDLE_INCOMPATIBLE"
        )
    if not isinstance(descriptor["serviceId"], str) or not descriptor["serviceId"]:
        raise CapabilityError("descriptor serviceId is missing", code="BUNDLE_INPUT_NOT_EXACT")
    if not isinstance(descriptor["buildId"], str) or not descriptor["buildId"]:
        raise CapabilityError("descriptor buildId is missing", code="BUNDLE_INPUT_NOT_EXACT")
    if (
        not isinstance(descriptor["sourceCommit"], str)
        or _SOURCE_COMMIT.fullmatch(descriptor["sourceCommit"]) is None
    ):
        raise CapabilityError(
            "descriptor sourceCommit is not immutable", code="BUNDLE_INPUT_NOT_EXACT"
        )
    if descriptor["openapiSha256"] != expected_openapi_digest:
        raise CapabilityError(
            "MCP descriptor and manifest do not pin the same OpenAPI digest",
            code="BUNDLE_INPUT_NOT_EXACT",
        )
    tools = descriptor["tools"]
    if (
        not isinstance(tools, list)
        or any(
            not isinstance(item, dict) or not isinstance(item.get("toolId"), str) for item in tools
        )
        or tools != sorted(tools, key=lambda item: item["toolId"])
    ):
        raise CapabilityError("FuseAPI tools must be a deterministically sorted list")
    if digest_json(tools) != descriptor["endpointCatalogSha256"]:
        raise CapabilityError(
            "FuseAPI endpoint catalog digest mismatch", code="BUNDLE_INPUT_NOT_EXACT"
        )

    index: dict[str, dict[str, Any]] = {}
    for tool in tools:
        checked = _validate_tool(tool, expected_digest)
        if checked["toolId"] in index:
            raise CapabilityError("duplicate FuseAPI tool identity", code="TOOL_SIGNATURE_MISMATCH")
        index[checked["toolId"]] = checked
    return {"descriptor": descriptor, "tools": index, "digest": expected_digest}


def _validate_tool(tool: object, descriptor_digest: str) -> dict[str, Any]:
    if not isinstance(tool, dict):
        raise CapabilityError("FuseAPI tool descriptor must be an object")
    required = {
        "toolId",
        "operationId",
        "inputSchema",
        "outputSchema",
        "annotations",
        "streaming",
        "signatureSha256",
        "groupId",
        "endpointId",
        "description",
        "argumentNames",
        "bodyProperty",
    }
    if set(tool) != required:
        raise CapabilityError("FuseAPI tool fields differ from the supported descriptor contract")
    tool_id = tool["toolId"]
    if not isinstance(tool_id, str) or _TOOL_ID.fullmatch(tool_id) is None:
        raise CapabilityError("invalid FuseAPI tool identity")
    signature = {
        "toolId": tool_id,
        "operationId": tool["operationId"],
        "inputSchema": tool["inputSchema"],
        "outputSchema": tool["outputSchema"],
        "annotations": tool["annotations"],
        "streaming": tool["streaming"],
    }
    expected_signature = digest_json(signature)
    if tool["signatureSha256"] != expected_signature:
        raise CapabilityError(
            f"FuseAPI signature digest mismatch for tool {tool_id}",
            code="TOOL_SIGNATURE_MISMATCH",
        )
    return {
        **tool,
        "mcpDescriptorDigest": descriptor_digest,
        "inputSchemaDigest": digest_json(tool["inputSchema"]),
        "outputSchemaDigest": (
            digest_json(tool["outputSchema"]) if tool["outputSchema"] is not None else None
        ),
    }


def validate_exact_tool_reference(
    reference: Mapping[str, Any],
    *,
    descriptor_digest: str,
    tools: Mapping[str, Mapping[str, Any]],
) -> None:
    tool_id = reference.get("toolId")
    tool = tools.get(str(tool_id))
    if tool is None:
        raise CapabilityError(f"unknown MCP Tool {tool_id!r}", code="TOOL_REFERENCE_NOT_FOUND")
    expected = {
        "mcpDescriptorDigest": descriptor_digest,
        "signatureSha256": tool["signatureSha256"],
        "inputSchemaDigest": tool["inputSchemaDigest"],
    }
    if tool["outputSchemaDigest"] is not None:
        expected["outputSchemaDigest"] = tool["outputSchemaDigest"]
    for field, value in expected.items():
        if reference.get(field) != value:
            raise CapabilityError(
                f"tool {tool_id!r} has mismatched {field}", code="TOOL_SIGNATURE_MISMATCH"
            )
    if tool["outputSchemaDigest"] is None and "outputSchemaDigest" in reference:
        raise CapabilityError(
            f"tool {tool_id!r} declares no output schema", code="TOOL_SIGNATURE_MISMATCH"
        )
