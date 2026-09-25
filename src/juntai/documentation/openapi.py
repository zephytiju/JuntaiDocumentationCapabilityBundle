"""Exact OpenAPI 3.1 HTTP tools; no producer-specific root fields are required.

The v2 profile deliberately supports JSON bodies/responses and scalar path/query
parameters only. Authentication belongs to the host transport, never tool input.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .canonical import digest_json, sha256_bytes
from .errors import CapabilityError

MAX_OPENAPI_BYTES = 8 * 1024 * 1024
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "head", "options", "trace"})
_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,199}$")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CapabilityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise CapabilityError(f"non-finite JSON value: {value}")


def read_openapi(payload: bytes) -> dict[str, Any]:
    """Parse exact bytes without canonicalizing or assigning service identity."""
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_OPENAPI_BYTES:
        raise CapabilityError("OpenAPI payload exceeds byte limit")
    try:
        document = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CapabilityError(f"invalid OpenAPI JSON: {error}") from error
    if not isinstance(document, dict) or document.get("openapi") != "3.1.0":
        raise CapabilityError("OpenAPI tools require the explicit 3.1.0 profile")
    if not isinstance(document.get("paths"), dict):
        raise CapabilityError("OpenAPI paths must be an object")

    def check_references(value, depth=0):
        if depth > 100:
            raise CapabilityError("OpenAPI nesting limit exceeded")
        if isinstance(value, list):
            for item in value:
                check_references(item, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key == "$ref":
                    if not isinstance(item, str) or not re.fullmatch(
                        r"#/components/[A-Za-z]+/[A-Za-z0-9_.-]{1,200}", item
                    ):
                        raise CapabilityError("unsupported nonlocal OpenAPI reference")
                    _, _, category, name = item.split("/")
                    components = document.get("components", {})
                    if not isinstance(components, dict) or name not in components.get(category, {}):
                        raise CapabilityError(f"unresolved OpenAPI reference: {item}")
                elif key not in {"default", "examples", "example", "const", "enum"}:
                    check_references(item, depth + 1)

    check_references(document)
    return document


def _object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise CapabilityError(f"{label} must be an object")
    return value


def _resolve(document: dict, value: Any, category: str) -> dict:
    value = _object(value, category)
    seen = set()
    while "$ref" in value:
        reference = value["$ref"]
        prefix = f"#/components/{category}/"
        if (
            set(value) != {"$ref"}
            or not isinstance(reference, str)
            or not reference.startswith(prefix)
            or not _COMPONENT.fullmatch(reference[len(prefix) :])
            or reference in seen
        ):
            raise CapabilityError(f"unsupported or cyclic {category} reference")
        seen.add(reference)
        try:
            value = _object(document["components"][category][reference[len(prefix) :]], category)
        except KeyError as error:
            raise CapabilityError(f"unresolved {category} reference: {reference}") from error
    return value


def _schema(document: dict, root: Any) -> dict | bool:
    """Make a self-contained schema, retaining valid recursive local references."""
    definitions: dict[str, Any] = {}

    def visit(value, depth=0):
        if depth > 100:
            raise CapabilityError("schema reference or nesting limit exceeded")
        if isinstance(value, list):
            return [visit(item, depth + 1) for item in value]
        if not isinstance(value, dict):
            return value
        if set(value) & {"$id", "$anchor", "$dynamicRef", "$dynamicAnchor", "$defs"}:
            raise CapabilityError("unsupported schema reference scope")
        result = {}
        for key, item in value.items():
            if key == "$ref":
                prefix = "#/components/schemas/"
                if (
                    not isinstance(item, str)
                    or not item.startswith(prefix)
                    or not _COMPONENT.fullmatch(item[len(prefix) :])
                ):
                    raise CapabilityError("only local component schema references are supported")
                name = item[len(prefix) :]
                if name not in definitions:
                    try:
                        target = document["components"]["schemas"][name]
                    except KeyError as error:
                        raise CapabilityError(f"unresolved schema reference: {item}") from error
                    definitions[name] = None
                    definitions[name] = visit(target, depth + 1)
                result[key] = f"#/$defs/{name}"
            elif key in {"default", "examples", "example", "const", "enum"}:
                result[key] = item  # Instance data, not nested schema syntax.
            else:
                result[key] = visit(item, depth + 1)
        return result

    schema = visit(root)
    if definitions:
        schema = {**_object(schema, "schema"), "$defs": definitions}
    try:
        Draft202012Validator.check_schema(schema)
    except (SchemaError, RecursionError) as error:
        raise CapabilityError("invalid JSON schema") from error
    return schema


def _json_schema(document: dict, value: Any, category: str) -> Any:
    value = _resolve(document, value, category)
    content = _object(value.get("content"), f"{category} content")
    if set(content) != {"application/json"}:
        raise CapabilityError("exact tools support only application/json content")
    media = _object(content["application/json"], "JSON media type")
    if "schema" not in media or "encoding" in media:
        raise CapabilityError("JSON content needs a schema without custom encoding")
    return media["schema"]


def _closed(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required),
        "additionalProperties": False,
    }


def _scalar(schema: dict | bool) -> bool:
    if not isinstance(schema, dict):
        return False
    if isinstance(schema.get("type"), str) and schema["type"] in {
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    }:
        return True
    return bool(schema.get("anyOf")) and all(_scalar(s) for s in schema["anyOf"])


def _input(document: dict, path: str, item: dict, operation: dict) -> dict:
    parameters = {}
    for source in (item.get("parameters", []), operation.get("parameters", [])):
        if not isinstance(source, list):
            raise CapabilityError("parameters must be an array")
        local = set()
        for raw in source:
            parameter = _resolve(document, raw, "parameters")
            name, location = parameter.get("name"), parameter.get("in")
            if not isinstance(name, str) or not _NAME.fullmatch(name):
                raise CapabilityError("unsupported parameter name")
            identity = (location, name)
            if identity in local or location not in {"path", "query"}:
                raise CapabilityError("duplicate or unsupported parameter location")
            local.add(identity)
            if set(parameter) & {"content", "allowReserved", "allowEmptyValue"}:
                raise CapabilityError("unsupported parameter serialization")
            style = "simple" if location == "path" else "form"
            if parameter.get("style", style) != style:
                raise CapabilityError("unsupported parameter style")
            schema = _schema(document, parameter.get("schema"))
            if not _scalar(schema):
                raise CapabilityError("path/query parameters must have scalar schemas")
            if location == "path" and parameter.get("required") is not True:
                raise CapabilityError("path parameters must be required")
            parameters[identity] = parameter
    path_names = set(re.findall(r"\{([A-Za-z][A-Za-z0-9_.-]*)\}", path))
    if any(c in re.sub(r"\{[A-Za-z][A-Za-z0-9_.-]*\}", "", path) for c in "{}"):
        raise CapabilityError("unsupported route template")
    if path_names != {name for location, name in parameters if location == "path"}:
        raise CapabilityError("route and path parameters differ")
    properties, required = {}, ["pathParameters"]
    for location, key in (("path", "pathParameters"), ("query", "query")):
        selected = {name: p for (where, name), p in parameters.items() if where == location}
        if selected or location == "path":
            needed = [name for name, p in selected.items() if p.get("required") is True]
            properties[key] = _closed({name: p["schema"] for name, p in selected.items()}, needed)
            if location == "query" and needed:
                required.append(key)
    if "requestBody" in operation:
        body = _resolve(document, operation["requestBody"], "requestBodies")
        properties["body"] = _json_schema(document, body, "requestBodies")
        if body.get("required") is True:
            required.append("body")
    return _schema(document, _closed(properties, required))


def compile_openapi_tools(
    payload: bytes, *, service_id: str, selections: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Derive exact HTTP references and schemas from original released bytes.

    Callers bind ``service_id`` and selections to a verified bundle pin. This pure
    function does not claim to authenticate source provenance or policy contents.
    """
    document = read_openapi(payload)
    if not isinstance(service_id, str) or not _NAME.fullmatch(service_id):
        raise CapabilityError("invalid service identity")
    operations = {}
    for path, item in document["paths"].items():
        if not isinstance(path, str) or not path.startswith("/") or "?" in path or "#" in path:
            raise CapabilityError("unsupported OpenAPI route")
        item = _object(item, "path item")
        if "$ref" in item:
            raise CapabilityError("path item references are unsupported")
        for method in HTTP_METHODS & item.keys():
            operation = _object(item[method], "operation")
            identity = operation.get("operationId")
            if (
                not isinstance(identity, str)
                or not _NAME.fullmatch(identity)
                or identity in operations
            ):
                raise CapabilityError("missing, invalid or duplicate operationId")
            operations[identity] = (method, path, item, operation)
    result, seen = [], set()
    for selection in selections:
        if set(selection) != {"operationId", "approvalPolicyUnitId", "idempotency"}:
            raise CapabilityError("operation selection has missing or unknown fields")
        identity = selection["operationId"]
        if not isinstance(identity, str) or identity in seen or identity not in operations:
            raise CapabilityError("duplicate or unavailable selected operation")
        seen.add(identity)
        method, path, item, operation = operations[identity]
        approval, idempotency = selection["approvalPolicyUnitId"], selection["idempotency"]
        if approval is not None and (
            not isinstance(approval, str) or not _NAME.fullmatch(approval)
        ):
            raise CapabilityError("invalid approval policy reference")
        if method == "get":
            if idempotency != "read":
                raise CapabilityError("GET tools require read idempotency")
        elif not approval or idempotency not in {"keyed", "none"}:
            raise CapabilityError("mutation tools require approval and explicit idempotency")
        if method not in {"get", "post", "put", "patch", "delete"} or operation.get("callbacks"):
            raise CapabilityError("unsupported HTTP operation shape")
        input_schema = _input(document, path, item, operation)
        responses = _object(operation.get("responses"), "responses")
        success = [response for code, response in responses.items() if re.fullmatch(r"2\d\d", code)]
        if len(success) != 1:
            raise CapabilityError("tools require one unambiguous successful JSON response")
        output_schema = _schema(document, _json_schema(document, success[0], "responses"))
        reference = {
            "protocol": "openapi",
            "serviceId": service_id,
            "operationId": identity,
            "method": method.upper(),
            "path": path,
            "openapiDigest": sha256_bytes(payload),
            "inputSchemaDigest": digest_json(input_schema),
            "outputSchemaDigest": digest_json(output_schema),
            "approvalPolicyUnitId": approval,
            "idempotency": idempotency,
        }
        result.append(
            {"reference": reference, "inputSchema": input_schema, "outputSchema": output_schema}
        )
    if not result:
        raise CapabilityError("OpenAPI tools require a nonempty operation selection")
    return sorted(result, key=lambda tool: tool["reference"]["operationId"])
