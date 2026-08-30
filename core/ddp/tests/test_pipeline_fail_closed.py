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


def _read_receipts(ledger: Path) -> list[dict]:
    return [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_pipeline_fail_closed_blocks_and_records_attempt_chain(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("tools.tool_receipts", reason="回执台账面是母仓基建、未随开源仓发布；该链完整性测试只在母仓布局可跑")

    artifact_root = tmp_path / "artifact_root"
    artifact_root.mkdir()
    ledger = tmp_path / "receipts.jsonl"
    monkeypatch.setenv("TOOL_RECEIPTS_LEDGER", str(ledger))

    rc = ddp_cli.main(
        [
            "pipeline",
            "--artifact-root",
            str(artifact_root),
            "--domain",
            DOMAIN,
            "--skip-regulator",
            "--task-id",
            "SL-4-test",
        ]
    )

    assert rc == 1
    artifact_path = artifact_root / "DDP_ARTIFACT.md"
    assert artifact_path.exists()

    receipts = _read_receipts(ledger)
    by_tool = {row["tool"]: row for row in receipts}
    assert {"ddp_assemble", "ddp_check_artifact", "ddp_pipeline"}.issubset(by_tool)

    assert by_tool["ddp_assemble"]["exit_code"] == 0
    assert by_tool["ddp_check_artifact"]["exit_code"] == 1
    assert by_tool["ddp_pipeline"]["exit_code"] == 1
    assert by_tool["ddp_pipeline"]["args_summary"]["gate_status"] == "FLAG"
    assert by_tool["ddp_pipeline"]["task_id"] == "SL-4-TEST"

    pass_pipeline_events = [
        row
        for row in receipts
        if row["tool"] == "ddp_pipeline"
        and row["exit_code"] == 0
        and row["args_summary"].get("gate_status") == "PASS"
    ]
    assert pass_pipeline_events == []
