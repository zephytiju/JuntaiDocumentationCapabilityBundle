from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

import pytest
from conftest import ROOT, relock

from juntai.documentation.canonical import digest_json
from juntai.documentation.descriptor import (
    validate_exact_tool_reference,
    validate_fuseapi_descriptor,
    validate_fuseapi_descriptor_document,
)
from juntai.documentation.errors import CapabilityError
from juntai.documentation.packager import validate_lock


@pytest.fixture
def exported(tmp_path: Path):
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
    generated = MCPArtifactGenerator().generate([group], identity=identity)
    assert generated.manifest["fuseApiVersion"] == version("juntai-fuse-api")
    generated.write_to(tmp_path)
    return generated, identity, tmp_path / generated.descriptor_path


def test_exact_installed_fuseapi_generator_contract_is_consumed(exported) -> None:
    generated, identity, path = exported
    checked = validate_fuseapi_descriptor(
        path,
        expected_digest=generated.descriptor_digest,
        expected_openapi_digest=identity.openapi_sha256,
    )
    assert set(checked["tools"]) == {"contract.echo"}
    assert checked["descriptor"]["profile"] == "juntai.fuse.profile.mcp/v1"
    assert checked["descriptor"]["fuseApiVersion"] == version("juntai-fuse-api")


@pytest.mark.parametrize(
    "unsupported", ["1.0.0", "2.0.1", "2.1.1", "2.2.0", "3.0.0", "latest", None, ["2.1.0"]]
)
def test_unsupported_exporter_versions_fail_even_with_matching_digest(exported, unsupported):
    _, identity, path = exported
    descriptor = json.loads(path.read_bytes())
    descriptor["fuseApiVersion"] = unsupported
    with pytest.raises(CapabilityError) as error:
        validate_fuseapi_descriptor_document(
            descriptor,
            expected_digest=digest_json(descriptor),
            expected_openapi_digest=identity.openapi_sha256,
        )
    assert error.value.code == "BUNDLE_INCOMPATIBLE"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schemaVersion", "juntai.fuse/mcp-descriptor/v2", "BUNDLE_INCOMPATIBLE"),
        ("profile", "unapproved.mcp/v1", "BUNDLE_INCOMPATIBLE"),
        ("compatibility", {"descriptorMajor": 2, "mcpProfileMajor": 1}, "BUNDLE_INCOMPATIBLE"),
        ("openapiSha256", "sha256:" + "0" * 64, "BUNDLE_INPUT_NOT_EXACT"),
        ("endpointCatalogSha256", "sha256:" + "0" * 64, "BUNDLE_INPUT_NOT_EXACT"),
        ("sourceCommit", "main", "BUNDLE_INPUT_NOT_EXACT"),
    ],
)
def test_mismatched_descriptor_contract_fails_with_matching_digest(exported, field, value, code):
    _, identity, path = exported
    descriptor = json.loads(path.read_bytes())
    descriptor[field] = value
    with pytest.raises(CapabilityError) as error:
        validate_fuseapi_descriptor_document(
            descriptor,
            expected_digest=digest_json(descriptor),
            expected_openapi_digest=identity.openapi_sha256,
        )
    assert error.value.code == code


@pytest.mark.parametrize("schema", ["inputSchema", "outputSchema"])
def test_changed_schema_rejected_after_catalog_digest_is_recomputed(exported, schema):
    _, identity, path = exported
    descriptor = json.loads(path.read_bytes())
    descriptor["tools"][0][schema] = {"type": "integer"}
    descriptor["endpointCatalogSha256"] = digest_json(descriptor["tools"])
    with pytest.raises(CapabilityError) as error:
        validate_fuseapi_descriptor_document(
            descriptor,
            expected_digest=digest_json(descriptor),
            expected_openapi_digest=identity.openapi_sha256,
        )
    assert error.value.code == "TOOL_SIGNATURE_MISMATCH"


@pytest.mark.parametrize(
    "field", ["mcpDescriptorDigest", "signatureSha256", "inputSchemaDigest", "outputSchemaDigest"]
)
def test_authored_reference_drift_rejected_against_real_exporter(exported, field):
    generated, identity, path = exported
    checked = validate_fuseapi_descriptor(
        path,
        expected_digest=generated.descriptor_digest,
        expected_openapi_digest=identity.openapi_sha256,
    )
    reference = deepcopy(checked["tools"]["contract.echo"])
    reference[field] = "sha256:" + "0" * 64
    with pytest.raises(CapabilityError) as error:
        validate_exact_tool_reference(
            reference, descriptor_digest=generated.descriptor_digest, tools=checked["tools"]
        )
    assert error.value.code == "TOOL_SIGNATURE_MISMATCH"


@pytest.mark.parametrize("tools", [[None], [{"toolId": 1}, {"toolId": "valid"}]])
def test_malformed_tool_catalog_fails_deterministically(exported, tools):
    _, identity, path = exported
    descriptor = json.loads(path.read_bytes())
    descriptor["tools"] = tools
    descriptor["endpointCatalogSha256"] = digest_json(tools)
    with pytest.raises(CapabilityError):
        validate_fuseapi_descriptor_document(
            descriptor,
            expected_digest=digest_json(descriptor),
            expected_openapi_digest=identity.openapi_sha256,
        )


def test_duplicate_tool_rejected_with_recomputed_catalog_digest(exported):
    _, identity, path = exported
    descriptor = json.loads(path.read_bytes())
    descriptor["tools"].append(deepcopy(descriptor["tools"][0]))
    descriptor["endpointCatalogSha256"] = digest_json(descriptor["tools"])
    with pytest.raises(CapabilityError) as error:
        validate_fuseapi_descriptor_document(
            descriptor,
            expected_digest=digest_json(descriptor),
            expected_openapi_digest=identity.openapi_sha256,
        )
    assert error.value.code == "TOOL_SIGNATURE_MISMATCH"


@pytest.mark.parametrize("mutation", ["extra-field", "missing-field", "noncanonical", "wrong-pin"])
def test_exact_descriptor_shape_and_bytes_cannot_drift(exported, mutation):
    generated, identity, path = exported
    descriptor = json.loads(path.read_bytes())
    expected_digest = generated.descriptor_digest
    if mutation in ("extra-field", "missing-field"):
        if mutation == "extra-field":
            descriptor["unrecognized"] = True
        else:
            del descriptor["serviceVersion"]
        from juntai.documentation.canonical import canonical_json_bytes

        path.write_bytes(canonical_json_bytes(descriptor))
        expected_digest = digest_json(descriptor)
    elif mutation == "noncanonical":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        expected_digest = "sha256:" + "0" * 64
    with pytest.raises(CapabilityError) as error:
        validate_fuseapi_descriptor(
            path,
            expected_digest=expected_digest,
            expected_openapi_digest=identity.openapi_sha256,
        )
    assert error.value.code == "BUNDLE_INPUT_NOT_EXACT"


def test_real_openapi_mcp_consumer_builds_identical_bundles(tmp_path):
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify_fuseapi_consumer.py"),
            "--out",
            str(tmp_path / "consumer"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads((tmp_path / "consumer/consumer-evidence.json").read_bytes())
    assert report["fuseApiVersion"] == version("juntai-fuse-api")
    assert report["exporterBytesPreserved"] is True
    assert report["byteIdenticalRebuild"] is True


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
