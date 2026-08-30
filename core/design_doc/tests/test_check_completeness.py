"""Held-out tests for design_doc check_completeness.

These tests pin the two design boundaries that BUG_LEDGER DDP-001/002/003 track:

- DDP-001 / UP-70: the placeholder-filling mechanism (`build_fill_guide` /
  `--fill-guide`) enumerates every remaining placeholder with its location, and
  a real unfilled scaffold (T631) yields a stable count.
- DDP-002: the regulator IS verified on a live channel elsewhere (see
  VALIDATION.md §4 + logs/oracle_run_regulator_codex_verified_20260616.md). Here
  we lock the deterministic parse path that maps a regulator FLAG JSON into the
  tool's final verdict, so the verified behavior cannot silently regress.
- DDP-003: the deterministic shell CANNOT catch DC3/DC4 (structure-complete but
  semantically empty). `dc3_echo_soft_negative.md` deliberately passes the shell
  while the live regulator flags it. This test asserts the shell PASS on purpose,
  documenting the split as a design boundary, not a bug.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.design_doc import check_completeness  # noqa: E402
from core.gatekit.base import DeterministicShell, Finding  # noqa: E402

FIXTURE_DIR = ROOT / "core" / "design_doc" / "fixtures"
REAL_T631 = (
    ROOT
    / "core"
    / "design_doc"
    / "fixtures"
    / "T631_git-env-cleanup-design.md"
)
SOFT_NEGATIVE = FIXTURE_DIR / "dc3_echo_soft_negative.md"
SELF_DESIGN = FIXTURE_DIR / "pass_check_completeness_self_design.md"


# --- DDP-001: placeholder-filling mechanism ---------------------------------


def test_fill_guide_enumerates_t631_placeholders_with_locations() -> None:
    """The filling mechanism tells the author exactly what to fill and where."""
    guide = check_completeness.build_fill_guide_for_file(REAL_T631)

    assert guide.placeholder_count == 34
    assert len(guide.items) == 34
    # Each item carries the deterministic locator quadruple.
    for item in guide.items:
        assert item.line >= 1
        assert item.section
        assert item.placeholder.startswith("<") and item.placeholder.endswith(">")
    # Core Layer 1 fields are present and located on their real lines.
    fields = {item.field for item in guide.items}
    assert {"core_need", "success_effect", "hard_requirements"}.issubset(fields)


def test_fill_guide_is_empty_when_no_placeholders_remain() -> None:
    guide = check_completeness.build_fill_guide_for_file(SELF_DESIGN)

    assert guide.placeholder_count == 0
    assert guide.items == ()


# --- DDP-002: regulator parse path (no live model call) ---------------------


def test_parse_regulator_json_flag_with_dc3_issues_maps_to_flag() -> None:
    """A regulator FLAG with dc3 issues must drive the tool toward FLAG.

    The live codex:high run (VALIDATION.md §4.1) returns exactly this shape. This
    test pins the parse logic so the verified verdict survives refactors.
    """
    raw = '{"verdict": "FLAG", "dc3_issues": [{"field": "core_need", "line": 27, "problem": "echo", "fix": "be specific"}], "dc4_issues": [], "dc5_issues": []}'
    parsed, error = check_completeness.parse_regulator_json(raw)

    assert error is None
    assert parsed is not None
    assert parsed["verdict"] == "FLAG"
    assert parsed["dc3_issues"]


def test_parse_regulator_json_pass_with_no_issues_stays_pass() -> None:
    raw = '{"verdict": "PASS", "dc3_issues": [], "dc4_issues": [], "dc5_issues": []}'
    parsed, error = check_completeness.parse_regulator_json(raw)

    assert error is None
    assert parsed["verdict"] == "PASS"


def test_parse_regulator_json_fail_alias_maps_to_flag() -> None:
    raw = '{"verdict": "FAIL", "dc3_issues": [], "dc4_issues": [], "dc5_issues": []}'
    parsed, error = check_completeness.parse_regulator_json(raw)

    assert error is None
    assert parsed["verdict"] == "FLAG"


def test_parse_regulator_json_dc6_issues_force_flag() -> None:
    raw = '{"verdict": "PASS", "dc3_issues": [], "dc4_issues": [], "dc5_issues": [], "dc6_issues": [{"field": "M1", "line": 30, "problem": "echo", "fix": "write meaning"}]}'
    parsed, error = check_completeness.parse_regulator_json(raw)

    assert error is None
    assert parsed is not None
    assert parsed["verdict"] == "FLAG"


# --- DDP-003: the deterministic shell deliberately cannot catch DC3/DC4 -----


def test_soft_negative_passes_deterministic_shell_by_design() -> None:
    """DC3/DC4 are semantic: structure-complete but empty docs pass the shell.

    `dc3_echo_soft_negative.md` has zero placeholders, all required sections, a
    filled decision row, and a chosen Final Boundary status. The deterministic
    shell (DC1/DC2) therefore returns PASS. The live regulator flags it
    (VALIDATION.md §4.1). This split is the design boundary DDP-003 documents:
    only DC1/DC2 are strong deterministic evidence; DC3/DC4/DC5 require the
    second agent. If this test starts FAILING because the shell now flags the
    soft negative, the shell has grown semantic heuristics and this boundary
    statement must be revisited, not silently updated.
    """
    shell = check_completeness.scan_text(SOFT_NEGATIVE.read_text(encoding="utf-8"))

    assert shell.verdict == "PASS", (
        "deterministic shell must NOT catch the DC3 soft negative; if it does, "
        "DC3/DC4 are no longer regulator-only and DDP-003 must be re-scoped"
    )
    assert shell.placeholder_count == 0


def test_scan_flagging_issues_matches_scan_text_verdict() -> None:
    """scan_flagging_issues is the stable interface gates consume; it equals the
    exact issue set that drives scan_text's verdict."""
    text = REAL_T631.read_text(encoding="utf-8")
    shell = check_completeness.scan_text(text)
    flagging = check_completeness.scan_flagging_issues(text)

    assert (shell.verdict == "FLAG") == bool(flagging)
    if shell.verdict == "FLAG":
        flagging_codes = {issue.code for issue in flagging}
        # Every flagging issue is a non-WARNING issue from the full set.
        for issue in flagging:
            assert issue.severity != "WARNING"
        # T631 must surface placeholder + structural issues.
        assert "DC1_PLACEHOLDER" in flagging_codes


