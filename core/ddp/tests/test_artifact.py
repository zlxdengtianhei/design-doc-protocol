"""Tests for the SL-0 DDP artifact assembly layer.

These tests pin the SL-0 boundaries (pointer-not-copy projection + three-stream
discovery + markdown rendering + CLI assemble). The SL-3 completeness gate is
out of scope and not exercised here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ddp import artifact as ddp_artifact  # noqa: E402
from core.ddp import cli as ddp_cli  # noqa: E402
from core.ddp.artifact import (  # noqa: E402
    assemble_manifest,
    discover_streams,
    render_artifact,
    write_artifact,
)

DOMAIN = "ddp_design_doc_protocol"
SECRET_BODY = "THIS-VERBATIM-BODY-MUST-NOT-LEAK-INTO-PROJECTION-9f3a"


def _build_full_fixture(root: Path) -> dict[str, Path]:
    """Create a fixture with all three streams present."""
    req = root / "requirements" / "design" / f"{DOMAIN}.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(
        f"# Requirements — {DOMAIN}\n\n"
        f"#### {DOMAIN}-REQ-001\n{SECRET_BODY}\n\n"
        f"#### {DOMAIN}-REQ-002\nsecond requirement body\n",
        encoding="utf-8",
    )
    meaning = root / "requirements" / "meaning" / f"{DOMAIN}.md"
    meaning.parent.mkdir(parents=True, exist_ok=True)
    meaning.write_text(
        f"# Meaning — {DOMAIN}\n\nAnchors M1.0 and M2 reference the requirements.\n",
        encoding="utf-8",
    )
    design = root / "design_docs" / f"{DOMAIN}_design.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text(f"# Design — {DOMAIN}\n\nDesign stream content.\n", encoding="utf-8")
    return {"requirements": req, "meaning": meaning, "design": design}


@pytest.fixture(autouse=True)
def _isolate_receipt(monkeypatch):
    """Never touch the real tool_receipts ledger from these tests."""
    monkeypatch.setattr(ddp_artifact, "record", lambda *a, **k: {"quarantined": True}, raising=True)
    yield


def test_assemble_three_streams_present(tmp_path):
    paths = _build_full_fixture(tmp_path)
    artifact = assemble_manifest(tmp_path, DOMAIN)
    by_name = {s.name: s for s in artifact.streams}
    assert set(by_name) == {"requirements", "meaning", "design"}
    for name in ("requirements", "meaning", "design"):
        assert by_name[name].status == "present", name
        assert by_name[name].authority == paths[name]
        assert by_name[name].source_hash == ddp_artifact.sha256_file(paths[name])
    assert by_name["requirements"].req_ids == (f"{DOMAIN}-REQ-001", f"{DOMAIN}-REQ-002")
    assert by_name["meaning"].anchors == ("M1.0", "M2")


def test_missing_streams_status_and_gap_state(tmp_path):
    # empty root: no streams at all
    streams = {s.name: s for s in discover_streams(tmp_path, DOMAIN)}
    assert streams["requirements"].status == "missing"
    assert streams["design"].status == "missing"
    # meaning has no tool yet (SL-1) -> not_yet_active, never missing
    assert streams["meaning"].status == "not_yet_active"
    artifact = assemble_manifest(tmp_path, DOMAIN)
    rows = {r.stream: r for r in ddp_artifact._coverage_rows(artifact.streams)}
    assert rows["requirements"].gap_state == "unmet"
    assert rows["design"].gap_state == "unmet"
    assert rows["meaning"].gap_state == "deferred"


def test_pointer_not_copy(tmp_path):
    _build_full_fixture(tmp_path)
    artifact = assemble_manifest(tmp_path, DOMAIN)
    rendered = render_artifact(artifact)
    # The authority PATH and hash ARE projected (pointer), but the verbatim body
    # is NOT copied into the projection (AD-09 projection-not-copy).
    assert SECRET_BODY not in rendered, "verbatim authority body leaked into projection"
    assert "second requirement body" not in rendered
    req_path = tmp_path / "requirements" / "design" / f"{DOMAIN}.md"
    assert str(req_path) in rendered
    assert ddp_artifact.sha256_file(req_path) in rendered


def test_render_has_three_stream_sections_and_coverage(tmp_path):
    _build_full_fixture(tmp_path)
    artifact = assemble_manifest(tmp_path, DOMAIN)
    rendered = render_artifact(artifact)
    assert rendered.startswith("---\n")  # frontmatter
    assert "# DDP Artifact — " in rendered
    assert "## Requirements Stream" in rendered
    assert "## Meaning Stream" in rendered
    assert "## Design Stream" in rendered
    assert "## Coverage" in rendered
    assert "projection. Authority remains" in rendered


def test_write_artifact_creates_file_default_path(tmp_path):
    _build_full_fixture(tmp_path)
    artifact = assemble_manifest(tmp_path, DOMAIN)
    written = write_artifact(artifact)
    assert written == tmp_path / "DDP_ARTIFACT.md"
    assert written.exists()
    text = written.read_text(encoding="utf-8")
    assert "## Requirements Stream" in text


def test_write_artifact_explicit_output(tmp_path):
    _build_full_fixture(tmp_path)
    artifact = assemble_manifest(tmp_path, DOMAIN)
    out = tmp_path / "nested" / "custom.md"
    written = write_artifact(artifact, out)
    assert written == out
    assert out.exists()


def test_cli_assemble_smoke_creates_markdown(tmp_path):
    _build_full_fixture(tmp_path)
    out = tmp_path / "out" / "DDP_ARTIFACT.md"
    rc = ddp_cli.main(
        [
            "assemble",
            "--artifact-root",
            str(tmp_path),
            "--domain",
            DOMAIN,
            "--output",
            str(out),
            "--task-id",
            "SL-0-test",
        ]
    )
    assert rc == 0
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    for section in (
        "## Requirements Stream",
        "## Meaning Stream",
        "## Design Stream",
        "## Coverage",
    ):
        assert section in text
    assert SECRET_BODY not in text


def test_cli_assemble_rejects_missing_root(tmp_path):
    bogus = tmp_path / "does-not-exist"
    rc = ddp_cli.main(
        ["assemble", "--artifact-root", str(bogus), "--domain", DOMAIN]
    )
    assert rc == 2
