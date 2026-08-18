from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import relock

from juntai.documentation.canonical import digest_json
from juntai.documentation.descriptor import validate_fuseapi_descriptor
from juntai.documentation.errors import CapabilityError
from juntai.documentation.packager import validate_lock


def test_exact_fuseapi_200_generator_contract_is_consumed(tmp_path: Path) -> None:
    from juntai.sdk.fuse_api import EndpointGroup, MCPArtifactGenerator, MCPArtifactIdentity

    group = EndpointGroup("contract")

    @group.endpoint(
        "/echo",
        protocols=["mcp"],
        operation_id="contract.echo",
        mcp={"tool_id": "contract.echo", "annotations": {"readOnlyHint": True}},
    )
    def echo(message: str) -> dict[str, str]:
        return {"message": message}

    identity = MCPArtifactIdentity(
        service="contract-service",
        version="1.0.0",
        build_id="contract-build",
        source_commit="2" * 40,
        openapi_sha256="sha256:" + "3" * 64,
    )
    generated = MCPArtifactGenerator(fuse_api_version="2.0.0").generate([group], identity=identity)
    generated.write_to(tmp_path)
    checked = validate_fuseapi_descriptor(
        tmp_path / generated.descriptor_path,
        expected_digest=generated.descriptor_digest,
        expected_openapi_digest=identity.openapi_sha256,
    )
    assert set(checked["tools"]) == {"contract.echo"}
    assert checked["descriptor"]["profile"] == "juntai.fuse.profile.mcp/v1"


def test_changed_tool_signature_fails_closed(locked) -> None:
    changed = relock(locked)
    changed["resolved"]["mcp"]["descriptor"]["tools"][0]["description"] = "changed"
    changed = relock(changed)
    with pytest.raises(CapabilityError) as raised:
        validate_lock(changed)
    assert raised.value.code == "BUNDLE_INPUT_NOT_EXACT"


def test_unknown_authored_tool_fails_closed(locked) -> None:
    changed = relock(locked)
    changed["resolved"]["units"][2]["toolReferences"][0]["toolId"] = "missing.tool"
    changed = relock(changed)
    with pytest.raises(CapabilityError) as raised:
        validate_lock(changed)
    assert raised.value.code == "TOOL_REFERENCE_NOT_FOUND"


def test_descriptor_digest_is_canonical(locked) -> None:
    descriptor = locked["resolved"]["mcp"]["descriptor"]
    assert digest_json(descriptor) == locked["resolved"]["mcp"]["digest"]
    assert json.loads(json.dumps(descriptor)) == descriptor
