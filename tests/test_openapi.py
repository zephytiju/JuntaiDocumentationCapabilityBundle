"""Actual released Lattice bytes; offline schema tests are not live acceptance."""

from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from juntai.documentation.canonical import canonical_json_bytes, sha256_bytes
from juntai.documentation.errors import CapabilityError
from juntai.documentation.openapi import compile_openapi_tools, read_openapi
from juntai.documentation.openapi_bundle import build_openapi_bundle, inspect_openapi_bundle

LATTICE = Path(__file__).parent / "fixtures/lattice-0.7.0/openapi.json"
OPERATIONS = ["getBundle", "listDefinitions", "getDefinition", "patchDefinition"]


def selections():
    return [
        {
            "operationId": operation,
            "approvalPolicyUnitId": "review" if operation == "patchDefinition" else None,
            "idempotency": "keyed" if operation == "patchDefinition" else "read",
        }
        for operation in OPERATIONS
    ]


def metadata():
    return {
        "ownerKey": "lattice",
        "bundleId": "ontology",
        "version": "1.0.0",
        "producerBuildId": "lattice-0.7.0",
        "serviceId": "lattice",
        "source": {
            "repository": "https://github.com/zephytiju/LatticeModelConfigurationService",
            "sourceCommit": "a" * 40,  # Offline provenance fixture, not attestation.
            "artifactDigest": (
                "sha256:f328e5c0f08f65b37391be73df5e1e8f8eb68bcf7b1336920c8a82acbd1cd702"
            ),
            "artifactPath": "lattice_model_configuration/openapi/lattice-ontology.v1.json",
        },
        "units": [
            {"unitId": "review", "kind": "policy", "content": "Review exact write arguments."}
        ],
        "selections": selections(),
    }


def compile_document(document=None, selected=None):
    payload = LATTICE.read_bytes() if document is None else canonical_json_bytes(document)
    return compile_openapi_tools(payload, service_id="lattice", selections=selected or selections())


def test_released_bytes_compile_four_operations_and_real_envelopes():
    raw = LATTICE.read_bytes()
    assert raw != canonical_json_bytes(read_openapi(raw))
    tools = {t["reference"]["operationId"]: t for t in compile_document()}
    assert set(tools) == set(OPERATIONS)
    assert {t["reference"]["openapiDigest"] for t in tools.values()} == {sha256_bytes(raw)}
    schema = tools["listDefinitions"]["inputSchema"]
    validator = Draft202012Validator(schema)
    validator.validate({"pathParameters": {"bundle_id": "sample"}, "query": {"revision": 1}})
    for invalid in [
        {"pathParameters": {"bundle_id": "sample"}},
        {"pathParameters": {"bundle_id": "sample"}, "query": {"revision": 0}},
        {"pathParameters": {"bundle_id": "sample"}, "query": {"revision": 1}, "token": "x"},
    ]:
        assert not validator.is_valid(invalid)
    write = tools["patchDefinition"]
    assert write["reference"]["method"] == "PATCH"
    assert write["reference"]["approvalPolicyUnitId"] == "review"
    assert "body" in write["inputSchema"]["required"]
    assert "$defs" in write["inputSchema"]


@pytest.mark.parametrize(
    "mutation", ["duplicate", "remote", "missing", "array", "header", "response", "path", "version"]
)
def test_reject_ambiguous_or_unsupported_contracts(mutation):
    document = read_openapi(LATTICE.read_bytes())
    op = document["paths"]["/v1/bundles/{bundle_id}"]["get"]
    if mutation == "duplicate":
        document["paths"]["/other"] = {"get": deepcopy(op)}
    elif mutation in {"remote", "missing"}:
        op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] = (
            "https://example.invalid/schema"
            if mutation == "remote"
            else "#/components/schemas/Missing"
        )
    elif mutation == "array":
        op["parameters"][1]["schema"] = {"type": "array", "items": {"type": "string"}}
    elif mutation == "header":
        op["parameters"][1]["in"] = "header"
    elif mutation == "response":
        op["responses"]["201"] = deepcopy(op["responses"]["200"])
    elif mutation == "path":
        op["parameters"][0]["name"] = "different"
    else:
        document["openapi"] = "3.0.3"
    with pytest.raises(CapabilityError):
        compile_document(document)


def test_recursive_schema_is_local_and_validated():
    document = read_openapi(LATTICE.read_bytes())
    document["components"]["schemas"]["BundleView"] = {
        "type": "object",
        "properties": {"child": {"$ref": "#/components/schemas/BundleView"}},
        "additionalProperties": False,
    }
    tool = next(
        t for t in compile_document(document) if t["reference"]["operationId"] == "getBundle"
    )
    validator = Draft202012Validator(tool["outputSchema"])
    validator.validate({"child": {"child": {}}})
    assert not validator.is_valid({"child": {"bad": True}})


@pytest.mark.parametrize(
    "payload", [b'{"openapi":"3.1.0","openapi":"3.1.0","paths":{}}', b'{"x":NaN}', b"[]"]
)
def test_strict_json(payload):
    with pytest.raises(CapabilityError):
        read_openapi(payload)


def test_mutation_requires_approval_and_bundle_policy():
    selected = selections()
    selected[-1]["approvalPolicyUnitId"] = None
    with pytest.raises(CapabilityError, match="approval"):
        compile_document(selected=selected)
    meta = metadata()
    meta["units"][0]["kind"] = "document"
    with pytest.raises(CapabilityError, match="approval policy"):
        build_openapi_bundle(LATTICE.read_bytes(), metadata=meta)


def test_bundle_keeps_original_bytes_and_binds_source():
    raw = LATTICE.read_bytes()
    archive = build_openapi_bundle(raw, metadata=metadata())
    manifest, original = inspect_openapi_bundle(archive)
    assert original == raw
    assert manifest["openapiDigest"] == sha256_bytes(raw)
    assert archive == build_openapi_bundle(raw, metadata=metadata())
    changed = metadata()
    changed["source"]["sourceCommit"] = "b" * 40
    assert archive != build_openapi_bundle(raw, metadata=changed)
    with pytest.raises(CapabilityError):
        inspect_openapi_bundle(archive + b"unbound trailing bytes")
