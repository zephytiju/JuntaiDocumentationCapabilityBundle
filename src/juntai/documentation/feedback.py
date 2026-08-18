"""Advisory feedback hooks and fail-closed public evidence dereference."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from .canonical import digest_json
from .errors import CapabilityError
from .schema_validation import validate_schema

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SECRET = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._~+/=-]{12,}|(?:password|client_secret|api_key)\s*[:=]\s*\S+)"
)


class FeedbackSink(Protocol):
    def __call__(self, envelope: Mapping[str, Any]) -> object: ...


class PublicEvidenceReader(Protocol):
    def __call__(
        self,
        read: Mapping[str, Any],
        selectors: list[Mapping[str, Any]],
        delegated_caller: object,
    ) -> object: ...


class EvidenceAuthorizer(Protocol):
    def __call__(
        self,
        pointer: Mapping[str, Any],
        purpose: str,
        delegated_caller: object,
    ) -> bool: ...


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CapabilityError("timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise CapabilityError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def validate_evidence_pointer(pointer: Mapping[str, Any]) -> None:
    validate_schema("evidence-pointer", pointer)
    seen: set[str] = set()
    for selector in pointer["selectors"]:
        selector_id = selector["selectorId"]
        if selector_id in seen:
            raise CapabilityError("evidence selector identities must be unique")
        seen.add(selector_id)
        value_type = selector["valueType"]
        value = selector["value"]
        valid = {
            "string": isinstance(value, str),
            "timestamp": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
        }[value_type]
        if not valid:
            raise CapabilityError("evidence selector value does not match valueType")
        if value_type == "timestamp":
            _instant(value)
    window = pointer.get("consistencyWindow")
    if window and _instant(window["fromInclusive"]) >= _instant(window["toExclusive"]):
        raise CapabilityError("evidence consistency window is empty")


def validate_tool_outcome(outcome: Mapping[str, Any]) -> None:
    validate_schema("tool-outcome", outcome)
    if outcome["mcpDescriptorDigest"] != outcome["tool"]["mcpDescriptorDigest"]:
        raise CapabilityError(
            "ToolOutcome descriptor differs from its exact tool",
            code="TOOL_OUTCOME_DESCRIPTOR_MISMATCH",
        )
    if _instant(outcome["terminalAt"]) < _instant(outcome["startedAt"]):
        raise CapabilityError("ToolOutcome terminalAt precedes startedAt")
    if outcome["observedStatus"] not in {"succeeded", "cancelled"} and "stableError" not in outcome:
        raise CapabilityError("non-success ToolOutcome requires an observed stable error")
    for pointer in outcome["returnedEvidencePointers"]:
        validate_evidence_pointer(pointer)


def privacy_filter_feedback(
    envelope: Mapping[str, Any],
    *,
    policy_version: str = "juntai.documentation.privacy/v1",
) -> dict[str, Any]:
    """Redact opt-in correction text before validation, hashing or emission."""

    filtered = deepcopy(dict(envelope))
    removed: list[str] = []
    correction = filtered.get("userCorrection")
    if correction is not None:
        if correction.get("optedIn") is not True:
            filtered.pop("userCorrection", None)
            removed.append("userCorrection")
        else:
            text = correction.get("text", "")
            redacted = _EMAIL.sub("[redacted-email]", text)
            redacted = _SECRET.sub("[redacted-secret]", redacted)
            if redacted != text:
                correction["text"] = redacted
                removed.append("userCorrection.text:protected-token")
            if correction.get("classification") not in {"public", "internal"}:
                filtered.pop("userCorrection", None)
                removed.append("userCorrection:classification")
    encoded = json.dumps(filtered, ensure_ascii=False)
    if _SECRET.search(encoded):
        raise CapabilityError(
            "feedback contains a prohibited raw credential", code="PRIVACY_FILTER_REJECTED"
        )
    filtered["privacy"] = {
        "filtered": bool(removed),
        "removedFields": sorted(removed),
        "policyVersion": policy_version,
    }
    return filtered


def _stable_evidence(pointer: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidenceId": pointer["evidenceId"],
        "ownerDomain": pointer["ownerDomain"],
        "evidenceKind": pointer["evidenceKind"],
        "target": pointer["target"],
        "read": pointer["read"],
        "selectors": sorted(pointer["selectors"], key=lambda item: item["selectorId"]),
        "applicationScope": pointer.get("applicationScope"),
        "access": {
            "authorizationPolicyId": pointer["access"]["authorizationPolicyId"],
            "delegatedCallerRequired": True,
            "requiredScopes": sorted(pointer["access"]["requiredScopes"]),
            "allowedPurposes": sorted(pointer["access"]["allowedPurposes"]),
            "dataClassification": pointer["access"]["dataClassification"],
            "revocation": pointer["access"].get("revocation"),
        },
    }


def _stable_outcome(outcome: Mapping[str, Any]) -> dict[str, Any]:
    result = outcome.get("result")
    return {
        "tool": outcome["tool"],
        "mcpDescriptorDigest": outcome["mcpDescriptorDigest"],
        "taskId": outcome["taskId"],
        "observedStatus": outcome["observedStatus"],
        "stableError": outcome.get("stableError"),
        "result": (
            _stable_evidence(result["evidence"])
            if result and result["kind"] == "authorized-reference"
            else result
        ),
        "attempt": outcome["attempt"],
        "idempotency": outcome.get("idempotency"),
        "returnedEvidencePointers": sorted(
            (_stable_evidence(item) for item in outcome["returnedEvidencePointers"]),
            key=lambda item: digest_json(item),
        ),
    }


def canonicalize_feedback(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the shared stable fingerprint after privacy filtering."""

    value = deepcopy(dict(envelope))
    if "privacy" not in value:
        raise CapabilityError("privacy filtering must precede feedback canonicalization")
    for pointer in value.get("evidencePointers", []):
        validate_evidence_pointer(pointer)
    for outcome in value.get("toolOutcomes", []):
        validate_tool_outcome(outcome)
    stable = {
        "schemaVersion": value.get("schemaVersion"),
        "bundleDigest": value.get("bundleDigest"),
        "mcpDescriptorDigest": value.get("mcpDescriptorDigest"),
        "agent": value.get("agent"),
        "task": value.get("task"),
        "outcome": value.get("outcome"),
        "failureCode": value.get("failureCode"),
        "evidencePointers": sorted(
            (_stable_evidence(item) for item in value.get("evidencePointers", [])),
            key=lambda item: digest_json(item),
        ),
        "toolOutcomes": sorted(
            (_stable_outcome(item) for item in value.get("toolOutcomes", [])),
            key=lambda item: digest_json(item),
        ),
    }
    value["dedupeFingerprint"] = digest_json(stable)
    validate_schema("feedback", value)
    return value


