from __future__ import annotations

from pathlib import Path

from conftest import FIXTURE_MANIFEST, ROOT

from juntai.documentation.cli import run


def test_cli_resolve_validate_and_build(tmp_path: Path) -> None:
    lock = tmp_path / "capability.lock"
    output = tmp_path / "output"
    assert (
        run(["resolve", "--manifest", str(FIXTURE_MANIFEST), "--lock", str(lock)])["status"]
        == "resolved"
    )
    assert run(["validate", "--lock", str(lock)])["status"] == "valid"
    assert run(["build", "--lock", str(lock), "--out", str(output)])["status"] == "built"


def test_repository_declares_no_service_or_domain_runtime() -> None:
    assert not (ROOT / "Dockerfile").exists()
    assert not (ROOT / "docker-compose.yml").exists()
    assert not list(ROOT.glob("**/*deployment*.yaml"))
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (ROOT / "src", ROOT / "packages")
        for path in base.rglob("*")
        if path.is_file() and path.suffix in {".py", ".ts", ".js", ".json"}
    ).lower()
    for forbidden in (
        "fastapi(",
        "uvicorn.run",
        "sqlalchemy",
        "opentelemetry.exporter",
        "private_database",
        "runtime tool registry",
        "central editor",
    ):
        assert forbidden not in production
