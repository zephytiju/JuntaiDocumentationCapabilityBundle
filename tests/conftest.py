from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from juntai.documentation.canonical import digest_json
from juntai.documentation.packager import build_bundle, resolve_manifest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_MANIFEST = ROOT / "fixtures/valid/minimal/documentation/manifest.yaml"


@pytest.fixture
def locked() -> dict[str, Any]:
    return resolve_manifest(FIXTURE_MANIFEST)


@pytest.fixture
def built(tmp_path: Path, locked: dict[str, Any]):
    return build_bundle(locked, out=tmp_path / "build")


def relock(value: dict[str, Any]) -> dict[str, Any]:
    changed = deepcopy(value)
    core = {key: item for key, item in changed.items() if key != "lockDigest"}
    changed["lockDigest"] = digest_json(core)
    return changed


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
