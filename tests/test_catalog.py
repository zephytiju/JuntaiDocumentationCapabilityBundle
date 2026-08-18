from __future__ import annotations

from copy import deepcopy

import pytest
from test_publication_loader import FakeArtifactClient

from juntai.documentation.catalog import (
    compile_catalog,
    select_capability,
    verify_catalog_signature,
)
from juntai.documentation.errors import CapabilityError
from juntai.documentation.publication import publish_bundle


def _signature():
    return {"algorithm": "fixture-v1", "keyId": "fixture-key", "value": "fixture-signature"}


def _record(pin):
    return {
        "title": "Generic fixture",
        "summary": "Immutable generic capability fixture.",
        "ownerKey": pin["coordinate"]["ownerKey"],
        "visibility": "public",
        "lifecycle": "release",
        "locales": ["en"],
        "taskClasses": ["fixture.echo"],
        "compatibility": {"platform": ">=4.0 <5.0"},
        "routeKey": "platform.documentation",
        "pin": pin,
    }


def test_catalog_compilation_and_exact_selection(built) -> None:
    pin = publish_bundle(built.output, artifact_client=FakeArtifactClient())["pin"]
    index = compile_catalog([_record(pin)], signature=_signature())
    verify_catalog_signature(
        index,
        lambda payload, signature: (
            payload.decode("ascii") == signature["signedDigest"]
            and signature["value"] == "fixture-signature"
        ),
    )
    selected = select_capability(
        index,
        {
            "ownerKey": "shared-foundation",
            "mcpDescriptorDigest": pin["mcpDescriptorDigest"],
            "platformVersion": "4.1.0",
            "taskClass": "fixture.echo",
            "locale": "en",
        },
    )
    assert selected == {"status": "selected", "pin": pin}
    assert select_capability(index, {"platformVersion": "5.0.0"})["reason"] == "BUNDLE_INCOMPATIBLE"


def test_revoked_versions_are_not_selected(built) -> None:
    pin = publish_bundle(built.output, artifact_client=FakeArtifactClient())["pin"]
    record = _record(pin)
    record["lifecycle"] = "revoked"
    record["revokedAt"] = "2026-08-18T01:00:00Z"
    index = compile_catalog([record], signature=_signature())
    assert select_capability(index, {"platformVersion": "4.1.0"}) == {
        "status": "unavailable",
        "reason": "BUNDLE_INCOMPATIBLE",
    }


def test_ambiguous_selection_fails_closed(built) -> None:
    pin = publish_bundle(built.output, artifact_client=FakeArtifactClient())["pin"]
    second = deepcopy(pin)
    second["coordinate"]["version"] = "1.0.1"
    second["coordinate"]["digest"] = "sha256:" + "e" * 64
    second["coordinate"]["artifactRef"]["manifest_digest"] = "sha256:" + "e" * 64
    index = compile_catalog([_record(pin), _record(second)], signature=_signature())
    assert select_capability(index, {"platformVersion": "4.1.0"})["reason"] == "SELECTION_AMBIGUOUS"


def test_catalog_signature_binding_and_trust_fail_closed(built) -> None:
    pin = publish_bundle(built.output, artifact_client=FakeArtifactClient())["pin"]
    index = compile_catalog([_record(pin)], signature=_signature())
    tampered = deepcopy(index)
    tampered["records"][0]["summary"] = "tampered"
    with pytest.raises(CapabilityError, match="digest mismatch"):
        verify_catalog_signature(tampered, lambda _payload, _signature: True)
    with pytest.raises(CapabilityError, match="not trusted"):
        verify_catalog_signature(index, lambda _payload, _signature: False)


def test_deprecation_replacement_and_rollback_exact_pin(built) -> None:
    pin = publish_bundle(built.output, artifact_client=FakeArtifactClient())["pin"]
    replacement = deepcopy(pin)
    replacement["coordinate"]["version"] = "1.0.1"
    replacement["coordinate"]["digest"] = "sha256:" + "d" * 64
    replacement["coordinate"]["artifactRef"]["manifest_digest"] = "sha256:" + "d" * 64
    old = _record(pin)
    old["lifecycle"] = "deprecated"
    old["deprecatedAt"] = "2026-08-18T01:00:00Z"
    old["replacement"] = replacement
    index = compile_catalog([old, _record(replacement)], signature=_signature())
    rollback = select_capability(
        index,
        {
            "platformVersion": "4.1.0",
            "version": pin["coordinate"]["version"],
            "digest": pin["coordinate"]["digest"],
        },
    )
    assert rollback == {"status": "selected", "pin": pin}
