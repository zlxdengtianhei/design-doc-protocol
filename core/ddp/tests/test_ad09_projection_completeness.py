"""Narrow tests for the AD-09 projection-completeness fix (T1262 / F26).

assemble_manifest used to stamp completeness_verdict=UNKNOWN unconditionally, so a
DDP artifact never signaled whether its own projection was complete. These tests
pin the new behavior: the verdict is COMPUTED from the stream pointers, with
explicit reasons when the projection is incomplete.
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
    compute_projection_completeness,
    render_artifact,
)
from core.ddp.schema import StreamPointer  # noqa: E402

DOMAIN = "ddp_design_doc_protocol"


def _pointer(name: str, status: str, *, source_hash: str = "abc123") -> StreamPointer:
    return StreamPointer(
        name=name,  # type: ignore[arg-type]
        authority=Path(f"/tmp/fake-{name}.md") if status == "present" else None,
        status=status,  # type: ignore[arg-type]
        source_hash=source_hash if status == "present" else "",
    )


def _build_cli_pass_fixture(root: Path) -> None:
    req = root / "requirements" / "design" / f"{DOMAIN}.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(
        f"# Requirements - {DOMAIN}\n\n"
        f"#### {DOMAIN}-REQ-001\n"
        "Projection completeness must be reachable from the CLI.\n\n"
        "provenance: source=prompt.md:L1 requirement_class=design task_id=T1385\n",
        encoding="utf-8",
    )
    meaning = root / "requirements" / "meaning" / f"{DOMAIN}.md"
    meaning.parent.mkdir(parents=True, exist_ok=True)
    meaning.write_text("# Meaning\n\nM1.0 anchors the requirement.\n", encoding="utf-8")
    design = root / "design_docs" / f"{DOMAIN}_design.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text(
        f"""# DDP Design

## (0) Requirement Anchor

req-doc: `{req}`

## Layer 1 功能设计

### (core_need)

Expose computed DDP projection completeness through the production CLI.

### (success_effect)

Default assemble writes PASS for complete projections, and pipeline restamps the artifact with the gate verdict.

### (hard_requirements)

Requirements and design streams are present, hashed, and pointer-only.

### (negative_requirements)

Do not stamp UNKNOWN by default when stream evidence is complete.

### (deliverable)

A CLI path that writes the computed or gate verdict into DDP_ARTIFACT.md.

## Layer 2 实现设计

### 2.3 关键设计决策（含为什么）

| 决策 | 选择 | 理由 | 不选什么 |
|---|---|---|---|
| default verdict | compute from stream pointers | makes AD-09 reachable from CLI | silent UNKNOWN |

## Final Boundary

