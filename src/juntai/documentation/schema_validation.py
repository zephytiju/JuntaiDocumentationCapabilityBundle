"""Packaged JSON Schema loading and strict instance validation."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .errors import CapabilityError

SCHEMAS = {
    "manifest": "manifest/v1.schema.json",
    "content-graph": "content-graph/v1.schema.json",
    "catalog-index": "catalog-index/v1.schema.json",
    "feedback": "feedback/v1.schema.json",
    "evidence-pointer": "evidence-pointer/v1.schema.json",
    "tool-outcome": "tool-outcome/v1.schema.json",
}


def load_schema(name: str) -> dict[str, Any]:
    try:
        relative = SCHEMAS[name]
    except KeyError as error:
        raise KeyError(f"unknown schema {name!r}") from error
    path = resources.files("juntai.documentation").joinpath("schemas", relative)
    if not path.is_file():
        path = Path(__file__).resolve().parents[3] / "schemas" / relative
    return json.loads(path.read_text(encoding="utf-8"))


def _registry() -> Registry:
    registry = Registry()
    for schema_name in SCHEMAS:
        schema = load_schema(schema_name)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def validate_schema(name: str, instance: object) -> None:
    validator = Draft202012Validator(
        load_schema(name), format_checker=FormatChecker(), registry=_registry()
    )
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    if not errors:
        return
    first = errors[0]
    location = "/".join(str(part) for part in first.absolute_path) or "$"
    raise CapabilityError(
        f"{name} schema violation at {location}: {first.message}",
        code=f"{name.upper().replace('-', '_')}_INVALID",
    )
