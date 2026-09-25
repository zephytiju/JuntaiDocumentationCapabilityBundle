"""Offline adapter failure tests; real storage is covered separately."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_meridian_publication import MemoryArtifacts
from test_openapi import LATTICE, metadata

from juntai.documentation.errors import CapabilityError
from juntai.documentation.meridian import exact_reference
from juntai.documentation.openapi_bundle import (
    build_openapi_bundle,
    load_openapi_bundle_meridian,
    publish_openapi_bundle_meridian,
    validate_openapi_bindings,
)


def publish(store):
    return publish_openapi_bundle_meridian(
        build_openapi_bundle(LATTICE.read_bytes(), metadata=metadata()),
        resource_store=store,
        namespace="test",
        kind="capability",
        name="lattice",
        actor="test",
    )


def test_published_pin_roundtrip_and_no_legacy_substitution():
    store = SimpleNamespace(artifacts=MemoryArtifacts())
    pin = publish(store)["pin"]
    loaded = load_openapi_bundle_meridian(resource_store=store, pin=pin)
    assert len(loaded["tools"]) == 4
    with pytest.raises(CapabilityError):
        exact_reference(pin["coordinate"])
    for field in [
        "serviceId",
        "producerBuildId",
        "sourceDigest",
        "manifestDigest",
        "openapiDigest",
    ]:
        tampered = deepcopy(pin)
        tampered[field] = "sha256:" + "0" * 64 if field.endswith("Digest") else "other"
        with pytest.raises(CapabilityError):
            load_openapi_bundle_meridian(resource_store=store, pin=tampered)


@pytest.mark.parametrize("failure", ["partial", "corrupt"])
def test_failed_commit_or_readback_returns_no_pin(failure):
    store = SimpleNamespace(artifacts=MemoryArtifacts())
    setattr(store.artifacts, failure, True)
    with pytest.raises(CapabilityError):
        publish(store)


@pytest.mark.parametrize(
    "mutation",
    ["service", "source", "schema", "approval", "added", "version", "bytes", "pin", "ceiling"],
)
def test_consumer_binding_rejects_substitution(mutation):
    store = SimpleNamespace(artifacts=MemoryArtifacts())
    pin = publish(store)["pin"]
    loaded = load_openapi_bundle_meridian(resource_store=store, pin=pin)
    capability = {
        "contractVersion": "v2",
        "bundlePins": [pin],
        "descriptorPins": [
            {"protocol": "openapi", "serviceId": "lattice", "digest": pin["openapiDigest"]}
        ],
        "openapiBindings": [loaded["openapiBinding"]],
        "exactTools": loaded["tools"],
        "maximumToolBoundary": [],
    }
    descriptors = {pin["openapiDigest"]: LATTICE.read_bytes()}
    assert len(validate_openapi_bindings(capability, descriptors)) == 4
    manifest = capability["openapiBindings"][0]["manifest"]
    if mutation == "service":
        capability["descriptorPins"][0]["serviceId"] = "another"
    elif mutation == "source":
        manifest["source"]["sourceCommit"] = "b" * 40
    elif mutation == "schema":
        capability["exactTools"][0]["inputSchemaDigest"] = "sha256:" + "0" * 64
    elif mutation == "approval":
        manifest["selections"][-1]["approvalPolicyUnitId"] = None
    elif mutation == "added":
        capability["exactTools"].append(deepcopy(capability["exactTools"][0]))
    elif mutation == "version":
        capability["contractVersion"] = "v1"
    elif mutation == "bytes":
        descriptors[pin["openapiDigest"]] += b"\n"
    elif mutation == "pin":
        pin["coordinate"]["digest"] = "sha256:" + "0" * 64
    else:
        capability["maximumToolBoundary"] = [
            {
                "protocol": "openapi",
                "serviceId": "lattice",
                "operationId": "deleteEverything",
                "openapiDigest": pin["openapiDigest"],
            }
        ]
    with pytest.raises(CapabilityError):
        validate_openapi_bindings(capability, descriptors)
