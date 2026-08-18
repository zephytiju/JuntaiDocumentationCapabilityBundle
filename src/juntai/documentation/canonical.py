"""Canonical serialization and deterministic archive helpers."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: object, *, newline: bool = True) -> bytes:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def digest_json(value: object, *, newline: bool = True) -> str:
    return sha256_bytes(canonical_json_bytes(value, newline=newline))


def normalized_text_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def checked_relative_file(root: Path, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith(("/", "~")):
        raise ValueError("source path must be a non-empty relative path")
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate == root or root not in candidate.parents or not candidate.is_file():
        raise ValueError(f"source path is missing or escapes its root: {relative_path}")
    return candidate


def deterministic_tar(files: Mapping[str, bytes]) -> bytes:
    """Return a POSIX tar with stable order, metadata, modes and bytes."""

    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(files.items()):
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"archive path is unsafe: {name}")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            info.pax_headers = {}
            archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def deep_sort(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: deep_sort(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [deep_sort(item) for item in value]
    return value
