"""Adapter contract tests; the test double is not deployment acceptance evidence."""

from __future__ import annotations

import io
import sys
import tarfile
from copy import deepcopy
from types import SimpleNamespace

import pytest

if sys.version_info < (3, 12):
    pytest.skip("Meridian requires Python 3.12+", allow_module_level=True)

from meridian_storage.plugins.config_artifact import ResourceIdentity, StoredResourceRef

from juntai.documentation import load_capability_set, load_capability_set_meridian
from juntai.documentation.canonical import sha256_bytes
from juntai.documentation.errors import CapabilityError
from juntai.documentation.meridian import publish_bundle_meridian
from juntai.documentation.publication import application_documentation_link


class MemoryArtifacts:
    def __init__(self):
        self.records = {}
        self.payloads = {}
        self.partial = False
        self.corrupt = False
        self.reads = 0

    def publish(self, **kwargs):
        identity = ResourceIdentity(
            **{key: kwargs[key] for key in ("namespace", "kind", "name", "version")}
        )
        ref = StoredResourceRef(
            identity.resource_id,
            **identity.to_dict(),
            profile="artifact",
            digest=sha256_bytes(kwargs["payload"]),
        )
        assert kwargs["expected_digest"] == ref.digest
        assert kwargs["expected_length"] == len(kwargs["payload"])
        resource = SimpleNamespace(
            ref=ref,
            state="PUBLISHED",
            media_type=kwargs["media_type_value"],
            byte_length=len(kwargs["payload"]),
        )
        self.records[identity] = resource
        self.payloads[identity] = kwargs["payload"]
        return SimpleNamespace(
            ref=ref, resource=resource, object_committed=True, metadata_committed=not self.partial
        )

    def exact(self, identity):
        return SimpleNamespace(resource=self.records[identity])

    def read(self, resolved):
        self.reads += 1
        return b"corrupt" if self.corrupt else self.payloads[resolved.resource.ref.identity]


def runtime(pin):
    return dict(
        runtime_build_id=pin["producerBuildId"],
        runtime_openapi_digest=pin["openapiDigest"],
        runtime_mcp_descriptor_digest=pin["mcpDescriptorDigest"],
    )


def publish(built):
    store = SimpleNamespace(artifacts=MemoryArtifacts())
    result = publish_bundle_meridian(built.output, resource_store=store, actor="build/fixture")
    return store, result


def test_exact_publication_load_and_association(built):
    store, result = publish(built)
    assert store.artifacts.reads == 4
    assert len(store.artifacts.records) == 4
    pin = result["pin"]
    assert "manifest_digest" not in pin["coordinate"]["artifactRef"]
    loaded = load_capability_set_meridian(resource_store=store, pin=pin, **runtime(pin))
    assert loaded == load_capability_set(built.output, pin=pin, **runtime(pin))
    assert {tool["toolId"] for tool in loaded["tools"]} == {"fixture.echo"}
    assert (
        application_documentation_link(
            result,
            contribution_key="fixture.docs",
            route_key="fixture.docs",
            unit_id="fixture.overview",
        )["pin"]
        == pin
    )
    again = publish_bundle_meridian(built.output, resource_store=store, actor="build/fixture")
    assert again == result


@pytest.mark.parametrize("failure", ["partial", "corrupt"])
def test_no_result_on_failed_commit_or_readback(built, tmp_path, failure):
    artifacts = MemoryArtifacts()
    setattr(artifacts, failure, True)
    destination = tmp_path / "publication.json"
    with pytest.raises(CapabilityError):
        publish_bundle_meridian(
            built.output,
            resource_store=SimpleNamespace(artifacts=artifacts),
            actor="build/fixture",
            result_path=destination,
        )
    assert not destination.exists()


@pytest.mark.parametrize("field", ["resourceId", "profile", "digest", "version", "extra"])
def test_reference_tampering_rejected(built, field):
    store, result = publish(built)
    pin = deepcopy(result["pin"])
    pin["coordinate"]["artifactRef"]["resource"][field] = "wrong"
    with pytest.raises(CapabilityError, match="invalid exact Meridian reference"):
        load_capability_set_meridian(resource_store=store, pin=pin, **runtime(pin))


@pytest.mark.parametrize(
    "filename", ["content-graph.json", "mcp-projection.json", "documentation-human.tar"]
)
def test_directory_mutation_rejected(built, filename):
    _, result = publish(built)
    path = built.output / filename
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(CapabilityError):
        load_capability_set(built.output, pin=result["pin"], **runtime(result["pin"]))


@pytest.mark.parametrize("failure", ["draft", "media", "length", "corrupt", "runtime", "lineage"])
def test_read_rejects_invalid_state_and_lineage(built, failure):
    store, result = publish(built)
    pin = result["pin"]
    resource = next(iter(store.artifacts.records.values()))
    kwargs = runtime(pin)
    if failure == "draft":
        resource.state = "DRAFT"
    elif failure == "media":
        resource.media_type = "application/json"
    elif failure == "length":
        resource.byte_length += 1
    elif failure == "corrupt":
        store.artifacts.corrupt = True
    elif failure == "runtime":
        kwargs["runtime_build_id"] = "other"
    else:
        pin["producerBuildId"] = "other"
        kwargs = runtime(pin)
    with pytest.raises(CapabilityError):
        load_capability_set_meridian(resource_store=store, pin=pin, **kwargs)


@pytest.mark.parametrize("failure", ["traversal", "symlink", "duplicate", "missing"])
def test_unsafe_archive_rejected_even_with_valid_payload_digest(built, failure):
    store, result = publish(built)
    identity = next(iter(store.artifacts.records))
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        name = "../escape" if failure == "traversal" else "build-result.json"
        member = tarfile.TarInfo(name)
        if failure == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/escape"
        archive.addfile(member, io.BytesIO(b""))
        if failure == "duplicate":
            archive.addfile(member, io.BytesIO(b""))
    payload = stream.getvalue()
    digest = sha256_bytes(payload)
    ref = StoredResourceRef(
        identity.resource_id, **identity.to_dict(), profile="artifact", digest=digest
    )
    resource = store.artifacts.records[identity]
    resource.ref, resource.byte_length = ref, len(payload)
    store.artifacts.payloads[identity] = payload
    pin = result["pin"]
    coordinate = pin["coordinate"]
    coordinate["digest"] = coordinate["artifactRef"]["digest"] = digest
    coordinate["artifactRef"]["resource"] = ref.to_dict()
    with pytest.raises(CapabilityError, match="archive"):
        load_capability_set_meridian(resource_store=store, pin=pin, **runtime(pin))
