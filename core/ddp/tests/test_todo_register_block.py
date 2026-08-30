from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.design_doc import design_doc_scaffold  # noqa: E402


DISPATCH_OUTPUT = """## 原始 prompt 逐字原文

Wire the DDP design stream to emit a downstream todo registration block.

## 任务元数据

- type: implementation
- label: ddp
- req_id: DDP-SL5
- prompt_ref: Run3/domains/ddp_design_doc_protocol/GOAL.md#SL-5
"""

SHOW_OUTPUT = """### T950: DDP design_doc wiring [medium]
- **Type**: implementation
- **Label**: ddp
- **Req**: DDP-SL5
- **PromptRef**: Run3/domains/ddp_design_doc_protocol/GOAL.md#SL-5
- **Description**: phase: SL-5 | domain: ddp_design_doc_protocol
"""


@pytest.fixture
def scaffold_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_todo(*args: str) -> str:
        if args == ("dispatch", "T950"):
            return DISPATCH_OUTPUT
        if args == ("show", "T950"):
            return SHOW_OUTPUT
        raise AssertionError(f"unexpected todo args: {args}")

    monkeypatch.setattr(design_doc_scaffold, "run_todo", fake_run_todo)
    monkeypatch.setattr(design_doc_scaffold, "record_receipt_best_effort", lambda *args, **kwargs: None)


def test_render_design_doc_includes_literal_todo_register_block() -> None:
    todo_register = "owner: downstream-todo\nbody: keep this literal\n- do not call todo add"

    text = design_doc_scaffold.render_design_doc(
        "T950",
        "original prompt",
        {"req_id": "DDP-SL5", "label": "ddp", "type": "implementation"},
        {"PromptRef": "source.md#SL-5", "phase": "SL-5"},
        "ddp-design-doc-wiring",
        todo_register=todo_register,
    )

    assert f"```todo_register\n{todo_register}\n```" in text
    assert "do not call todo add" in text


def test_render_design_doc_omits_todo_register_when_absent() -> None:
    text = design_doc_scaffold.render_design_doc(
        "T950",
        "original prompt",
        {"req_id": "DDP-SL5", "label": "ddp", "type": "implementation"},
        {"PromptRef": "source.md#SL-5", "phase": "SL-5"},
        "ddp-design-doc-wiring",
    )

    assert "todo_register" not in text
    assert "Todo Register" not in text


def test_ddp_caller_can_override_scaffold_output_dir(scaffold_fixture: None, tmp_path: Path) -> None:
    out_dir = tmp_path / "ddp_design_docs"
    todo_register = "task: consume-this-design"

    target = design_doc_scaffold.create_scaffold(
        "T950",
        slug="ddp-design-doc-wiring",
        out_dir=out_dir,
        todo_register=todo_register,
    )

    assert target == out_dir / "T950_ddp-design-doc-wiring.md"
    text = target.read_text(encoding="utf-8")
    assert f"```todo_register\n{todo_register}\n```" in text
