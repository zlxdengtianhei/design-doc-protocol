from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ddp import cli as ddp_cli  # noqa: E402

DOMAIN = "ddp_design_doc_protocol"


def _write_projection_authorities(root: Path, *, meaning: bool = False, design: bool = True) -> None:
    req = root / "requirements" / "design" / f"{DOMAIN}.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(
        "\n".join(
            [
                "# Requirements",
                "",
                "#### REQ-DDP-CLI CLI completion",
                "source prompt.md:L1 · provenance req_id=REQ-DDP-CLI requirement_class=design task_id=T1387 session_id=session-1 created_at=2026-07-08 sha256=abc · session session-1",
                "",
                "> DDP CLI exposes the stream operations.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if meaning:
        meaning_path = root / "requirements" / "meaning" / f"{DOMAIN}.md"
        meaning_path.parent.mkdir(parents=True, exist_ok=True)
        meaning_path.write_text(
            "# Meaning\n\nM1: Meaning stays in the authority stream.\n",
            encoding="utf-8",
        )
    if design:
        design_path = root / "design_docs" / f"{DOMAIN}_design.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text("# Design\n\nThe design authority exists.\n", encoding="utf-8")


def test_meaning_cli_scaffold_and_check_pass(tmp_path: Path, capsys) -> None:
    root = tmp_path / "job"
    root.mkdir()

    rc = ddp_cli.main(["meaning", "scaffold", "--artifact-root", str(root), "--domain", DOMAIN])
    out = capsys.readouterr().out

    assert rc == 0
    assert "meaning authority:" in out
    assert (root / "requirements" / "meaning" / f"{DOMAIN}.md").exists()

    _write_projection_authorities(root, meaning=True)
    rc = ddp_cli.main(["meaning", "check", "--artifact-root", str(root), "--domain", DOMAIN])
    out = capsys.readouterr().out

    assert rc == 0
    assert "verdict: PASS" in out


def test_meaning_cli_check_flags_copied_body_without_pointer(tmp_path: Path, capsys) -> None:
    root = tmp_path / "job"
    _write_projection_authorities(root, meaning=True)
    artifact = root / "copied_artifact.md"
    artifact.write_text(
        "\n".join(
            [
                "# DDP Artifact - copied",
                "",
                "## Meaning Stream",
                "",
                "M1: Meaning stays in the authority stream.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    rc = ddp_cli.main(
        [
            "meaning",
            "check",
            "--artifact",
            str(artifact),
            "--authority",
            str(root / "requirements" / "meaning" / f"{DOMAIN}.md"),
        ]
    )
    out = capsys.readouterr().out

    assert rc == 1
    assert "verdict: FLAG" in out
    assert "meaning copied instead of pointed" in out


def test_intake_cli_records_execution_requirement_and_receipt(tmp_path: Path, monkeypatch, capsys) -> None:
    pytest.importorskip("tools.requirement_doc", reason="requirement_doc 集成面未随开源仓发布；只在母仓布局可跑")
    root = tmp_path / "job"
    verbatim = tmp_path / "verbatim.txt"
    verbatim.write_text("Execution phases need their own requirement carrier.\n", encoding="utf-8")
    ledger = tmp_path / "receipts.jsonl"
    monkeypatch.setenv("TOOL_RECEIPTS_LEDGER", str(ledger))

    rc = ddp_cli.main(
        [
            "intake",
            "--job",
            str(root),
            "--verbatim-file",
            str(verbatim),
            "--source-anchor",
            "prompt.md:L4",
            "--req-class",
            "execution",
            "--phase",
            "phase_1",
            "--session-id",
            "session-1",
            "--task-id",
            "T1389",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "requirements/execution/phase_1.md" in out
    assert (root / "requirements" / "execution" / "phase_1.md").exists()
    receipts = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert any(row["tool"] == "ddp_record_requirement" for row in receipts)


def test_coverage_cli_returns_live_gap_rows(tmp_path: Path, capsys) -> None:
    root = tmp_path / "job"
    _write_projection_authorities(root, design=True)

    rc = ddp_cli.main(["coverage", "--job", str(root), "--domain", DOMAIN])
    out = capsys.readouterr().out

    assert rc == 0
    assert "requirements | present | satisfied" in out
    assert "meaning | not_yet_active | deferred" in out
    assert "design | present | satisfied" in out

    missing_design_root = tmp_path / "missing_design"
    _write_projection_authorities(missing_design_root, design=False)
    rc = ddp_cli.main(["coverage", "--job", str(missing_design_root), "--domain", DOMAIN])
    out = capsys.readouterr().out

    assert rc == 1
    assert "design | missing | unmet" in out


def test_status_cli_reports_projection_and_recent_receipts(tmp_path: Path, capsys) -> None:
    root = tmp_path / "job"
    _write_projection_authorities(root, design=True)
    ledger = tmp_path / "receipts.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "event_id": "TR-DDP-STATUS",
                "tool": "ddp_assemble",
                "exit_code": 0,
                "task_id": "T1391",
                "args_summary": {"artifact_root": str(root)},
                "artifact_paths": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rc = ddp_cli.main(
        [
            "status",
            "--artifact-root",
            str(root),
            "--domain",
            DOMAIN,
            "--ledger",
            str(ledger),
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "projection_verdict: PASS" in out
    assert "recent_receipts: 1" in out
    assert "TR-DDP-STATUS ddp_assemble" in out


def test_guide_cli_intent_routes_to_stream_commands(capsys) -> None:
    rc = ddp_cli.main(["guide", "--intent", "meaning"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "DDP guide: meaning" in out
    assert "meaning scaffold" in out
    assert "meaning check" in out


def test_meaning_scaffold_and_check_emit_receipts(tmp_path: Path, monkeypatch) -> None:
    from core.ddp import check_artifact as ddp_check_artifact

    captured: list[tuple[str, dict, int]] = []

    def _capture(tool_name, args_summary, exit_code, task=None, artifact_paths=None):
        captured.append((tool_name, args_summary, exit_code))

    monkeypatch.setattr(ddp_check_artifact, "record_receipt_best_effort", _capture)

    root = tmp_path / "job"
    root.mkdir()
    rc = ddp_cli.main(["meaning", "scaffold", "--artifact-root", str(root), "--domain", DOMAIN])
    assert rc == 0

    _write_projection_authorities(root, meaning=True)
    rc = ddp_cli.main(["meaning", "check", "--artifact-root", str(root), "--domain", DOMAIN])
    assert rc == 0

    tools_seen = [item[0] for item in captured]
    assert "ddp_meaning_scaffold" in tools_seen
    assert "ddp_meaning_check" in tools_seen
    check_calls = [item for item in captured if item[0] == "ddp_meaning_check"]
    assert check_calls[0][2] == 0
    assert check_calls[0][1]["domain"] == DOMAIN
