from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from juntai.documentation.canonical import canonical_json_bytes
from juntai.documentation.packager import build_bundle


def test_clean_builds_are_byte_identical(tmp_path: Path, locked) -> None:
    first = build_bundle(locked, out=tmp_path / "first")
    second = build_bundle(locked, out=tmp_path / "second")
    first_files = {path.name: path.read_bytes() for path in first.output.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second.output.iterdir()}
    assert first_files == second_files

    for name in ("capability-bundle.tar", "agent-capability-bundle.tar", "documentation-human.tar"):
        with tarfile.open(fileobj=io.BytesIO(first_files[name]), mode="r:") as archive:
            assert archive.getnames() == sorted(archive.getnames())
            for member in archive.getmembers():
                assert (member.mtime, member.uid, member.gid, member.mode) == (0, 0, 0, 0o644)


def test_one_source_projects_to_human_and_agent(built) -> None:
    graph_units = {unit["unitId"] for unit in built.graph["units"]}
    human_units = {page["unitId"] for page in built.human_projection["pages"]}
    agent_units = {
        unit_id for resource in built.mcp_projection["resources"] for unit_id in resource["unitIds"]
    }
    assert graph_units == human_units == agent_units
    assert all(prompt["userInvoked"] is True for prompt in built.mcp_projection["prompts"])
    assert {
        tool["toolId"] for prompt in built.mcp_projection["prompts"] for tool in prompt["toolRefs"]
    } == {"fixture.echo"}


def test_offline_human_archive_is_safe_and_accessible(built) -> None:
    payload = (built.output / "documentation-human.tar").read_bytes()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        page = archive.extractfile("pages/fixture.overview.html")
        assert page is not None
        html = page.read().decode("utf-8")
    assert 'aria-label="Documentation"' in html
    assert "Exact references" in html
    assert "<script" not in html
    assert built.graph["contracts"]["mcpDescriptorDigest"] in html


def test_build_result_records_every_immutable_artifact(built) -> None:
    disk = json.loads((built.output / "build-result.json").read_text(encoding="utf-8"))
    assert disk == built.manifest
    assert canonical_json_bytes(disk) == (built.output / "build-result.json").read_bytes()
    assert set(disk["artifacts"]) == {
        "agent-capability-bundle.tar",
        "capability-bundle.tar",
        "documentation-human.tar",
        "documentation-mcp.json",
        "provenance.json",
    }
