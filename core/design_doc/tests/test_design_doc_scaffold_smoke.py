from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.design_doc import design_doc_scaffold  # noqa: E402
from core.design_doc.inject_units import parse_units  # noqa: E402


DISPATCH_OUTPUT = """## 原始 prompt 逐字原文

解决 Git 环境问题，清理没正常用上的 Git 工具。

## 任务元数据

- type: implementation
- label: landing-pipeline
- req_id: G-01
- prompt_ref: REQUIREMENTS_ORIGINAL_TEXT.md#G-01
"""

SHOW_OUTPUT = """### T902: 解决 Git 环境问题：生产环境没正常用上之前创建的 Git 工具，导致 Git 环境有问题，需先清理干净 [medium]
- **Created**: 2026-06-03
- **Type**: implementation
- **Label**: landing-pipeline
- **Req**: G-01
- **PromptRef**: REQUIREMENTS_ORIGINAL_TEXT.md#G-01
- **Description**: phase: Phase 2 | domain: tools-code
"""

NON_LANDING_DISPATCH_OUTPUT = """## 原始 prompt 逐字原文

为普通任务生成设计文档。

## 任务元数据

- type: implementation
- label: infra-tooling
- req_id: NL-01
- prompt_ref: adhoc_jobs/example/source.md#NL-01
"""

NON_LANDING_SHOW_OUTPUT = """### T857: 普通任务设计文档 [medium]
- **Type**: implementation
- **Label**: infra-tooling
- **Req**: NL-01
- **PromptRef**: adhoc_jobs/example/source.md#NL-01
- **Description**: phase: Phase X | domain: tools-code
"""


@pytest.fixture
def isolated_scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(design_doc_scaffold, "DESIGN_DOC_DIR", tmp_path)

    def fake_run_todo(*args: str) -> str:
        if args == ("dispatch", "T902"):
            return DISPATCH_OUTPUT
        if args == ("show", "T902"):
            return SHOW_OUTPUT
        if args == ("dispatch", "T857"):
            return NON_LANDING_DISPATCH_OUTPUT
        if args == ("show", "T857"):
            return NON_LANDING_SHOW_OUTPUT
        raise AssertionError(f"unexpected todo args: {args}")

    monkeypatch.setattr(design_doc_scaffold, "run_todo", fake_run_todo)
    monkeypatch.setattr(design_doc_scaffold, "record_receipt_best_effort", lambda *args, **kwargs: None)
    return tmp_path


def test_design_doc_explicit_slug_and_idempotent_exit(
    isolated_scaffold: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = design_doc_scaffold.create_scaffold("T902", slug="git-env-cleanup-design")

    assert target == isolated_scaffold / "T902_git-env-cleanup-design.md"
    text = target.read_text(encoding="utf-8")
    assert "解决 Git 环境问题，清理没正常用上的 Git 工具。" in text
    assert "| semantic_slug | git-env-cleanup-design |" in text
    assert "## §需求面" in text
    assert "## §意义面" in text
    assert "## §设计面" in text
    assert "| d9_contract | on-demand-v1 |" in text
    assert "### D9 层适用性与状态" in text
    assert "multiple_paths=unwritten" in text
    assert "direct_multi_file_execution=unwritten" in text
    assert "| face_status | unwritten |" in text
    assert "| 承接总领意义 | `<CROSS_DOMAIN_MEANING.md 条目编号，例如 1 或 A>` |" in text
    assert "设计需求" in text and "执行需求" in text
    assert "Forbidden Read 契约" in text
    assert "写意义面的 agent 不读 §设计面草稿" in text

    monkeypatch.setattr(
        sys,
        "argv",
        ["design_doc_scaffold.py", "T902", "--slug", "git-env-cleanup-design"],
    )
    assert design_doc_scaffold.main() == 1


def test_design_doc_auto_slug_is_semantic(isolated_scaffold: Path) -> None:
    target = design_doc_scaffold.create_scaffold("T902")

    assert target.name == "T902_git-env-tool-cleanup.md"
    assert target.name != "T902_G-01_DESIGN.md"
    assert "| semantic_slug | git-env-tool-cleanup |" in target.read_text(encoding="utf-8")


def test_non_landing_scaffold_out_dir_and_req_doc_anchor(isolated_scaffold: Path, tmp_path: Path) -> None:
    req_doc = tmp_path / "req.md"
    req_doc.write_text("req", encoding="utf-8")

    target = design_doc_scaffold.create_scaffold(
        "T857",
        slug="ordinary-task",
        out_dir=tmp_path,
        req_doc=req_doc,
    )

    text = target.read_text(encoding="utf-8")
    assert target == tmp_path / "T857_ordinary-task.md"
    assert "label | infra-tooling" in text
    assert f"req-doc: `{req_doc}`" in text
    assert f"| requirement_doc 指针 | `{req_doc}` |" in text


def test_scaffold_output_feeds_inject_units_without_raise(isolated_scaffold: Path, tmp_path: Path) -> None:
    req_doc = tmp_path / "req.md"
    req_doc.write_text("req", encoding="utf-8")
    target = design_doc_scaffold.create_scaffold(
        "T857",
        slug="injectable",
        out_dir=tmp_path,
        req_doc=req_doc,
    )

    units = parse_units(target)

    assert len(units) == 1
