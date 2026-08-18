from __future__ import annotations

import json

import pytest
from conftest import relock

from juntai.documentation.errors import CapabilityError
from juntai.documentation.packager import validate_lock


def test_schema_drift_is_rejected(locked) -> None:
    changed = relock(locked)
    changed["resolved"]["schemas"][0]["digest"] = "sha256:" + "0" * 64
    changed = relock(changed)
    with pytest.raises(CapabilityError, match="schema bytes changed"):
        validate_lock(changed)


def test_hierarchy_cycle_is_rejected(locked) -> None:
    changed = relock(locked)
    changed["resolved"]["units"][0]["parentUnitId"] = "fixture.example.echo"
    changed = relock(changed)
    with pytest.raises(CapabilityError, match="cycle"):
        validate_lock(changed)


def test_unbounded_example_arguments_are_rejected(locked) -> None:
    changed = relock(locked)
    example = changed["resolved"]["units"][3]
    payload = json.loads(example["content"])
    payload["expectedToolCalls"][0]["arguments"] = {"unknown": "example"}
    example["content"] = json.dumps(payload, indent=2) + "\n"
    from juntai.documentation.canonical import sha256_bytes

    example["contentDigest"] = sha256_bytes(example["content"].encode())
    changed = relock(changed)
    with pytest.raises(CapabilityError, match="do not match"):
        validate_lock(changed)


def test_raw_credentials_are_rejected_before_packaging(locked) -> None:
    changed = relock(locked)
    unit = changed["resolved"]["units"][0]
    unit["content"] += "\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
    from juntai.documentation.canonical import sha256_bytes

    unit["contentDigest"] = sha256_bytes(unit["content"].encode())
    changed = relock(changed)
    with pytest.raises(CapabilityError) as raised:
        validate_lock(changed)
    assert raised.value.code == "PRIVACY_FILTER_REJECTED"
