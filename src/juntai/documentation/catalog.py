"""Immutable static catalog compilation and pure fail-closed selection."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .canonical import canonical_json_bytes, digest_json
from .errors import CapabilityError
from .schema_validation import validate_schema

CatalogSignatureVerifier = Callable[[bytes, Mapping[str, Any]], bool]


def _read_records(source: str | Path | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(source, (str, Path)):
        return [dict(item) for item in source]
    path = Path(source)
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    records: list[dict[str, Any]] = []
    for file in files:
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CapabilityError(f"cannot read catalog record {file}: {error}") from error
        if isinstance(value, list):
            records.extend(value)
        else:
            records.append(value)
    return records


def compile_catalog(
    records: str | Path | Iterable[Mapping[str, Any]],
    *,
    out: str | Path | None = None,
    signature: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    values = _read_records(records)
    values.sort(
        key=lambda item: (
            item["ownerKey"],
            item["pin"]["coordinate"]["bundleId"],
            item["pin"]["coordinate"]["version"],
            item["pin"]["coordinate"]["digest"],
        )
    )
    identities: set[tuple[str, str, str, str]] = set()
    for value in values:
        coordinate = value["pin"]["coordinate"]
        identity = (
            value["ownerKey"],
            coordinate["bundleId"],
            coordinate["version"],
            coordinate["digest"],
        )
        if identity in identities:
            raise CapabilityError("catalog contains a duplicate immutable publication record")
        identities.add(identity)
        if value["ownerKey"] != coordinate["ownerKey"]:
            raise CapabilityError("catalog owner differs from bundle coordinate")
        if value["lifecycle"] == "revoked" and "revokedAt" not in value:
            raise CapabilityError("revoked catalog entry requires revokedAt")
        if value["lifecycle"] == "deprecated" and "deprecatedAt" not in value:
            raise CapabilityError("deprecated catalog entry requires deprecatedAt")
    core = {"schemaVersion": "1", "records": values}
    index_digest = digest_json(core)
    if signature is None:
        raise CapabilityError("catalog compilation requires an external signature")
    bound_signature = dict(signature)
    bound_signature.setdefault("signedDigest", index_digest)
    if bound_signature["signedDigest"] != index_digest:
        raise CapabilityError("catalog signature is bound to a different index digest")
    index: dict[str, Any] = {
        **core,
        "indexDigest": index_digest,
        "signature": bound_signature,
    }
    validate_schema("catalog-index", index)
    if out is not None:
        destination = Path(out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(canonical_json_bytes(index))
    return index


def verify_catalog_signature(index: Mapping[str, Any], verifier: CatalogSignatureVerifier) -> None:
    """Verify catalog integrity and an externally managed signature.

    The verifier owns key lookup, trust policy and the signature algorithm. It
    receives the canonical UTF-8 bytes of the bound ``sha256:...`` digest and
    the complete signature object. This library never owns a central key or
    catalog service.
    """

    validate_schema("catalog-index", index)
    core = {"schemaVersion": index["schemaVersion"], "records": index["records"]}
    digest = digest_json(core)
    if digest != index["indexDigest"]:
        raise CapabilityError("catalog index digest mismatch")
    signature = index["signature"]
    if signature["signedDigest"] != digest:
        raise CapabilityError("catalog signature digest mismatch")
    if not verifier(digest.encode("ascii"), signature):
        raise CapabilityError("catalog signature is not trusted")


def _platform_matches(specifier: str, version: str) -> bool:
    normalized = ",".join(specifier.split())
    try:
        return Version(version) in SpecifierSet(normalized)
    except (InvalidSpecifier, InvalidVersion) as error:
        raise CapabilityError(f"invalid platform compatibility constraint: {error}") from error


def select_capability(index: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    """Select one exact pin from an already signature-verified immutable catalog."""

    validate_schema("catalog-index", index)
    core = {"schemaVersion": index["schemaVersion"], "records": index["records"]}
    if digest_json(core) != index["indexDigest"]:
        raise CapabilityError("catalog index digest mismatch")
    if index["signature"]["signedDigest"] != index["indexDigest"]:
        raise CapabilityError("catalog signature digest mismatch")
    candidates: list[Mapping[str, Any]] = []
    for record in index["records"]:
        if record["lifecycle"] == "revoked":
            continue
        pin = record["pin"]
        coordinate = pin["coordinate"]
        exact_filters = {
            "ownerKey": record["ownerKey"],
            "bundleId": coordinate["bundleId"],
            "version": coordinate["version"],
            "digest": coordinate["digest"],
            "producerBuildId": pin["producerBuildId"],
            "mcpDescriptorDigest": pin["mcpDescriptorDigest"],
            "openapiDigest": pin["openapiDigest"],
        }
        if any(
            request.get(key) is not None and request[key] != value
            for key, value in exact_filters.items()
        ):
            continue
        if request.get("locale") is not None and request["locale"] not in record["locales"]:
            continue
        if (
            request.get("taskClass") is not None
            and request["taskClass"] not in record["taskClasses"]
        ):
            continue
        platform_version = request.get("platformVersion")
        if platform_version is None or not _platform_matches(
            record["compatibility"]["platform"], platform_version
        ):
            continue
        candidates.append(record)
    if not candidates:
        return {"status": "unavailable", "reason": "BUNDLE_INCOMPATIBLE"}
    if len(candidates) != 1:
        return {"status": "unavailable", "reason": "SELECTION_AMBIGUOUS"}
    return {"status": "selected", "pin": candidates[0]["pin"]}