def test_t631_scaffold_is_flagged_and_self_design_passes() -> None:
    """Regression: the known T631 fixture (34 placeholders) FLAGs; a genuinely
    filled design doc PASSes the deterministic shell."""
    assert check_completeness.scan_text(REAL_T631.read_text(encoding="utf-8")).verdict == "FLAG"
    self_design = check_completeness.scan_text(SELF_DESIGN.read_text(encoding="utf-8"))
    assert self_design.verdict == "PASS"
    assert not [issue for issue in self_design.issues if issue.code.startswith("DC6_")]


def _tri_face_doc(
    *,
    requirement_status: str = "filled",
    meaning_status: str = "unwritten",
    design_status: str = "filled",
    meaning_pointer_row: str = "| 承接总领意义 | `<CROSS_DOMAIN_MEANING.md 条目编号，例如 1 或 A>` |",
) -> str:
    return f"""# Design Doc：T963 / DDP-02

## (0) 原始需求锚

req-doc: `adhoc_jobs/example/T963_req.md`

## §需求面

| 字段 | 值 |
|---|---|
| face_status | {requirement_status} |
| 设计需求 | `DDP-02` |
| 执行需求 | `T963` |
| requirement_doc 指针 | `adhoc_jobs/example/T963_req.md` |

## §意义面

| 字段 | 值 |
|---|---|
| face_status | {meaning_status} |
| 设计需求 | `<设计需求 req_id / requirement_doc 条目>` |
| 执行需求 | `<执行需求 todo id / dispatch 条目>` |
{meaning_pointer_row}

### M1 本域核心意义
- `<这个设计文档为什么存在>`

### M2 补哪类根局限
- `<补上下文缺口 c>`

### M3 总领意义锚
- `<CROSS_DOMAIN_MEANING.md 中的 1>`

### M4 防哪种不良行为
- `<防回显需求>`

### M5 意义到落地对应
- `<落到 DC6 和状态门>`

## §设计面

| 字段 | 值 |
|---|---|
| face_status | {design_status} |
| 设计需求 | `DDP-02` |
| 执行需求 | `T963` |

## Layer 1 功能设计

### 1.1 核心问题(core_need)
- 给 design_doc 增加意义面，并让三面可以异步填写。

### 1.2 成功效果(success_effect)
- unwritten 面占位合法，filled 面占位被 DC1 抓住。

### 1.3 硬性约束(hard_requirements)
- 需求面只指向 requirement_doc，不复制逐字需求。

### 1.4 明确不做(negative_requirements)
- 不改 requirement_doc 子系统。

### 1.5 交付物(deliverable)
- scaffold、DC1 状态门、DC6 壳和测试。

## Layer 2 实现设计

### 2.2 各组件职责与边界(scope_in/scope_out)

| 组件 | 职责 (scope_in) | 禁读 (scope_out / forbidden_read) | skill_injection | 证据或接口 |
|---|---|---|---|---|
| checker | 校验三面状态和意义面结构 | 不读设计者成功叙事 | workflow_design_doc_protocol | check_completeness.py |

### 2.3 关键设计决策(含为什么)

| 决策 | 选择 | 为什么 | 放弃的替代方案 |
|---|---|---|---|
| DC1 状态门 | 只检查 filled 面 | 异步留白需要合法状态 | 全文零占位会误伤 unwritten 面 |

## Final Boundary

| 字段 | 填写 |
|---|---|
| 状态 | DONE |
"""


