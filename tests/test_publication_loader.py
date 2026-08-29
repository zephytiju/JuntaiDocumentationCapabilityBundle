from __future__ import annotations

from types import SimpleNamespace

import pytest

from juntai.documentation.errors import CapabilityError
from juntai.documentation.loader import (
    create_derived_projection,
    load_capability_set,
    verify_derived_projection,
)
from juntai.documentation.publication import application_documentation_link, publish_bundle


class FakeArtifactClient:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, **kwargs):
        self.calls.append(kwargs)
        manifest_digest = "sha256:" + f"{len(self.calls):064x}"
        return SimpleNamespace(
            reference={
                "artifact_id": f"artifact-{len(self.calls)}",
                "version_id": f"version-{len(self.calls)}",
                "manifest_digest": manifest_digest,
                "version": kwargs["version"],
                "name": kwargs["name"],
                "kind": kwargs["kind"],
            }
        )


def test_artifact_sdk_publication_precedes_association_and_loading(built) -> None:
    client = FakeArtifactClient()
    result = publish_bundle(built.output, artifact_client=client)
    assert len(client.calls) == 4
    assert [len(call["layers"]) for call in client.calls] == [2, 1, 1, 1]
    assert all(isinstance(layer.data, bytes) for call in client.calls for layer in call["layers"])
    assert all("registry" not in call and "oci" not in call for call in client.calls)

    link = application_documentation_link(
        result,
        contribution_key="generic.agent-capability",
        route_key="generic.documentation",
        unit_id="fixture.overview",
    )
    assert link["pin"] == result["pin"]
    assert link["unitId"] == "fixture.overview"
    loaded = load_capability_set(
        built.output,
        pin=result["pin"],
        runtime_build_id=built.manifest["producerBuildId"],
        runtime_openapi_digest=built.manifest["openapiDigest"],
        runtime_mcp_descriptor_digest=built.manifest["mcpDescriptorDigest"],
    )
    assert {tool["toolId"] for tool in loaded["tools"]} == {"fixture.echo"}
    derived = create_derived_projection(
        loaded,
        adapter_id="fixture-adapter",
        adapter_version="1.0.0",
        kind="instruction-file",
        files={"instructions.md": b"derived read-only fixture\n"},
    )
    verify_derived_projection(derived, loaded)


def test_runtime_descriptor_mismatch_is_rejected(built) -> None:
    result = publish_bundle(built.output, artifact_client=FakeArtifactClient())
    with pytest.raises(CapabilityError, match="runtime mcpDescriptorDigest"):
        load_capability_set(
            built.output,
            pin=result["pin"],
            runtime_build_id=built.manifest["producerBuildId"],
            runtime_openapi_digest=built.manifest["openapiDigest"],
            runtime_mcp_descriptor_digest="sha256:" + "f" * 64,
        )


def test_unpublished_planned_coordinate_cannot_be_associated() -> None:
    with pytest.raises(CapabilityError, match="publish-before-associate"):
        application_documentation_link(
            {"coordinate": "planned"},
            contribution_key="generic.agent-capability",
            route_key="generic.documentation",
            unit_id="fixture.overview",
        )


def test_application_association_requires_stable_unit_id(built) -> None:
    result = publish_bundle(built.output, artifact_client=FakeArtifactClient())
    with pytest.raises(CapabilityError, match="stable unitId"):
        application_documentation_link(
            result,
            contribution_key="generic.agent-capability",
            route_key="generic.documentation",
            unit_id="../active payload",
        )
