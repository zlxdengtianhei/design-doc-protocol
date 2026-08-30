from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

pytest.importorskip("tools.requirement_doc", reason="requirement_doc 集成面未随开源仓发布（见 README 已知集成面）；该测试只在母仓布局可跑")

from tools.requirement_doc import append, scaffold  # noqa: E402


def test_design_and_execution_route_to_distinct_targets(tmp_path: Path) -> None:
    job = tmp_path / "job"

    design_target = append._target_path(job, "alpha", "design")
    execution_target = append._target_path(job, "alpha", "execution", "phase_1")

    assert design_target == job / "requirements" / "design" / "alpha.md"
    assert execution_target == job / "requirements" / "execution" / "phase_1.md"
    assert design_target != execution_target


def test_requirement_class_does_not_change_design_req_id(tmp_path: Path) -> None:
    job = tmp_path / "job"
    scaffold.scaffold_job(job, ["alpha"], "REQ")
    verbatim = "The hash input remains source anchor plus verbatim only."
    source_anchor = "source.md:L9"
    expected_req_id = "REQ-" + hashlib.sha256(f"{source_anchor}\n{verbatim}".encode("utf-8")).hexdigest()[:8].upper()

    result = append.append_requirement(
        job=job,
        domain="alpha",
        verbatim=verbatim,
        source_anchor=source_anchor,
        session_id="session-1",
        req_id=append.derive_req_id(verbatim, source_anchor),
        date="2026-07-03",
        requirement_class="design",
        task_id="SL-2",
    )

    assert result.req_id == expected_req_id
    assert append.derive_req_id(verbatim, source_anchor) == expected_req_id