def test_unwritten_meaning_face_placeholders_do_not_trigger_dc1() -> None:
    shell = check_completeness.scan_text(_tri_face_doc())

    assert shell.verdict == "PASS"
    assert not [issue for issue in shell.issues if issue.code == "DC1_PLACEHOLDER"]


def test_filled_meaning_face_placeholders_still_trigger_dc1() -> None:
    shell = check_completeness.scan_text(_tri_face_doc(meaning_status="filled"))

    assert shell.verdict == "FLAG"
    assert any(issue.code == "DC1_PLACEHOLDER" for issue in shell.issues)


def test_dc6_flags_missing_meaning_pointer_slot() -> None:
    shell = check_completeness.scan_text(_tri_face_doc(meaning_pointer_row="| 承接总领意义 |  |"))

    assert shell.verdict == "FLAG"
    assert any(issue.code == "DC6_MEANING_POINTER_MISSING" for issue in shell.issues)


def test_dc6_flags_invalid_face_status() -> None:
    shell = check_completeness.scan_text(_tri_face_doc(meaning_status="draft"))

    assert shell.verdict == "FLAG"
    assert any(issue.code == "DC6_FACE_STATUS_INVALID" for issue in shell.issues)


def _d9_doc(
    *,
    layer2_state: str = "not_applicable",
    layer2_reason: str = "单文件边界明确，没有实现路径分叉。",
    layer2_triggers: str = "multiple_paths=false;handoff=false;user_confirmation=false;cross_file_impact=false",
    layer3_state: str = "not_applicable",
    layer3_reason: str = "本轮只验证文档结构，不写回实现对象。",
    layer3_triggers: str = "existing_object_disposition=false;implementation_writeback=false;direct_multi_file_execution=false",
) -> str:
    return f"""# Current D9 design

## 头部元数据

| d9_contract | on-demand-v1 |

## (0) 原始需求锚

req-doc: `requirements.md`

## Layer 1 功能设计

### 1.2 成功效果(success_effect)

- checker can deterministically report the selected layer state.

### 1.4 明确不做(negative_requirements)

- 不判断理由的语义质量，也不宣称协议运行效果。

## D9 层适用性与状态

| layer | state | reason | trigger_evaluation |
|---|---|---|---|
| Layer 2 | {layer2_state} | {layer2_reason} | {layer2_triggers} |
| Layer 3 | {layer3_state} | {layer3_reason} | {layer3_triggers} |

## Final Boundary

| 字段 | 填写 |
|---|---|
| 状态 | PARTIAL |
"""


