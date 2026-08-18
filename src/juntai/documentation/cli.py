"""`juntai-capability` command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes
from .catalog import compile_catalog, select_capability
from .errors import CapabilityError
from .loader import load_capability_set
from .packager import build_bundle, load_lock, resolve_manifest, validate_lock


def _read_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CapabilityError(f"{path} must contain a JSON object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="juntai-capability",
        description="Deterministic service-free documentation capability bundle tooling",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    resolve = commands.add_parser(
        "resolve", help="freeze exact producer inputs into a content lock"
    )
    resolve.add_argument("--manifest", required=True)
    resolve.add_argument("--lock", required=True)

    validate = commands.add_parser("validate", help="validate a content lock offline")
    validate.add_argument("--lock", required=True)

    build = commands.add_parser("build", help="build deterministic projections and archives")
    build.add_argument("--lock", required=True)
    build.add_argument("--out", required=True)

    verify = commands.add_parser(
        "verify", help="verify an exact local build against a published pin"
    )
    verify.add_argument("--bundle", required=True, help="local build output directory")
    verify.add_argument("--pin", required=True, help="pin or publication-result JSON")
    verify.add_argument("--runtime-build-id")
    verify.add_argument("--openapi-digest")
    verify.add_argument("--mcp-descriptor-digest")

    catalog = commands.add_parser("catalog", help="compile or select from a static catalog")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    compile_command = catalog_commands.add_parser("compile")
    compile_command.add_argument("--records", required=True)
    compile_command.add_argument("--out", required=True)
    compile_command.add_argument(
        "--signature",
        required=True,
        help="JSON signature object; signedDigest is bound to the compiled index",
    )
    select_command = catalog_commands.add_parser("select")
    select_command.add_argument("--index", required=True)
    select_command.add_argument("--request", required=True)
    return parser


def run(arguments: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(arguments)
    if args.command == "resolve":
        lock = resolve_manifest(args.manifest, lock_path=args.lock)
        return {"status": "resolved", "lock": str(Path(args.lock)), "digest": lock["lockDigest"]}
    if args.command == "validate":
        lock = validate_lock(load_lock(args.lock))
        return {"status": "valid", "lockDigest": lock["lockDigest"]}
    if args.command == "build":
        result = build_bundle(args.lock, out=args.out)
        return {
            "status": "built",
            "output": str(result.output),
            "buildResultDigest": result.manifest["buildResultDigest"],
            "artifacts": result.manifest["artifacts"],
        }
    if args.command == "verify":
        value = _read_object(args.pin)
        pin = value.get("pin", value)
        loaded = load_capability_set(
            args.bundle,
            pin=pin,
            runtime_build_id=args.runtime_build_id or pin["producerBuildId"],
            runtime_openapi_digest=args.openapi_digest or pin["openapiDigest"],
            runtime_mcp_descriptor_digest=(
                args.mcp_descriptor_digest or pin["mcpDescriptorDigest"]
            ),
        )
        return {"status": "verified", "units": len(loaded["units"]), "tools": len(loaded["tools"])}
    if args.command == "catalog" and args.catalog_command == "compile":
        index = compile_catalog(args.records, out=args.out, signature=_read_object(args.signature))
        return {"status": "compiled", "indexDigest": index["indexDigest"]}
    if args.command == "catalog" and args.catalog_command == "select":
        return select_capability(_read_object(args.index), _read_object(args.request))
    raise AssertionError("unreachable command")


def main(arguments: list[str] | None = None) -> int:
    try:
        result = run(arguments)
    except (CapabilityError, OSError, KeyError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "CLI_ERROR")
        sys.stderr.buffer.write(
            canonical_json_bytes({"ok": False, "error": {"code": code, "message": str(error)}})
        )
        return 2
    sys.stdout.buffer.write(canonical_json_bytes({"ok": True, "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
