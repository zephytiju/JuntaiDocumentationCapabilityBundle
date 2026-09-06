"""Exercise released OpenAPI/MCP exporters through an installed bundle consumer."""

from __future__ import annotations

import argparse
import json
import shutil
from importlib.metadata import version
from pathlib import Path

import yaml
from juntai.sdk.fuse_api import (
    EndpointGroup,
    MCPArtifactGenerator,
    MCPArtifactIdentity,
    OpenAPIArtifactGenerator,
    ServiceArtifactIdentity,
)

from juntai.documentation.canonical import canonical_json_bytes, digest_json, sha256_bytes
from juntai.documentation.cli import run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[1] / "fixtures/valid/minimal/documentation"
    producer = args.out / "producer"
    shutil.copytree(source, producer)
    group = EndpointGroup("fixture")

    @group.endpoint(
        "/echo",
        method="GET",
        protocols=["http", "mcp"],
        operation_id="fixture.echo",
        mcp={"tool_id": "fixture.echo", "annotations": {"readOnlyHint": True}},
    )
    def echo(message: str) -> dict[str, str]:
        return {"message": message}

    openapi = OpenAPIArtifactGenerator().generate(
        [group],
        identity=ServiceArtifactIdentity(
            service="fixture-service", version="1.0.0", source_commit="1" * 40
        ),
        title="Generic capability fixture",
    )
    mcp = MCPArtifactGenerator().generate(
        [group],
        identity=MCPArtifactIdentity(
            service="fixture-service",
            version="1.0.0",
            build_id="fixture-build-1",
            source_commit="1" * 40,
            openapi_sha256=openapi.digest,
        ),
    )
    installed_version = version("juntai-fuse-api")
    assert installed_version in ("2.0.0", "2.1.0")
    assert openapi.manifest["fuseApiVersion"] == installed_version
    assert mcp.manifest["fuseApiVersion"] == installed_version
    openapi.write_to(producer)
    mcp.write_to(producer)
    descriptor = json.loads(mcp.files[mcp.descriptor_path])
    tool = descriptor["tools"][0]
    assert tool["toolId"] == "fixture.echo"
    openapi_document = json.loads(openapi.files[openapi.openapi_path])
    assert openapi_document["paths"]["/echo"]["get"]["operationId"] == tool["operationId"]

    manifest_path = producer / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["contracts"]["openapi"] = {"path": openapi.openapi_path, "digest": openapi.digest}
    manifest["contracts"]["mcp"] = {
        "path": mcp.descriptor_path,
        "digest": mcp.descriptor_digest,
        "descriptorDigest": mcp.descriptor_digest,
    }
    for unit in manifest["sources"]["units"]:
        for reference in unit.get("toolReferences", []):
            reference.update(
                mcpDescriptorDigest=mcp.descriptor_digest,
                signatureSha256=tool["signatureSha256"],
                inputSchemaDigest=digest_json(tool["inputSchema"]),
            )
            if tool["outputSchema"] is not None:
                reference["outputSchemaDigest"] = digest_json(tool["outputSchema"])
            else:
                reference.pop("outputSchemaDigest", None)
    manifest["provenance"]["approvalEvidenceRef"]["read"]["openapiDigest"] = openapi.digest
    manifest["provenance"]["packagerVersion"] = version("juntai-documentation-capability")
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    lock_path = args.out / "capability.lock"
    assert (
        run(["resolve", "--manifest", str(manifest_path), "--lock", str(lock_path)])["status"]
        == "resolved"
    )
    assert run(["validate", "--lock", str(lock_path)])["status"] == "valid"
    for name in ("first", "second"):
        assert (
            run(["build", "--lock", str(lock_path), "--out", str(args.out / name)])["status"]
            == "built"
        )
    first = {p.name: p.read_bytes() for p in (args.out / "first").iterdir()}
    second = {p.name: p.read_bytes() for p in (args.out / "second").iterdir()}
    assert first == second
    locked = json.loads(lock_path.read_bytes())
    assert (
        canonical_json_bytes(locked["resolved"]["mcp"]["descriptor"])
        == mcp.files[mcp.descriptor_path].encode()
    )
    assert (
        locked["resolved"]["openapi"]["raw"].encode()
        == openapi.files[openapi.openapi_path].encode()
    )
    report = {
        "schemaVersion": "capability.juntai.io/fuseapi-consumer-evidence/v1",
        "packageVersion": version("juntai-documentation-capability"),
        "fuseApiVersion": installed_version,
        "openapiDigest": openapi.digest,
        "mcpDescriptorDigest": mcp.descriptor_digest,
        "toolIds": [item["toolId"] for item in descriptor["tools"]],
        "toolSignatures": {tool["toolId"]: tool["signatureSha256"]},
        "lockDigest": locked["lockDigest"],
        "exporterBytesPreserved": True,
        "byteIdenticalRebuild": True,
        "artifacts": {name: sha256_bytes(payload) for name, payload in sorted(first.items())},
    }
    (args.out / "consumer-evidence.json").write_bytes(canonical_json_bytes(report))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