def test_current_d9_not_applicable_rows_pass_with_all_trigger_evaluations() -> None:
    shell = check_completeness.scan_text(_d9_doc())

    assert shell.verdict == "PASS"
    assert not [issue for issue in shell.issues if issue.code.startswith("DC2_LAYER_")]


def test_current_d9_not_applicable_with_active_trigger_flags_exact_state() -> None:
    shell = check_completeness.scan_text(
        _d9_doc(layer2_triggers="multiple_paths=true;handoff=false;user_confirmation=false;cross_file_impact=false")
    )

    assert shell.verdict == "FLAG"
    issue = next(issue for issue in shell.issues if issue.code == "DC2_LAYER_NOT_APPLICABLE_TRIGGERED")
    assert issue.field == "Layer 2 state"
    assert issue.value == "multiple_paths"


def test_current_d9_requires_reason_and_trigger_evaluation() -> None:
    shell = check_completeness.scan_text(
        _d9_doc(layer2_reason="", layer3_triggers="")
    )

    assert shell.verdict == "FLAG"
    codes = {issue.code for issue in shell.issues}
    assert "DC2_NOT_APPLICABLE_REASON_MISSING" in codes
    assert "DC2_LAYER_TRIGGER_EVALUATION_MISSING" in codes


def test_current_d9_unwritten_is_incomplete() -> None:
    shell = check_completeness.scan_text(
        _d9_doc(layer2_state="unwritten", layer2_triggers="multiple_paths=false;handoff=false;user_confirmation=false;cross_file_impact=false")
    )

    assert shell.verdict == "FLAG"
    assert any(issue.code == "DC2_LAYER_STATE_UNWRITTEN" for issue in shell.issues)


def test_current_d9_required_layer_two_requires_decision_table() -> None:
    shell = check_completeness.scan_text(_d9_doc(layer2_state="required"))

    assert shell.verdict == "FLAG"
    assert any(issue.code == "DC2_MISSING_DECISION_TABLE" for issue in shell.issues)


def test_current_d9_required_layer_two_passes_with_decision_row() -> None:
    text = _d9_doc(
        layer2_state="required",
        layer2_triggers="multiple_paths=true;handoff=false;user_confirmation=false;cross_file_impact=false",
    ).replace(
        "## Final Boundary",
        """## Layer 2 实现设计

### 2.3 关键设计决策(含为什么)

| 决策 | 选择 | 为什么 | 放弃的替代方案 |
|---|---|---|---|
| applicability | explicit state table | structural gate is deterministic | unconditional Layer 2 |

## Final Boundary""",
    )
    shell = check_completeness.scan_text(text)

    assert shell.verdict == "PASS"


def test_current_d9_required_layer_two_all_false_flags_precise_predicate() -> None:
    text = _d9_doc(layer2_state="required").replace(
        "## Final Boundary",
        """## Layer 2 实现设计

### 2.3 关键设计决策(含为什么)

| 决策 | 选择 | 为什么 | 放弃的替代方案 |
|---|---|---|---|
| applicability | explicit state table | structural gate is deterministic | unconditional Layer 2 |

## Final Boundary""",
    )
    shell = check_completeness.scan_text(text)

    assert shell.verdict == "FLAG"
    issue = next(issue for issue in shell.issues if issue.code == "DC2_REQUIRED_WITHOUT_ACTIVE_TRIGGER")
    assert issue.line > 0
    assert issue.field == "Layer 2 state / trigger_evaluation"
    assert issue.value == "state=required; active_trigger=none"


def test_current_d9_required_layer_three_requires_code_delta_sections() -> None:
    shell = check_completeness.scan_text(_d9_doc(layer3_state="required"))

    assert shell.verdict == "FLAG"
    assert any(issue.code == "DC2_MISSING_LAYER3_CONTENT" for issue in shell.issues)


