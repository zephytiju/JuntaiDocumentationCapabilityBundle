from __future__ import annotations

from datetime import UTC, datetime

import pytest

from juntai.documentation.errors import CapabilityError
from juntai.documentation.feedback import (
    CapabilityFeedbackHook,
    EvidenceDereferencer,
    canonicalize_feedback,
    privacy_filter_feedback,
    validate_tool_outcome,
)

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64


def tool_ref():
    return {
        "toolId": "fixture.echo",
        "mcpDescriptorDigest": D2,
        "signatureSha256": D3,
        "inputSchemaDigest": D4,
    }


def pointer(*, expires_at=None, revoked=False):
    access = {
        "authorizationPolicyId": "fixture.public-read",
        "delegatedCallerRequired": True,
        "requiredScopes": ["fixture.read"],
        "allowedPurposes": ["evaluation"],
        "dataClassification": "public",
    }
    if expires_at:
        access["expiresAt"] = expires_at
    if revoked:
        access["revocation"] = {
            "authority": "fixture-authority",
            "handle": "fixture-handle",
            "statusRead": {"protocol": "mcp", "tool": tool_ref()},
        }
    return {
        "schemaVersion": "1",
        "evidenceId": "fixture-evidence",
        "ownerDomain": "shared-foundation",
        "evidenceKind": "fixture-result",
        "target": {"kind": "resource", "resourceId": "fixture-resource"},
        "read": {"protocol": "mcp", "tool": tool_ref()},
        "selectors": [{"selectorId": "recordId", "valueType": "string", "value": "record-1"}],
        "observedAt": "2026-08-18T00:00:00Z",
        "traceId": "trace-transient",
        "access": access,
    }


def outcome(*, result_digest=D4):
    return {
        "schemaVersion": "1",
        "tool": tool_ref(),
        "mcpDescriptorDigest": D2,
        "invocationId": "invocation-transient",
        "traceId": "trace-transient",
        "taskId": "evaluation-task-1",
        "correlationId": "correlation-transient",
        "observedStatus": "succeeded",
        "result": {
            "kind": "digest",
            "digest": result_digest,
            "mediaType": "application/json",
            "byteLength": 10,
        },
        "startedAt": "2026-08-18T00:00:00Z",
        "terminalAt": "2026-08-18T00:00:01Z",
        "attempt": 1,
        "returnedEvidencePointers": [pointer()],
    }


def envelope():
    return {
        "schemaVersion": "1",
        "feedbackId": "feedback-transient",
        "dedupeFingerprint": "sha256:" + "0" * 64,
        "bundleDigest": D1,
        "mcpDescriptorDigest": D2,
        "agent": {"runtime": "fixture", "frameworkVersion": "1.0.0", "modelId": "fixture-model"},
        "task": {
            "taskClass": "fixture.echo",
            "evaluationTaskId": "eval-1",
            "evaluationTaskVersion": "1",
        },
        "documents": {
            "retrievedUnitIds": ["fixture.overview"],
            "injectedUnitIds": ["fixture.overview"],
            "citedUnitIds": ["fixture.overview"],
            "inferredUsedUnitIds": ["fixture.overview"],
        },
        "toolOutcomes": [outcome()],
        "outcome": "success",
        "evidencePointers": [pointer()],
        "userCorrection": {
            "text": "Contact person@example.com; api_key=very-secret-token-value",
            "classification": "internal",
            "optedIn": True,
        },
    }


def test_privacy_filter_runs_before_stable_dedupe_and_sink_emission() -> None:
    emitted = []
    hook = CapabilityFeedbackHook(emitted.append)
    first = hook.emit(envelope())
    assert emitted == [first]
    assert "person@example.com" not in first["userCorrection"]["text"]
    assert "very-secret-token-value" not in first["userCorrection"]["text"]
    assert first["privacy"]["filtered"] is True

    transient = envelope()
    transient["feedbackId"] = "another-feedback-id"
    transient["toolOutcomes"][0]["invocationId"] = "another-invocation"
    transient["toolOutcomes"][0]["traceId"] = "another-trace"
    transient["toolOutcomes"][0]["startedAt"] = "2026-08-19T00:00:00Z"
    transient["toolOutcomes"][0]["terminalAt"] = "2026-08-19T00:00:01Z"
    transient["evidencePointers"][0]["observedAt"] = "2026-08-19T00:00:00Z"
    second = canonicalize_feedback(privacy_filter_feedback(transient))
    assert second["dedupeFingerprint"] == first["dedupeFingerprint"]

    changed = envelope()
    changed["toolOutcomes"][0]["result"]["digest"] = "sha256:" + "9" * 64
    third = canonicalize_feedback(privacy_filter_feedback(changed))
    assert third["dedupeFingerprint"] != first["dedupeFingerprint"]


def test_tool_outcome_descriptor_mismatch_is_rejected() -> None:
    changed = outcome()
    changed["mcpDescriptorDigest"] = D1
    with pytest.raises(CapabilityError) as raised:
        validate_tool_outcome(changed)
    assert raised.value.code == "TOOL_OUTCOME_DESCRIPTOR_MISMATCH"


def test_expired_evidence_never_calls_any_transport() -> None:
    calls = []
    resolver = EvidenceDereferencer(
        authorizer=lambda *_: calls.append("authorize") or True,
        public_reader=lambda *_: calls.append("read"),
        clock=lambda: datetime(2026, 8, 18, 1, tzinfo=UTC),
    )
    with pytest.raises(CapabilityError) as raised:
        resolver.dereference(
            pointer(expires_at="2026-08-18T01:00:00Z"),
            purpose="evaluation",
            delegated_caller=object(),
        )
    assert raised.value.code == "EVIDENCE_EXPIRED"
    assert calls == []


def test_revoked_evidence_never_calls_target_read() -> None:
    calls = []

    def read(operation, selectors, caller):
        calls.append((operation, selectors, caller))
        return {"status": "revoked"}

    resolver = EvidenceDereferencer(authorizer=lambda *_: True, public_reader=read)
    with pytest.raises(CapabilityError) as raised:
        resolver.dereference(pointer(revoked=True), purpose="evaluation", delegated_caller="caller")
    assert raised.value.code == "EVIDENCE_REVOKED"
    assert len(calls) == 1
    assert calls[0][0] == pointer(revoked=True)["access"]["revocation"]["statusRead"]


def test_allowed_evidence_uses_only_declared_public_operation() -> None:
    calls = []

    def read(operation, selectors, caller):
        calls.append((operation, selectors, caller))
        return {"digest": D4}

    resolver = EvidenceDereferencer(authorizer=lambda *_: True, public_reader=read)
    value = resolver.dereference(pointer(), purpose="evaluation", delegated_caller="caller")
    assert value == {"digest": D4}
    assert calls == [(pointer()["read"], pointer()["selectors"], "caller")]


def test_failure_does_not_use_cached_telemetry_or_private_database() -> None:
    class FailingReader:
        def __call__(self, *_):
            raise RuntimeError("public operation unavailable")

    resolver = EvidenceDereferencer(authorizer=lambda *_: True, public_reader=FailingReader())
    assert not hasattr(resolver, "telemetry")
    assert not hasattr(resolver, "database")
    assert not hasattr(resolver, "cache")
    with pytest.raises(CapabilityError) as raised:
        resolver.dereference(pointer(), purpose="evaluation", delegated_caller="caller")
    assert raised.value.code == "EVIDENCE_PUBLIC_READ_FAILED"
