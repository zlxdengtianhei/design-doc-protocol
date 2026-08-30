from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ddp import intake  # noqa: E402
pytest.importorskip("tools.requirement_doc", reason="requirement_doc 集成面未随开源仓发布（见 README 已知集成面）；该测试只在母仓布局可跑")

from tools.requirement_doc import append  # noqa: E402


def test_execution_write_scaffolds_phase_bound_carrier(tmp_path: Path) -> None:
    job = tmp_path / "job"
    verbatim = "Run phase workers must preserve execution-only requirements."
    result = intake.record_requirement(
        job=job,
        verbatim=verbatim,
        source_anchor="runbook.md:L12",
        session_id="session-2",
        requirement_class="execution",
        phase="phase_2",
        req_id="REQ-EXEC-01",
        date="2026-07-03",
        task_id="SL-2-real-task",
    )

    target = job / "requirements" / "execution" / "phase_2.md"
    assert result.target.endswith("requirements/execution/phase_2.md")
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "doc_type: execution_requirements" in text
    assert "#### REQ-EXEC-01" in text
    assert "requirement_class=execution" in text
    assert "task_id=SL-2-real-task" in text
    assert "session_id=session-2" in text
    assert f"sha256={append.sha256_text(verbatim)}" in text
    assert "> Run phase workers must preserve execution-only requirements." in text


def test_execution_requires_phase(tmp_path: Path) -> None:
    with pytest.raises(append.AppendError, match="phase is required"):
        intake.record_requirement(
            job=tmp_path / "job",
            verbatim="execution requirement",
            source_anchor="source.md:L1",
            session_id="session-2",
            requirement_class="execution",
            req_id="REQ-EXEC-02",
        )


def test_execution_dry_run_does_not_create_carrier(tmp_path: Path) -> None:
    job = tmp_path / "job"

    result = intake.record_requirement(
        job=job,
        verbatim="dry run execution requirement",
        source_anchor="source.md:L2",
        session_id="session-2",
        requirement_class="execution",
        phase="phase_3",
        req_id="REQ-EXEC-03",
        dry_run=True,
    )

    assert result.action == "dry-run:appended"
    assert not (job / "requirements" / "execution" / "phase_3.md").exists()