def test_current_d9_required_layer_three_passes_with_delta_sections() -> None:
    text = _d9_doc(
        layer3_state="required",
        layer3_triggers="existing_object_disposition=true;implementation_writeback=false;direct_multi_file_execution=false",
    ).replace(
        "## Final Boundary",
        """## Layer 3 代码改动清单

### 3.1 新增(ADDED)
- 无

### 3.2 修改(MODIFIED)
- 无

### 3.3 删除(REMOVED)
- 无

## Final Boundary""",
    )
    shell = check_completeness.scan_text(text)

    assert shell.verdict == "PASS"


def test_current_d9_required_layer_three_all_false_flags_precise_predicate() -> None:
    text = _d9_doc(layer3_state="required").replace(
        "## Final Boundary",
        """## Layer 3 代码改动清单

### 3.1 新增(ADDED)
- 无

### 3.2 修改(MODIFIED)
- 无

### 3.3 删除(REMOVED)
- 无

## Final Boundary""",
    )
    shell = check_completeness.scan_text(text)

    assert shell.verdict == "FLAG"
    issue = next(issue for issue in shell.issues if issue.code == "DC2_REQUIRED_WITHOUT_ACTIVE_TRIGGER")
    assert issue.line > 0
    assert issue.field == "Layer 3 state / trigger_evaluation"
    assert issue.value == "state=required; active_trigger=none"


def test_current_d9_rejects_filled_layer_state_but_keeps_face_status_compatibility() -> None:
    shell = check_completeness.scan_text(_d9_doc(layer2_state="filled"))

    assert shell.verdict == "FLAG"
    issue = next(issue for issue in shell.issues if issue.code == "DC2_LAYER_STATE_INVALID")
    assert issue.value == "filled"
    # The separate, historical face_status state machine remains readable.
    assert check_completeness.scan_text(_tri_face_doc()).verdict == "PASS"


@pytest.mark.parametrize("alias", ("yes", "no", "active", "inactive", "triggered", "not_triggered"))
def test_current_d9_rejects_trigger_value_aliases(alias: str) -> None:
    layer2_triggers = ";".join(
        f"{key}={alias}"
        for key in ("multiple_paths", "handoff", "user_confirmation", "cross_file_impact")
    )
    shell = check_completeness.scan_text(_d9_doc(layer2_triggers=layer2_triggers))

    assert shell.verdict == "FLAG"
    issue = next(issue for issue in shell.issues if issue.code == "DC2_LAYER_TRIGGER_EVALUATION_MISSING")
    assert issue.field == "Layer 2 trigger_evaluation"
    assert "multiple_paths" in issue.value


def test_current_d9_requires_requirement_anchor() -> None:
    shell = check_completeness.scan_text(_d9_doc().replace("req-doc: `requirements.md`", "req-doc: MISSING"))

    assert shell.verdict == "FLAG"
    assert any(issue.code == "DC0_REQUIREMENT_ANCHOR_MISSING" for issue in shell.issues)


def test_design_doc_completeness_shell_is_deterministic_shell() -> None:
    shell = check_completeness.DesignDocCompletenessShell()
    findings, _text = shell.execute(SELF_DESIGN)

    assert issubclass(check_completeness.DesignDocCompletenessShell, DeterministicShell)
    assert all(isinstance(item, Finding) for item in findings)
    assert shell.result is not None
    assert shell.result.verdict == "PASS"


def test_main_uses_compute_verdict(monkeypatch, capsys) -> None:
    calls = []
    real_compute_verdict = check_completeness.compute_verdict

    def spy(findings, regulator_result, use_regulator=True):
        calls.append((findings, regulator_result, use_regulator))
        return real_compute_verdict(findings, regulator_result, use_regulator=use_regulator)

    monkeypatch.setattr(check_completeness, "compute_verdict", spy)

    rc = check_completeness.main((str(SELF_DESIGN), "--json"))

    assert rc == 0
    assert len(calls) == 1
    assert calls[0][1] is None
    assert calls[0][2] is False
    assert '"final_verdict": "PASS"' in capsys.readouterr().out