class EvidenceDereferencer:
    """Calls only the pointer's declared public operation after every gate."""

    def __init__(
        self,
        *,
        authorizer: EvidenceAuthorizer,
        public_reader: PublicEvidenceReader,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._authorizer = authorizer
        self._public_reader = public_reader
        self._clock = clock or (lambda: datetime.now(UTC))

    def dereference(
        self,
        pointer: Mapping[str, Any],
        *,
        purpose: str,
        delegated_caller: object,
    ) -> object:
        validate_evidence_pointer(pointer)
        if delegated_caller is None:
            raise CapabilityError(
                "delegated caller is required", code="EVIDENCE_DEREFERENCE_FORBIDDEN"
            )
        access = pointer["access"]
        if purpose not in access["allowedPurposes"]:
            raise CapabilityError(
                "evidence purpose is not allowed", code="EVIDENCE_DEREFERENCE_FORBIDDEN"
            )
        expires_at = access.get("expiresAt")
        if expires_at is not None and self._clock().astimezone(UTC) >= _instant(expires_at):
            raise CapabilityError("evidence reference expired", code="EVIDENCE_EXPIRED")
        if not self._authorizer(pointer, purpose, delegated_caller):
            raise CapabilityError(
                "evidence authorization denied", code="EVIDENCE_DEREFERENCE_FORBIDDEN"
            )
        revocation = access.get("revocation")
        if revocation is not None:
            selectors = [
                {
                    "selectorId": "authority",
                    "valueType": "string",
                    "value": revocation["authority"],
                },
                {"selectorId": "handle", "valueType": "string", "value": revocation["handle"]},
            ]
            try:
                status = self._public_reader(revocation["statusRead"], selectors, delegated_caller)
            except Exception as error:
                raise CapabilityError(
                    "revocation public read failed", code="EVIDENCE_REVOKED"
                ) from error
            if not isinstance(status, Mapping) or status.get("status") != "active":
                raise CapabilityError("evidence reference is revoked", code="EVIDENCE_REVOKED")
        try:
            return self._public_reader(
                pointer["read"], list(pointer["selectors"]), delegated_caller
            )
        except CapabilityError:
            raise
        except Exception as error:
            raise CapabilityError(
                "declared public evidence read failed", code="EVIDENCE_PUBLIC_READ_FAILED"
            ) from error


class CapabilityFeedbackHook:
    """Privacy-filter and emit advisory envelopes to an injected sink."""

    def __init__(self, sink: FeedbackSink) -> None:
        self._sink = sink

    def emit(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        filtered = privacy_filter_feedback(envelope)
        canonical = canonicalize_feedback(filtered)
        self._sink(canonical)
        return canonical