| 字段 | 值 |
|---|---|
| 状态 | DONE |
""",
        encoding="utf-8",
    )


def test_compute_completeness_all_present_passes() -> None:
    streams = (
        _pointer("requirements", "present"),
        _pointer("meaning", "present"),
        _pointer("design", "present"),
    )
    verdict, reasons = compute_projection_completeness(streams)
    assert verdict == "PASS"
    assert reasons == ()


def test_compute_completeness_missing_design_flagged_with_reason() -> None:
    streams = (
        _pointer("requirements", "present"),
        _pointer("meaning", "present"),
        _pointer("design", "missing"),
    )
    verdict, reasons = compute_projection_completeness(streams)
    assert verdict == "FLAG"
    assert any("design" in r and "not present" in r for r in reasons)


def test_compute_completeness_present_without_hash_flagged() -> None:
    streams = (
        _pointer("requirements", "present", source_hash=""),
        _pointer("meaning", "present"),
        _pointer("design", "present"),
    )
    verdict, reasons = compute_projection_completeness(streams)
    assert verdict == "FLAG"
    assert any("requirements" in r and "source_hash" in r for r in reasons)


def test_compute_completeness_meaning_not_yet_active_is_acceptable() -> None:
    streams = (
        _pointer("requirements", "present"),
        _pointer("meaning", "not_yet_active"),
        _pointer("design", "present"),
    )
    verdict, reasons = compute_projection_completeness(streams)
    assert verdict == "PASS"
    assert reasons == ()


def test_compute_completeness_meaning_missing_flagged() -> None:
    streams = (
        _pointer("requirements", "present"),
        _pointer("meaning", "missing"),
        _pointer("design", "present"),
    )
    verdict, reasons = compute_projection_completeness(streams)
    assert verdict == "FLAG"
    assert any(r.startswith("meaning") for r in reasons)


def test_assemble_manifest_computes_verdict_by_default(tmp_path: Path) -> None:
    # Build a real projection root with all three streams present.
    (tmp_path / "requirements" / "design").mkdir(parents=True)
    (tmp_path / "requirements" / "meaning").mkdir(parents=True)
    (tmp_path / "design_docs").mkdir(parents=True)
    domain = "ad09_test_domain"
    (tmp_path / "requirements" / "design" / f"{domain}.md").write_text("reqs", encoding="utf-8")
    (tmp_path / "requirements" / "meaning" / f"{domain}.md").write_text("meaning", encoding="utf-8")
    (tmp_path / "design_docs" / f"{domain}_design.md").write_text("design", encoding="utf-8")

    artifact = assemble_manifest(tmp_path, domain)
    # AD-09: no longer stamps UNKNOWN; computes PASS when projection is complete.
    assert artifact.completeness_verdict == "PASS"
    assert artifact.completeness_reasons == ()


def test_assemble_manifest_computes_flag_when_stream_missing(tmp_path: Path) -> None:
    (tmp_path / "requirements" / "design").mkdir(parents=True)
    (tmp_path / "requirements" / "meaning").mkdir(parents=True)
    (tmp_path / "design_docs").mkdir(parents=True)
    domain = "ad09_incomplete"
    # design stream authority file absent on purpose.
    (tmp_path / "requirements" / "design" / f"{domain}.md").write_text("reqs", encoding="utf-8")
    (tmp_path / "requirements" / "meaning" / f"{domain}.md").write_text("meaning", encoding="utf-8")

    artifact = assemble_manifest(tmp_path, domain)
    assert artifact.completeness_verdict == "FLAG"
    assert any("design" in reason for reason in artifact.completeness_reasons)


def test_assemble_manifest_explicit_verdict_override_still_supported(tmp_path: Path) -> None:
    (tmp_path / "requirements" / "design").mkdir(parents=True)
    (tmp_path / "requirements" / "meaning").mkdir(parents=True)
    (tmp_path / "design_docs").mkdir(parents=True)
    domain = "ad09_override"
    (tmp_path / "requirements" / "design" / f"{domain}.md").write_text("reqs", encoding="utf-8")
    (tmp_path / "requirements" / "meaning" / f"{domain}.md").write_text("meaning", encoding="utf-8")
    (tmp_path / "design_docs" / f"{domain}_design.md").write_text("design", encoding="utf-8")

    artifact = assemble_manifest(tmp_path, domain, verdict="UNKNOWN")
    # A caller-supplied verdict is honored (e.g. a gate result); reasons stay empty
    # because the verdict was not computed here.
    assert artifact.completeness_verdict == "UNKNOWN"
    assert artifact.completeness_reasons == ()


def test_assemble_manifest_invalid_explicit_verdict_falls_back_unknown(tmp_path: Path) -> None:
    (tmp_path / "requirements" / "design").mkdir(parents=True)
    (tmp_path / "requirements" / "meaning").mkdir(parents=True)
    (tmp_path / "design_docs").mkdir(parents=True)
    domain = "ad09_invalid"
    (tmp_path / "requirements" / "design" / f"{domain}.md").write_text("reqs", encoding="utf-8")
    (tmp_path / "requirements" / "meaning" / f"{domain}.md").write_text("meaning", encoding="utf-8")
    (tmp_path / "design_docs" / f"{domain}_design.md").write_text("design", encoding="utf-8")

    artifact = assemble_manifest(tmp_path, domain, verdict="BOGUS")
    assert artifact.completeness_verdict == "UNKNOWN"


def test_rendered_artifact_carries_reasons_when_flagged(tmp_path: Path) -> None:
    (tmp_path / "requirements" / "design").mkdir(parents=True)
    (tmp_path / "requirements" / "meaning").mkdir(parents=True)
    (tmp_path / "design_docs").mkdir(parents=True)
    domain = "ad09_render"
    (tmp_path / "requirements" / "design" / f"{domain}.md").write_text("reqs", encoding="utf-8")
    (tmp_path / "requirements" / "meaning" / f"{domain}.md").write_text("meaning", encoding="utf-8")
    # design file absent → FLAG with a reason that must appear in the rendered frontmatter.

    artifact = assemble_manifest(tmp_path, domain)
    rendered = render_artifact(artifact)
    assert "completeness_verdict: FLAG" in rendered
    assert "completeness_reasons:" in rendered
    assert "design" in rendered


def test_cli_assemble_default_uses_computed_projection_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build_cli_pass_fixture(tmp_path)
    monkeypatch.setattr(ddp_artifact, "record", lambda *a, **k: {"quarantined": True}, raising=True)
    out = tmp_path / "DDP_ARTIFACT.md"

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
            "T1385-assemble-test",
        ]
    )

    assert rc == 0
    assert "completeness_verdict: PASS" in out.read_text(encoding="utf-8")


def test_cli_pipeline_pass_restamps_artifact_with_gate_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build_cli_pass_fixture(tmp_path)
    monkeypatch.setenv("TOOL_RECEIPTS_LEDGER", str(tmp_path / "receipts.jsonl"))
    out = tmp_path / "DDP_ARTIFACT.md"

    rc = ddp_cli.main(
        [
            "pipeline",
            "--artifact-root",
            str(tmp_path),
            "--domain",
            DOMAIN,
            "--output",
            str(out),
            "--skip-regulator",
            "--task-id",
            "T1385-pipeline-test",
        ]
    )

    assert rc == 0
    assert "completeness_verdict: PASS" in out.read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
