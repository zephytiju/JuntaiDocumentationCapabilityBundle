"""Required CI acceptance through released Meridian and real PostgreSQL/S3."""

import os
import uuid

import pytest

if not os.environ.get("DOCUMENTATION_REAL_STORAGE"):
    pytest.skip("run in the required real-storage CI job", allow_module_level=True)

from meridian_fixture import compose
from meridian_storage import OperationContext
from meridian_storage.plugins.config_artifact import IdentityConflict, ResourceStore

from juntai.documentation import load_capability_set_meridian, publish_bundle_meridian
from juntai.documentation.meridian import exact_reference


def test_committed_publication_idempotency_and_fresh_runtime_read(built):
    schema = "documentation_" + uuid.uuid4().hex[:12]
    context = OperationContext(
        "documentation-fixture",
        tenant="fixture",
        scope={"tenant": "fixture", "application": "documentation"},
    )
    runtime = compose(schema_namespace=schema)
    try:
        with runtime.context(context):
            store = ResourceStore(runtime)
            first = publish_bundle_meridian(
                built.output, resource_store=store, actor="build/fixture"
            )
            assert (
                publish_bundle_meridian(built.output, resource_store=store, actor="build/fixture")
                == first
            )
            identity = exact_reference(first["bundle"]).identity
            with pytest.raises(IdentityConflict):
                store.artifacts.publish(
                    **identity.to_dict(), payload=b"conflict", actor="build/fixture"
                )
    finally:
        runtime.close()

    runtime = compose(schema_namespace=schema)
    try:
        with runtime.context(context):
            pin = first["pin"]
            loaded = load_capability_set_meridian(
                resource_store=ResourceStore(runtime),
                pin=pin,
                runtime_build_id=pin["producerBuildId"],
                runtime_openapi_digest=pin["openapiDigest"],
                runtime_mcp_descriptor_digest=pin["mcpDescriptorDigest"],
            )
            assert loaded["pin"] == pin
            assert {tool["toolId"] for tool in loaded["tools"]} == {"fixture.echo"}
    finally:
        runtime.close()


def test_released_lattice_openapi_publication_and_fresh_runtime_read():
    from test_openapi import LATTICE, metadata

    from juntai.documentation.openapi_bundle import (
        build_openapi_bundle,
        load_openapi_bundle_meridian,
        publish_openapi_bundle_meridian,
        validate_openapi_bindings,
    )

    schema = "openapi_" + uuid.uuid4().hex[:12]
    context = OperationContext(
        "openapi-fixture",
        tenant="fixture",
        scope={"tenant": "fixture", "application": "documentation"},
    )
    runtime = compose(schema_namespace=schema)
    try:
        with runtime.context(context):
            publication = publish_openapi_bundle_meridian(
                build_openapi_bundle(LATTICE.read_bytes(), metadata=metadata()),
                resource_store=ResourceStore(runtime),
                namespace="lattice",
                kind="capability",
                name="ontology",
                actor="build/fixture",
            )
    finally:
        runtime.close()
    runtime = compose(schema_namespace=schema)
    try:
        with runtime.context(context):
            pin = publication["pin"]
            loaded = load_openapi_bundle_meridian(resource_store=ResourceStore(runtime), pin=pin)
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
            assert (
                len(
                    validate_openapi_bindings(
                        capability, {pin["openapiDigest"]: LATTICE.read_bytes()}
                    )
                )
                == 4
            )
    finally:
        runtime.close()
