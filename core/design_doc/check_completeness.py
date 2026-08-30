#!/usr/bin/env python3
"""Check whether a design_doc artifact is filled enough to leave the draft gate.

QGF migration note (T1321): DC shell checks now run through
``DesignDocCompletenessShell(DeterministicShell)`` and final verdict aggregation
uses ``compute_verdict``. DC3/DC4/DC5 keep the legacy direct-runner rich schema
until P1 generalizes ``base.Regulator``.

Deterministic shell:
- DC1: no ``<...>`` placeholders remain in filled faces, with line/section/field
  location. Legacy docs with no face_status markers keep the old whole-document
  placeholder scan.
- DC2: current ``on-demand-v1`` documents always require a success effect, an
  explicit negative boundary, requirement anchors, and Final Boundary status.
  Layer 2/3 are gated by an explicit applicability/state table. Legacy documents
  remain readable under the historical five-field/decision-table checks.
- DC6: tri-face meaning-face shell checks when the new face scaffold is present.
- DC7 removed (2026-08-30, D4 slimming audit): the reference-only marker rule
  was a mechanical gate over a semantic obligation and produced friction without
  a single recorded real failure it prevented. Its obligation moved to the
  regulator's DC3 judgement (design face must keep implementation truth in the
  files, not in the design document's description of them).

Optional regulator:
- DC3/DC4/DC5/DC6 review through infra_core.regulator_runner, using only the
  design document text.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


TOOL_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
DAO_ROUTING = WORKSPACE_ROOT / "rules" / "skills" / "_DAO_ROUTING.md"

from core.gatekit.base import (  # noqa: E402
    DeterministicShell,
    Finding,
    STATUS_FLAG,
    STATUS_PASS,
    compute_verdict,
)

PLACEHOLDER_RE = re.compile(r"<[^<>\n]{1,180}>")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
DAO_SKILL_RE = re.compile(r"\b(?:workflow|bestpractice)_[a-z_]+\b")
REQ_DOC_ANCHOR_RE = re.compile(
    r"(?:req-doc|requirement_doc|requirement-doc)\s*[:=]\s*`?([^`\s]+\.md)",
    re.IGNORECASE,
)
VALID_FINAL_STATUS = ("DONE", "PARTIAL", "BLOCKED")
FACE_STATUS_ALLOWED = frozenset(("unwritten", "filled"))
FACE_NAMES = ("requirement", "meaning", "design")
MEANING_ANCHOR_RE = re.compile(
    r"(?:\b(?:[1-9]|1[0-3])\b|(?:新意义\s*)?[ABC]\b)",
    re.IGNORECASE,
)
LAYER1_FIELDS = (
    ("core_need", re.compile(r"核心问题|\(core_need\)", re.IGNORECASE)),
    ("success_effect", re.compile(r"成功效果|\(success_effect\)", re.IGNORECASE)),
    ("hard_requirements", re.compile(r"硬性约束|\(hard_requirements\)", re.IGNORECASE)),
    ("negative_requirements", re.compile(r"明确不做|\(negative_requirements\)", re.IGNORECASE)),
    ("deliverable", re.compile(r"交付物|\(deliverable\)", re.IGNORECASE)),
)

# The marker is deliberately explicit. Documents produced before D9 remain
# readable, but they do not silently acquire the current applicability contract.
D9_CONTRACT_RE = re.compile(r"(?im)^\s*\|\s*d9_contract\s*\|\s*on-demand-v1\s*\|")
D9_LAYER_HEADING_RE = re.compile(
    r"(?:D9.*(?:层适用性|layer\s+applicability)|(?:层适用性|layer\s+applicability).*D9)",
    re.IGNORECASE,
)
D9_REQUIRED_LAYER1_FIELDS = ("success_effect", "negative_requirements")
# `filled` belongs to the independent face_status contract. It is deliberately
# not a D9 layer state, so a current document cannot silently mix the two state
# machines.
D9_ALLOWED_STATES = frozenset(("required", "not_applicable", "unwritten"))
D9_TRIGGER_KEYS: dict[str, tuple[str, ...]] = {
    "Layer 2": (
        "multiple_paths",
        "handoff",
        "user_confirmation",
        "cross_file_impact",
    ),
    "Layer 3": (
        "existing_object_disposition",
        "implementation_writeback",
        "direct_multi_file_execution",
    ),
}
D9_TRIGGER_VALUE_RE = re.compile(
    r"(?P<key>[a-z][a-z0-9_]*)\s*[:=]\s*"
    r"(?P<value>true|false)\b",
    re.IGNORECASE,
)

REGULATOR_PROMPT_TEMPLATE = """You are an independent regulator for design_doc completeness.

Forbidden read:
- Do not use repository files, chat history, hidden reasoning, sibling artifacts, or
  any information outside the DESIGN DOCUMENT below.
- The design document is self-contained: it includes the original requirement.

Task:
1. Judge DC3: does the filled content describe a real design, or does it mostly
   echo the requirement with vague phrases such as "finish the requirement",
   "make it work", "solve this problem", or equivalent?
   Also judge the former DC7 obligation semantically: when the design face
   references existing implementation files, does the document treat the
   implementation's truth as living in those files (design describes, files
   decide), or does it present its own description of existing behavior as an
   authoritative source? Flag only the latter, and only with a concrete line.
   Report such findings in dc3_issues.
2. Judge DC4: for each key Layer 2 decision, is there a real reason and an
   explicit rejected alternative with a reason?
3. Judge DC5: in the Layer 2 section 2.2 "component responsibilities and
   boundaries" table, check semantic responsibility isolation:
   - For each unit, scope_in must be mutually exclusive in substance. Flag
     cases where two units are effectively responsible for the same work.
   - For each unit, scope_out / forbidden_read must name a real read boundary.
     Flag cases where it only restates scope_in in reverse, such as "this unit
     does not do other units' work", without saying what concrete information
     it must not read.
4. Judge DC6 when a "§意义面" is present: does the meaning face explain why this
   design exists / which context gap or root limitation it addresses, or is it
   only a restatement of the requirement or design plan? Also check that the
   design face's core_need can point back to the meaning face instead of drifting
   independently.
5. If any dc3_issues, dc4_issues, dc5_issues, or dc6_issues are non-empty, verdict must be
   FLAG.
6. Be actionable. Name the exact field, decision, unit, or meaning item and cite the document line
   number when possible. Do not answer with only "not enough detail".
7. For DC5, name the concrete unit(s), line number, problem, and fix. Do not
   answer with only "responsibilities are unclear".
8. Output strict JSON only.

JSON schema:
{{
  "verdict": "PASS|FLAG",
  "dc3_issues": [
    {{"field": "field or section name", "line": 0, "problem": "...", "fix": "..."}}
  ],
  "dc4_issues": [
    {{"decision": "decision name", "line": 0, "problem": "...", "fix": "..."}}
  ],
  "dc5_issues": [
    {{"unit": "unit name", "line": 0, "problem": "...", "fix": "..."}}
  ],
  "dc6_issues": [
    {{"field": "meaning item or design link", "line": 0, "problem": "...", "fix": "..."}}
  ],
  "actionable_signal": "one concise paragraph naming the concrete defect",
  "evidence": ["short document excerpt or line reference"]
}}

DESIGN DOCUMENT WITH LINE NUMBERS:
{numbered_document}
"""


@dataclass(frozen=True)
class Heading:
    line: int
    level: int
    title: str
    start_index: int
    end_index: int


@dataclass(frozen=True)
class FaceRange:
    name: str
    heading: Heading
    start_line: int
    end_line: int
    status: str = ""


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    line: int
    section: str
    field: str
    value: str = ""
    severity: str = "ERROR"


@dataclass(frozen=True)
class ShellResult:
    verdict: str
    issues: tuple[Issue, ...]
    placeholder_count: int


@dataclass(frozen=True)
class FillGuideItem:
    """One unfilled placeholder the author must replace before the doc can leave the gate."""

    line: int
    section: str
    field: str
    placeholder: str


@dataclass(frozen=True)
class FillGuideResult:
    """Per-placeholder fill sheet produced by the placeholder-filling mechanism (UP-70)."""

    document_path: str
    placeholder_count: int
    items: tuple[FillGuideItem, ...]


def _absolute(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _load_text(path: Path | str) -> str:
    return _absolute(path).read_text(encoding="utf-8")


def _headings(lines: list[str]) -> tuple[Heading, ...]:
    raw: list[tuple[int, int, str, int]] = []
    for idx, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if match:
            raw.append((idx, len(match.group(1)), match.group(2).strip(), idx + 1))
    headings: list[Heading] = []
    for pos, (idx, level, title, line_no) in enumerate(raw):
        end = len(lines)
        for next_idx, next_level, _next_title, _next_line in raw[pos + 1 :]:
            if next_level <= level:
                end = next_idx
                break
        headings.append(Heading(line_no, level, title, idx, end))
    return tuple(headings)


def _section_for_line(headings: tuple[Heading, ...], line_no: int) -> str:
    candidates = [heading for heading in headings if heading.line <= line_no]
    if not candidates:
        return "document"
    return candidates[-1].title


def _face_name_for_heading(title: str) -> Optional[str]:
    if "§需求面" in title:
        return "requirement"
    if "§意义面" in title:
        return "meaning"
    if "§设计面" in title:
        return "design"
    return None


def _face_ranges(lines: list[str], headings: tuple[Heading, ...]) -> dict[str, FaceRange]:
    starts: list[tuple[int, str, Heading]] = []
    for heading in headings:
        face_name = _face_name_for_heading(heading.title)
        if face_name:
            starts.append((heading.line, face_name, heading))
    starts.sort(key=lambda item: item[0])
    ranges: dict[str, FaceRange] = {}
    for index, (start_line, face_name, heading) in enumerate(starts):
        next_start = starts[index + 1][0] if index + 1 < len(starts) else len(lines) + 1
        ranges[face_name] = FaceRange(
            name=face_name,
            heading=heading,
            start_line=start_line,
            end_line=next_start - 1,
        )
    return ranges


def _face_for_line(face_ranges: dict[str, FaceRange], line_no: int) -> Optional[str]:
    for face_name, face_range in face_ranges.items():
        if face_range.start_line <= line_no <= face_range.end_line:
            return face_name
    return None


def _normalize_face_status(value: str) -> str:
    return value.strip().strip("`").lower()


def _row_value_by_label(
    lines: list[str],
    start_line: int,
    end_line: int,
    label_patterns: tuple[str, ...],
) -> tuple[int, str] | None:
    for idx in range(start_line, end_line + 1):
        if idx < 1 or idx > len(lines):
            continue
        cells = _split_table_row(lines[idx - 1])
        if len(cells) < 2 or _is_table_separator(cells):
            continue
        label = _normalized_header_cell(cells[0])
        if any(pattern in label for pattern in label_patterns):
            return idx, cells[1].strip()
    return None


def _face_status_map(lines: list[str], face_ranges: dict[str, FaceRange]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for face_name, face_range in face_ranges.items():
        row = _row_value_by_label(lines, face_range.start_line, face_range.end_line, ("face_status", "面状态"))
        if row is not None:
            _line_no, value = row
            statuses[face_name] = _normalize_face_status(value)
    return statuses


def _face_body_text(lines: list[str], face_range: FaceRange) -> str:
    start = max(face_range.start_line - 1, 0)
    end = min(face_range.end_line, len(lines))
    return "\n".join(lines[start:end])


def _nearest_heading(headings: tuple[Heading, ...], line_no: int) -> Optional[Heading]:
    candidates = [heading for heading in headings if heading.line <= line_no]
    return candidates[-1] if candidates else None


def _strip_md_label(text: str) -> str:
    value = text.strip().strip("`")
    value = re.sub(r"^[-*]\s*", "", value)
    value = value.strip().strip("`")
    return value


def _split_table_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return ()
    return tuple(cell.strip() for cell in stripped.strip("|").split("|"))


def _is_table_separator(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _field_for_placeholder(line: str, placeholder: str, section: str, heading: Optional[Heading]) -> str:
    cells = _split_table_row(line)
    if cells and not _is_table_separator(cells):
        for index, cell in enumerate(cells):
            if placeholder in cell:
                row_label = _strip_md_label(cells[0]) if cells else ""
                if index == 0:
                    return row_label or section
                return f"{row_label or section} / column {index + 1}"
    if heading:
        match = re.search(r"\(([^)]+)\)", heading.title)
        if match:
            return match.group(1).strip()
    if "：" in line:
        return _strip_md_label(line.split("：", 1)[0])
    if ":" in line:
        return _strip_md_label(line.split(":", 1)[0])
    return section


def _placeholder_issues(lines: list[str], headings: tuple[Heading, ...]) -> tuple[Issue, ...]:
    issues: list[Issue] = []
    face_ranges = _face_ranges(lines, headings)
    face_statuses = _face_status_map(lines, face_ranges)
    use_status_gate = bool(face_statuses)
    for idx, line in enumerate(lines, start=1):
        section = _section_for_line(headings, idx)
        heading = _nearest_heading(headings, idx)
        for match in PLACEHOLDER_RE.finditer(line):
            value = match.group(0)
            face_name = _face_for_line(face_ranges, idx)
            if use_status_gate and face_name and face_statuses.get(face_name) != "filled":
                continue
            issues.append(
                Issue(
                    code="DC1_PLACEHOLDER",
                    message="placeholder remains",
                    line=idx,
                    section=section,
                    field=_field_for_placeholder(line, value, section, heading),
                    value=value,
                )
            )
    return tuple(issues)


def _find_heading(headings: tuple[Heading, ...], pattern: re.Pattern[str]) -> Optional[Heading]:
    for heading in headings:
        if pattern.search(heading.title):
            return heading
    return None


def _content_lines(lines: list[str], heading: Heading) -> tuple[tuple[int, str], ...]:
    return tuple((idx + 1, lines[idx]) for idx in range(heading.start_index + 1, heading.end_index))


def _substantive_text(text: str) -> str:
    value = text.strip()
    if not value or value.startswith(">") or value.startswith("```"):
        return ""
    cells = _split_table_row(value)
    if cells:
        if _is_table_separator(cells):
            return ""
        value = " ".join(cells)
    value = re.sub(r"^[-*]\s*", "", value)
    value = PLACEHOLDER_RE.sub("", value)
    value = value.replace("`", "").strip()
    value = re.sub(r"[\s|:：/、，。；;,.!！?？\-]+", "", value)
    return value


def _section_has_filled_content(lines: list[str], heading: Heading) -> bool:
    return any(_substantive_text(line) for _line_no, line in _content_lines(lines, heading))


def _layer1_issues(
    lines: list[str],
    headings: tuple[Heading, ...],
    required_fields: tuple[str, ...] | None = None,
) -> tuple[Issue, ...]:
    issues: list[Issue] = []
    selected = set(required_fields) if required_fields is not None else None
    for field, pattern in LAYER1_FIELDS:
        if selected is not None and field not in selected:
            continue
        heading = _find_heading(headings, pattern)
        if heading is None:
            issues.append(Issue("DC2_MISSING_LAYER1_FIELD", f"missing Layer 1 field {field}", 0, "Layer 1 功能设计", field))
            continue
        if not _section_has_filled_content(lines, heading):
            issues.append(Issue("DC2_EMPTY_LAYER1_FIELD", f"Layer 1 field {field} is empty", heading.line, heading.title, field))
    return tuple(issues)


def _cell_is_filled(cell: str) -> bool:
    value = cell.strip().strip("`")
    if not value or PLACEHOLDER_RE.search(value):
        return False
    if _is_table_separator((value,)):
        return False
    stripped = re.sub(r"[\s/|:：\-]+", "", value)
    return bool(stripped)


def _decision_table_issues(lines: list[str], headings: tuple[Heading, ...]) -> tuple[Issue, ...]:
    heading = _find_heading(headings, re.compile(r"关键设计决策|含为什么|2\.3"))
    if heading is None:
        return (Issue("DC2_MISSING_DECISION_TABLE", "missing Layer 2 decision table", 0, "Layer 2 实现设计", "decision_table"),)

    real_rows: list[int] = []
    for line_no, line in _content_lines(lines, heading):
        cells = _split_table_row(line)
        if len(cells) < 4 or _is_table_separator(cells):
            continue
        if cells[0] == "决策":
            continue
        if all(_cell_is_filled(cell) for cell in cells[:4]):
            real_rows.append(line_no)
    if real_rows:
        return ()
    return (
        Issue(
            "DC2_EMPTY_DECISION_TABLE",
            "Layer 2 decision table has no filled decision row",
            heading.line,
            heading.title,
            "decision_table",
        ),
    )


def _d9_trigger_values(cell: str, triggers: tuple[str, ...]) -> tuple[dict[str, bool], tuple[str, ...]]:
    """Parse the deliberately small, structural trigger-evaluation grammar."""
    values: dict[str, bool] = {}
    for match in D9_TRIGGER_VALUE_RE.finditer(cell.strip().strip("`")):
        key = match.group("key").lower()
        if key not in triggers:
            continue
        values[key] = match.group("value").lower() == "true"
    missing = tuple(trigger for trigger in triggers if trigger not in values)
    return values, missing


def _d9_layer_issues(lines: list[str], headings: tuple[Heading, ...]) -> tuple[Issue, ...]:
    """Check D9 applicability/state rows without judging the prose reason."""
    heading = _find_heading(headings, D9_LAYER_HEADING_RE)
    if heading is None:
        return (
            Issue(
                "DC2_MISSING_LAYER_APPLICABILITY",
                "current on-demand-v1 document must declare Layer 2 and Layer 3 applicability/state",
                0,
                "D9 layer applicability",
                "layer_applicability",
            ),
        )

    header: tuple[str, ...] = ()
    rows: list[tuple[int, tuple[str, ...]]] = []
    for line_no, line in _content_lines(lines, heading):
        cells = _split_table_row(line)
        if not cells or _is_table_separator(cells):
            continue
        if not header:
            if (
                _column_index(cells, ("layer", "层")) is not None
                and _column_index(cells, ("state", "状态")) is not None
            ):
                header = cells
            continue
        rows.append((line_no, cells))

    layer_index = _column_index(header, ("layer", "层")) if header else None
    state_index = _column_index(header, ("state", "状态")) if header else None
    reason_index = _column_index(header, ("reason", "理由", "原因")) if header else None
    trigger_index = (
        _column_index(header, ("trigger_evaluation", "triggerevaluation", "触发评估"))
        if header
        else None
    )
    if None in (layer_index, state_index, reason_index, trigger_index):
        return (
            Issue(
                "DC2_INVALID_LAYER_APPLICABILITY_TABLE",
                "D9 table must contain layer, state, reason, and trigger_evaluation columns",
                heading.line,
                heading.title,
                "layer_applicability",
            ),
        )

    issues: list[Issue] = []
    found: set[str] = set()
    assert layer_index is not None
    assert state_index is not None
    assert reason_index is not None
    assert trigger_index is not None
    for line_no, cells in rows:
        if len(cells) <= max(layer_index, state_index, reason_index, trigger_index):
            continue
        raw_layer = cells[layer_index].strip().strip("`")
        layer = "Layer 2" if re.search(r"layer\s*2|第\s*二\s*层", raw_layer, re.IGNORECASE) else "Layer 3" if re.search(r"layer\s*3|第\s*三\s*层", raw_layer, re.IGNORECASE) else ""
        if not layer:
            continue
        if layer in found:
            issues.append(Issue("DC2_DUPLICATE_LAYER_APPLICABILITY", "D9 layer row is duplicated", line_no, heading.title, layer, raw_layer))
            continue
        found.add(layer)
        state = cells[state_index].strip().strip("`").lower()
        if state not in D9_ALLOWED_STATES:
            issues.append(Issue("DC2_LAYER_STATE_INVALID", "D9 layer state must be required, not_applicable, or unwritten; filled belongs only to face_status", line_no, heading.title, f"{layer} state", state))
            continue
        reason = cells[reason_index]
        trigger_cell = cells[trigger_index]
        trigger_values, missing = _d9_trigger_values(trigger_cell, D9_TRIGGER_KEYS[layer])
        if missing:
            issues.append(Issue("DC2_LAYER_TRIGGER_EVALUATION_MISSING", "D9 row must evaluate every named trigger", line_no, heading.title, f"{layer} trigger_evaluation", ",".join(missing)))
        if state == "unwritten":
            issues.append(Issue("DC2_LAYER_STATE_UNWRITTEN", "D9 layer applicability/state remains unwritten", line_no, heading.title, f"{layer} state", state))
            continue
        if state == "not_applicable":
            if not _substantive_text(reason):
                issues.append(Issue("DC2_NOT_APPLICABLE_REASON_MISSING", "not_applicable requires a substantive reason", line_no, heading.title, f"{layer} reason"))
            active = tuple(key for key, value in trigger_values.items() if value)
            if active:
                issues.append(Issue("DC2_LAYER_NOT_APPLICABLE_TRIGGERED", "not_applicable conflicts with an active trigger", line_no, heading.title, f"{layer} state", ",".join(active)))
        if state == "required":
            active = tuple(key for key, value in trigger_values.items() if value)
            if not active:
                issues.append(
                    Issue(
                        "DC2_REQUIRED_WITHOUT_ACTIVE_TRIGGER",
                        "required requires at least one named trigger=true",
                        line_no,
                        heading.title,
                        f"{layer} state / trigger_evaluation",
                        "state=required; active_trigger=none",
                    )
                )

    for layer in D9_TRIGGER_KEYS:
        if layer not in found:
            issues.append(Issue("DC2_MISSING_LAYER_APPLICABILITY_ROW", "D9 table must contain one row for each conditional layer", heading.line, heading.title, layer))

    # A required state must expose the corresponding structural layer.
    for layer in D9_TRIGGER_KEYS:
        matching = next(
            (cells for line_no, cells in rows if len(cells) > layer_index and re.search(rf"layer\s*{layer[-1]}|第\s*{'二' if layer == 'Layer 2' else '三'}\s*层", cells[layer_index], re.IGNORECASE)),
            None,
        )
        if matching is None:
            continue
        current_state = matching[state_index].strip().strip("`").lower()
        if current_state != "required":
            continue
        if layer == "Layer 2":
            issues.extend(_decision_table_issues(lines, headings))
        else:
            issues.extend(_layer3_issues(lines, headings))
    return tuple(issues)


def _layer3_issues(lines: list[str], headings: tuple[Heading, ...]) -> tuple[Issue, ...]:
    heading = _find_heading(headings, re.compile(r"^Layer\s*3|代码改动清单", re.IGNORECASE))
    if heading is None:
        return (Issue("DC2_MISSING_LAYER3_CONTENT", "required Layer 3 state has no code-change list", 0, "Layer 3 代码改动清单", "layer3"),)
    expected = (
        ("ADDED", re.compile(r"新增|ADDED", re.IGNORECASE)),
        ("MODIFIED", re.compile(r"修改|MODIFIED", re.IGNORECASE)),
        ("REMOVED", re.compile(r"删除|REMOVED", re.IGNORECASE)),
    )
    issues: list[Issue] = []
    for field, pattern in expected:
        subheading = _find_heading(headings, pattern)
        if subheading is None or not _section_has_filled_content(lines, subheading):
            line = subheading.line if subheading is not None else heading.line
            issues.append(Issue("DC2_EMPTY_LAYER3_FIELD", f"required Layer 3 field {field} is missing or empty", line, heading.title, field))
    return tuple(issues)


def _known_dao_skills() -> Optional[frozenset[str]]:
    try:
        text = DAO_ROUTING.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"warning: failed to read DAO skill routing: {exc}", file=sys.stderr)
        return None
    return frozenset(DAO_SKILL_RE.findall(text))


def _normalized_header_cell(cell: str) -> str:
    return re.sub(r"[\s`*()（）/]+", "", cell).lower()


def _column_index(cells: tuple[str, ...], names: tuple[str, ...]) -> Optional[int]:
    for index, cell in enumerate(cells):
        normalized = _normalized_header_cell(cell)
        if any(name in normalized for name in names):
            return index
    return None


def _table_with_column(
    lines: list[str],
    heading: Heading,
    column_name: str,
) -> tuple[tuple[str, ...], tuple[tuple[int, tuple[str, ...]], ...]]:
    header: tuple[str, ...] = ()
    rows: list[tuple[int, tuple[str, ...]]] = []
    for line_no, line in _content_lines(lines, heading):
        cells = _split_table_row(line)
        if not cells or _is_table_separator(cells):
            continue
        if not header and _column_index(cells, (column_name,)) is not None:
            header = cells
            continue
        if header:
            rows.append((line_no, cells))
    return header, tuple(rows)


def _dc5_unknown_skill_issue(line_no: int, section: str, value: str) -> Issue:
    return Issue(
        "DC5_SKILL_INJECTION_UNKNOWN",
        "skill_injection value is not listed in _DAO_ROUTING.md",
        line_no,
        section,
        "skill_injection",
        value,
    )


def _dc5_forbidden_empty_issue(line_no: int, section: str, value: str) -> Issue:
    return Issue(
        "DC5_FORBIDDEN_READ_EMPTY",
        "scope_out / forbidden_read cell must be filled when skill_injection is declared",
        line_no,
        section,
        "scope_out / forbidden_read",
        value,
    )


def _skill_injection_issues(
    lines: list[str],
    headings: tuple[Heading, ...],
) -> tuple[Issue, ...]:
    heading = _find_heading(headings, re.compile(r"组件职责|2\.2|scope_in", re.IGNORECASE))
    if heading is None:
        return ()
    header, rows = _table_with_column(lines, heading, "skill_injection")
    if not header:
        return ()
    skill_index = _column_index(header, ("skill_injection",))
    forbidden_index = _column_index(header, ("scope_out", "forbidden_read", "禁读"))
    if skill_index is None:
        return ()
    known_skills = _known_dao_skills()
    issues: list[Issue] = []
    for line_no, cells in rows:
        skill_cell = cells[skill_index].strip() if len(cells) > skill_index else ""
        if (
            known_skills is not None
            and not PLACEHOLDER_RE.search(skill_cell)
            and skill_cell
            and skill_cell not in known_skills
        ):
            issues.append(_dc5_unknown_skill_issue(line_no, heading.title, skill_cell))
        forbidden_cell = (
            cells[forbidden_index]
            if forbidden_index is not None and len(cells) > forbidden_index
            else ""
        )
        if (
            not PLACEHOLDER_RE.search(forbidden_cell)
            and not _cell_is_filled(forbidden_cell)
        ):
            issues.append(_dc5_forbidden_empty_issue(line_no, heading.title, forbidden_cell))
    return tuple(issues)


def _requirement_anchor_issues(
    lines: list[str],
    headings: tuple[Heading, ...],
    document_path: Path | None = None,
    current_contract: bool = False,
) -> tuple[Issue, ...]:
    heading = _find_heading(headings, re.compile(r"^\(0\)|原始需求锚|需求文档锚"))
    if heading is None:
        return (
            Issue(
                "DC0_REQUIREMENT_ANCHOR_MISSING" if current_contract else "DC0_REQUIREMENT_ANCHOR_LEGACY",
                "current on-demand-v1 document has no §0 requirement_doc anchor" if current_contract else "legacy design doc has no §0 requirement_doc anchor",
                0,
                "document",
                "req-doc",
                severity="ERROR" if current_contract else "WARNING",
            ),
        )
    body = "\n".join(line for _line_no, line in _content_lines(lines, heading))
    match = REQ_DOC_ANCHOR_RE.search(body)
    if not match:
        severity = "ERROR" if current_contract or "req-doc" in body.lower() or "需求锚" in heading.title else "WARNING"
        return (
            Issue(
                "DC0_REQUIREMENT_ANCHOR_MISSING" if severity == "ERROR" else "DC0_REQUIREMENT_ANCHOR_LEGACY",
                "§0 does not contain a req-doc path anchor",
                heading.line,
                heading.title,
                "req-doc",
                severity=severity,
            ),
        )
    if document_path is None:
        return ()
    req_doc = Path(match.group(1)).expanduser()
    if not req_doc.is_absolute():
        req_doc = (document_path.parent / req_doc).resolve()
        if not req_doc.exists():
            req_doc = (WORKSPACE_ROOT / match.group(1)).resolve()
    if not req_doc.exists():
        return (
            Issue(
                "DC0_REQUIREMENT_ANCHOR_NOT_FOUND",
                "req-doc anchor path does not exist",
                heading.line,
                heading.title,
                "req-doc",
                str(req_doc),
            ),
        )
    return ()


def _dc6_issue(code: str, message: str, line: int, section: str, field: str, value: str = "") -> Issue:
    return Issue(code, message, line, section, field, value)


def _has_face_scaffold(lines: list[str], headings: tuple[Heading, ...]) -> bool:
    if any(_face_name_for_heading(heading.title) for heading in headings):
        return True
    return any("face_status" in line or "面状态" in line for line in lines)


def _face_label_issues(lines: list[str], face_range: FaceRange) -> tuple[Issue, ...]:
    body = _face_body_text(lines, face_range)
    issues: list[Issue] = []
    if "设计需求" not in body:
        issues.append(
            _dc6_issue(
                "DC6_FACE_LABEL_MISSING",
                "face must carry a design requirement label",
                face_range.heading.line,
                face_range.heading.title,
                "设计需求",
            )
        )
    if "执行需求" not in body:
        issues.append(
            _dc6_issue(
                "DC6_FACE_LABEL_MISSING",
                "face must carry an execution requirement label",
                face_range.heading.line,
                face_range.heading.title,
                "执行需求",
            )
        )
    return tuple(issues)


def _meaning_pointer_issues(lines: list[str], face_range: FaceRange, status: str) -> tuple[Issue, ...]:
    issues: list[Issue] = []
    pointer_row = _row_value_by_label(lines, face_range.start_line, face_range.end_line, ("承接总领意义",))
    if pointer_row is None or "CROSS_DOMAIN_MEANING.md" not in pointer_row[1]:
        issues.append(
            _dc6_issue(
                "DC6_MEANING_POINTER_MISSING",
                "meaning face must include a CROSS_DOMAIN_MEANING.md anchor slot",
                face_range.heading.line,
                face_range.heading.title,
                "承接总领意义",
            )
        )
        return tuple(issues)
    line_no, value = pointer_row
    if status == "filled":
        normalized = value.strip().strip("`")
        if (
            not normalized
            or PLACEHOLDER_RE.search(normalized)
            or normalized.lower() in {"missing", "unwritten"}
            or not MEANING_ANCHOR_RE.search(normalized)
        ):
            issues.append(
                _dc6_issue(
                    "DC6_MEANING_POINTER_INVALID",
                    "filled meaning face must point to CROSS_DOMAIN_MEANING.md item 1-13 or A/B/C",
                    line_no,
                    face_range.heading.title,
                    "承接总领意义",
                    value,
                )
            )
    return tuple(issues)


def _meaning_structure_issues(lines: list[str], face_range: FaceRange) -> tuple[Issue, ...]:
    body = _face_body_text(lines, face_range)
    issues: list[Issue] = []
    for item in ("M1", "M2", "M3", "M4", "M5"):
        if item not in body:
            issues.append(
                _dc6_issue(
                    "DC6_MEANING_FIELD_MISSING",
                    f"meaning face must include {item}",
                    face_range.heading.line,
                    face_range.heading.title,
                    item,
                )
            )
    return tuple(issues)


def _meaning_face_issues(lines: list[str], headings: tuple[Heading, ...]) -> tuple[Issue, ...]:
    if not _has_face_scaffold(lines, headings):
        return ()
    face_ranges = _face_ranges(lines, headings)
    statuses = _face_status_map(lines, face_ranges)
    issues: list[Issue] = []
    for face_name in FACE_NAMES:
        face_range = face_ranges.get(face_name)
        if face_range is None:
            issues.append(
                _dc6_issue(
                    "DC6_FACE_MISSING",
                    f"tri-face scaffold is missing {face_name} face",
                    0,
                    "document",
                    face_name,
                )
            )
            continue
        status = statuses.get(face_name, "")
        if not status:
            issues.append(
                _dc6_issue(
                    "DC6_FACE_STATUS_MISSING",
                    "face_status row is required",
                    face_range.heading.line,
                    face_range.heading.title,
                    "face_status",
                )
            )
        elif status not in FACE_STATUS_ALLOWED:
            issues.append(
                _dc6_issue(
                    "DC6_FACE_STATUS_INVALID",
                    "face_status must be unwritten or filled",
                    face_range.heading.line,
                    face_range.heading.title,
                    "face_status",
                    status,
                )
            )
        issues.extend(_face_label_issues(lines, face_range))
    meaning_range = face_ranges.get("meaning")
    if meaning_range is not None:
        meaning_status = statuses.get("meaning", "")
        issues.extend(_meaning_pointer_issues(lines, meaning_range, meaning_status))
        issues.extend(_meaning_structure_issues(lines, meaning_range))
    return tuple(issues)


def _status_value_is_chosen(value: str) -> bool:
    normalized = value.strip().strip("`")
    if not normalized or PLACEHOLDER_RE.search(normalized):
        return False
    upper = normalized.upper()
    if all(status in upper for status in VALID_FINAL_STATUS) and "/" in upper:
        return False
    return bool(re.match(r"^(DONE|PARTIAL|BLOCKED)\b", upper))


def _final_boundary_issues(lines: list[str], headings: tuple[Heading, ...]) -> tuple[Issue, ...]:
    heading = _find_heading(headings, re.compile(r"^Final Boundary$", re.IGNORECASE))
    if heading is None:
        return (Issue("DC2_MISSING_FINAL_BOUNDARY", "missing Final Boundary section", 0, "Final Boundary", "状态"),)
    status_rows: list[tuple[int, str]] = []
    for line_no, line in _content_lines(lines, heading):
        cells = _split_table_row(line)
        if len(cells) >= 2 and cells[0].strip() == "状态":
            status_rows.append((line_no, cells[1]))
    if not status_rows:
        return (Issue("DC2_MISSING_FINAL_STATUS", "Final Boundary status row is missing", heading.line, heading.title, "状态"),)
    line_no, value = status_rows[0]
    if not _status_value_is_chosen(value):
        return (
            Issue(
                "DC2_EMPTY_FINAL_STATUS",
                "Final Boundary status must choose DONE, PARTIAL, or BLOCKED",
                line_no,
                heading.title,
                "状态",
                value,
            ),
        )
    return ()


def _full_issue_set(text: str, document_path: Path | None = None) -> tuple[Issue, ...]:
    lines = text.splitlines()
    headings = _headings(lines)
    current_contract = bool(D9_CONTRACT_RE.search(text))
    return (
        _requirement_anchor_issues(lines, headings, document_path, current_contract=current_contract)
        + _placeholder_issues(lines, headings)
        + _layer1_issues(
            lines,
            headings,
            required_fields=D9_REQUIRED_LAYER1_FIELDS if current_contract else None,
        )
        + (_d9_layer_issues(lines, headings) if current_contract else _decision_table_issues(lines, headings))
        + _skill_injection_issues(lines, headings)
        + _meaning_face_issues(lines, headings)
        + _final_boundary_issues(lines, headings)
    )


def scan_flagging_issues(text: str, document_path: Path | None = None) -> tuple[Issue, ...]:
    """Return exactly the issues that make ``scan_text`` return FLAG.

    Exposed as a stable interface so downstream gates (e.g. landing_gate) can fold
    design-doc completeness into their own verdict without duplicating the
    severity filtering or the DC1-DC5 detector composition.
    """
    return tuple(issue for issue in _full_issue_set(text, document_path) if issue.severity != "WARNING")


def scan_text(text: str, document_path: Path | None = None) -> ShellResult:
    issues = _full_issue_set(text, document_path)
    error_issues = tuple(issue for issue in issues if issue.severity != "WARNING")
    return ShellResult(
        verdict="FLAG" if error_issues else "PASS",
        issues=issues,
        placeholder_count=sum(1 for issue in error_issues if issue.code == "DC1_PLACEHOLDER"),
    )


def scan_file(path: Path | str) -> ShellResult:
    abs_path = _absolute(path)
    return scan_text(_load_text(abs_path), abs_path)


class DesignDocCompletenessShell(DeterministicShell):
    """DeterministicShell adapter for design_doc DC checks."""

    def __init__(self) -> None:
        self.result: Optional[ShellResult] = None

    def run_checks(self, artifact_path: Path, text: str) -> list[Finding]:
        self.result = scan_text(text, artifact_path)
        findings = [_finding_from_issue(issue) for issue in self.result.issues if issue.severity != "WARNING"]
        return findings or [Finding("DC", STATUS_PASS, "", "")]


def _finding_from_issue(issue: Issue) -> Finding:
    anchor = f"line {issue.line}" if issue.line else issue.section
    return Finding(
        check_id=issue.code.split("_", 1)[0],
        status=STATUS_FLAG,
        line_anchor=anchor,
        message=f"{issue.code}: {issue.message}",
    )


def build_fill_guide(text: str, document_path: Path | None = None) -> FillGuideResult:
    """Produce a per-placeholder fill sheet (UP-70 占位符填充机制).

    For every remaining ``<...>`` placeholder, report the line, markdown section,
    inferred field/row label, and the literal placeholder value. The sheet is the
    deterministic half of the filling mechanism: it tells the author exactly what
    to replace and where, without writing the content for them. Run it, fill every
    item, then rerun ``scan_text`` (or the gate) until the placeholder count is 0.
    """
    lines = text.splitlines()
    headings = _headings(lines)
    items: list[FillGuideItem] = []
    for idx, line in enumerate(lines, start=1):
        section = _section_for_line(headings, idx)
        heading = _nearest_heading(headings, idx)
        for match in PLACEHOLDER_RE.finditer(line):
            placeholder = match.group(0)
            items.append(
                FillGuideItem(
                    line=idx,
                    section=section,
                    field=_field_for_placeholder(line, placeholder, section, heading),
                    placeholder=placeholder,
                )
            )
    return FillGuideResult(
        document_path=str(document_path) if document_path else "",
        placeholder_count=len(items),
        items=tuple(items),
    )


def build_fill_guide_for_file(path: Path | str) -> FillGuideResult:
    return build_fill_guide(_load_text(path), _absolute(path))


def _numbered_document(text: str) -> str:
    return "\n".join(f"{idx:04d}: {line}" for idx, line in enumerate(text.splitlines(), start=1))


def _strip_code_fences(text: str) -> str:
    """Drop a leading ```json / ``` fence and its closing ``` when the model wraps
    its reply in a markdown code block. Brace scanning already tolerates fences, but
    stripping first makes the "prose vs truncated" distinction below unambiguous."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^\s*```[^\n]*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped


def _top_level_json_spans(text: str) -> list[str]:
    """Return every top-level ``{...}`` span in order, tolerating braces inside
    strings. Unlike a first-brace scan this survives prose that carries a stray
    ``{`` before the real object, and lets the caller pick the span that actually
    holds the verdict rather than the first balanced pair it stumbles on."""
    spans: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for idx, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    spans.append(text[start : idx + 1])
                    start = -1
    return spans


def _select_regulator_object(spans: list[str]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Pick the JSON object that carries the regulator verdict.

    Prefers a span that parses to an object AND holds ``verdict`` or a
    ``dcN_issues`` key, so a stray ``{...}`` in the model's preamble never shadows
    the real payload. Falls back to the first parseable object, then to the last
    decode error seen."""
    fallback: Optional[dict[str, Any]] = None
    decode_error: Optional[str] = None
    verdict_keys = ("verdict", "dc3_issues", "dc4_issues", "dc5_issues", "dc6_issues")
    for span in spans:
        try:
            candidate = json.loads(span)
        except json.JSONDecodeError as exc:
            decode_error = f"json_decode_error:{exc}"
            continue
        if not isinstance(candidate, dict):
            continue
        if fallback is None:
            fallback = candidate
        if any(key in candidate for key in verdict_keys):
            return candidate, None
    if fallback is not None:
        return fallback, None
    return None, decode_error or "json_root_not_object"


def parse_regulator_json(raw_text: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    text = _strip_code_fences(raw_text or "")
    spans = _top_level_json_spans(text)
    if not spans:
        # Separate an empty / pure-prose body (no object at all) from a truncated
        # one (an object opened but the output was cut before it closed). Both are
        # parse failures the retry path handles, but the reason must name what
        # actually happened instead of a blanket "no_json_object_found".
        return None, "truncated_json" if "{" in text else "no_json_object_found"
    parsed, error = _select_regulator_object(spans)
    if parsed is None:
        return None, error
    verdict = str(parsed.get("verdict", "")).upper()
    if verdict == "FAIL":
        parsed["verdict"] = "FLAG"
    elif any(
        _json_issue_list_has_items(parsed, key)
        for key in ("dc3_issues", "dc4_issues", "dc5_issues", "dc6_issues")
    ):
        parsed["verdict"] = "FLAG"
    elif verdict not in {"PASS", "FLAG"}:
        return parsed, "missing_or_invalid_verdict"
    return parsed, None


def _json_issue_list_has_items(parsed: dict[str, Any], key: str) -> bool:
    value = parsed.get(key)
    return isinstance(value, list) and bool(value)


def _regulator_issue_lists_have_items(regulator: dict[str, Any]) -> bool:
    return any(
        _json_issue_list_has_items(regulator, key)
        for key in ("dc3_issues", "dc4_issues", "dc5_issues", "dc6_issues")
    )


# Regulator runner returns this status once a channel actually delivered model
# text under a custom response_contract; any other status means the dispatch
# ladder was exhausted WITHOUT model output (import error, all channels failed,
# timeout, refusal) — a dispatch failure, not a parser failure.
REGULATOR_RAW_DELIVERED = "RAW_DELIVERED"
DEFAULT_REGULATOR_LADDER = ("codex:high", "claude-zai:high", "claude-kimi:medium")
MAX_REGULATOR_ATTEMPTS = 3
STRICT_JSON_REMINDER = (
    "\n\nSTRICT OUTPUT: reply with the JSON object only — no prose before or after, "
    "no markdown code fences. The first character of your reply must be '{' and the "
    "last must be '}'."
)
# Reason fragments that mark a retry as worth escalating to the next tier rather
# than aborting (a deterministic import error is not in here on purpose).
_TRANSIENT_REASON_MARKERS = (
    "timeout", "rate", "429", "temporar", "connection", "reset",
    "unavailable", "overload", "throttl", "quota",
)


@dataclass(frozen=True)
class RegulatorAttempt:
    """One tier attempt inside run_regulator_for_text's degradation loop."""

    tier: str
    kind: str  # "parsed" | "parse_failed" | "dispatch_failed"
    reason: str
    raw_text_len: int


def _regulator_ladder(primary: str) -> tuple[str, ...]:
    """Order the tiers to try: the requested one first, then the rest of the
    default ladder, de-duplicated. Degradation walks this list on failure."""
    ordered = [primary, *(tier for tier in DEFAULT_REGULATOR_LADDER if tier != primary)]
    seen: set[str] = set()
    out: list[str] = []
    for tier in ordered:
        if tier and tier not in seen:
            seen.add(tier)
            out.append(tier)
    return tuple(out)


def _reason_looks_transient(reason: str) -> bool:
    low = (reason or "").lower()
    return any(marker in low for marker in _TRANSIENT_REASON_MARKERS)


def _invoke_unified_regulator(prompt: str, tier: str, timeout_seconds: int) -> Any:
    """One regulator dispatch through the unified runner. Isolated as a module
    attribute so tests can substitute it without a live model call."""
    from tools.infra_core.regulator_runner import run_regulator as run_unified_regulator

    return run_unified_regulator(
        prompt,
        must_read=["design_doc_check_completeness supplied DESIGN DOCUMENT block"],
        forbidden_read=[
            "repository files outside the supplied DESIGN DOCUMENT",
            "chat history",
            "reviewed agent success narrative",
        ],
        tier=tier,
        timeout=timeout_seconds,
        response_contract=REGULATOR_RESPONSE_CONTRACT,
    )


_regulator_invoker = _invoke_unified_regulator


def _regulator_failure_hint(kind: str, reason: str) -> str:
    low = (reason or "").lower()
    if kind == "dispatch_failed":
        base = (
            "regulator dispatch failed before the model could answer — this is an "
            "environment / dispatch error, not a defect in the reviewed document."
        )
        if "uniontype" in low or sys.version_info < (3, 10):
            return (
                base + " The dispatch chain imports types.UnionType (needs Python "
                ">=3.10); re-run with the repo interpreter (/opt/homebrew/bin/python3 "
                "or the project .venv)."
            )
        return base + " Inspect the attempt reason above and rerun from the main environment."
    if kind == "parse_failed":
        return (
            "the regulator returned text but no parseable JSON after every fallback "
            "tier; inspect raw_text and consider a different --regulator-tier."
        )
    return "regulator produced no verdict; treated as FLAG (fail-closed)."


def _success_regulator_result(
    verdict_obj: Any, parsed: dict[str, Any], raw_text: str, attempts: tuple[RegulatorAttempt, ...]
) -> dict[str, Any]:
    return {
        "runner": verdict_obj.as_dict(),
        "raw_text": raw_text,
        "parsed": parsed,
        "parse_error": None,
        "dc3_issues": parsed.get("dc3_issues", []),
        "dc4_issues": parsed.get("dc4_issues", []),
        "dc5_issues": parsed.get("dc5_issues", []),
        "dc6_issues": parsed.get("dc6_issues", []),
        "verdict": parsed.get("verdict"),
        "attempts": [asdict(attempt) for attempt in attempts],
        "degraded": False,
        "failure_kind": None,
        "failure_reason": None,
        "hint": None,
    }


def _degraded_regulator_result(
    verdict_obj: Any, raw_text: str, reason: str, attempts: tuple[RegulatorAttempt, ...]
) -> dict[str, Any]:
    kind = attempts[-1].kind if attempts else "dispatch_failed"
    return {
        "runner": verdict_obj.as_dict() if verdict_obj is not None else None,
        "raw_text": raw_text,
        "parsed": None,
        # Keep parse_error populated only for a genuine parse failure so downstream
        # readers are not told "parser error" for a dispatch failure ever again.
        "parse_error": reason if kind == "parse_failed" else None,
        "dc3_issues": [],
        "dc4_issues": [],
        "dc5_issues": [],
        "dc6_issues": [],
        "verdict": "UNKNOWN",
        "attempts": [asdict(attempt) for attempt in attempts],
        "degraded": True,
        "failure_kind": kind,
        "failure_reason": reason or "regulator produced no parseable verdict",
        "hint": _regulator_failure_hint(kind, reason),
    }


def run_regulator_for_text(
    document_text: str,
    regulator_tier: str = "claude-zai:high",
    timeout_seconds: int = 600,
    task: str | None = None,
    max_attempts: int = MAX_REGULATOR_ATTEMPTS,
) -> dict[str, Any]:
    """Run the DC3-DC6 regulator with a bounded retry / tier-degradation path.

    Attempt the requested tier; on a delivered-but-unparseable reply, retry the
    next ladder tier with a stricter JSON-only reminder; on a dispatch failure
    (no model text), surface the runner's real reason instead of mislabeling an
    empty body as a JSON parse error, and stop unless the reason looks transient.
    Returns a dict whose legacy keys (verdict / parsed / parse_error / dcN_issues /
    runner / raw_text) are unchanged, plus attempts / degraded / failure_kind /
    failure_reason / hint for diagnosability."""
    if timeout_seconds < 600:
        raise ValueError("timeout_seconds must be >= 600 for model calls")
    base_prompt = REGULATOR_PROMPT_TEMPLATE.format(numbered_document=_numbered_document(document_text))
    tiers = _regulator_ladder(regulator_tier)
    previous_task = os.environ.get("TODO_ID")
    attempts: list[RegulatorAttempt] = []
    last_verdict_obj: Any = None
    last_raw = ""
    last_reason = ""
    try:
        if task:
            os.environ["TODO_ID"] = task.strip().upper()
        use_strict = False
        for tier in tiers[: max(1, int(max_attempts))]:
            prompt = base_prompt + (STRICT_JSON_REMINDER if use_strict else "")
            try:
                verdict_obj = _regulator_invoker(prompt, tier, timeout_seconds)
            except Exception as exc:  # noqa: BLE001 — dispatch import/runtime error must not crash the gate
                last_reason = f"{type(exc).__name__}: {exc}"
                attempts.append(RegulatorAttempt(tier, "dispatch_failed", last_reason, 0))
                if _reason_looks_transient(last_reason):
                    use_strict = False
                    continue
                break
            last_verdict_obj = verdict_obj
            status = str(getattr(verdict_obj, "status", "") or "")
            raw_text = str(getattr(verdict_obj, "raw_text", "") or "")
            runner_reason = str(getattr(verdict_obj, "reason", "") or "")
            if status != REGULATOR_RAW_DELIVERED:
                # The runner exhausted its own channel ladder without delivering
                # model text. Escalating to the next tier here would re-run the
                # same broken environment, so only continue for transient reasons.
                last_raw, last_reason = raw_text, runner_reason or status or "dispatch_failed"
                attempts.append(RegulatorAttempt(tier, "dispatch_failed", last_reason, len(raw_text)))
                if _reason_looks_transient(last_reason):
                    use_strict = False
                    continue
                break
            parsed, parse_error = parse_regulator_json(raw_text)
            if parse_error is None and parsed is not None:
                attempts.append(RegulatorAttempt(tier, "parsed", "", len(raw_text)))
                return _success_regulator_result(verdict_obj, parsed, raw_text, tuple(attempts))
            last_raw, last_reason = raw_text, parse_error or "unparseable"
            attempts.append(RegulatorAttempt(tier, "parse_failed", last_reason, len(raw_text)))
            use_strict = True
        return _degraded_regulator_result(last_verdict_obj, last_raw, last_reason, tuple(attempts))
    finally:
        if task:
            if previous_task is None:
                os.environ.pop("TODO_ID", None)
            else:
                os.environ["TODO_ID"] = previous_task


REGULATOR_RESPONSE_CONTRACT = """{
  "verdict": "PASS|FLAG",
  "dc3_issues": [
    {"field": "field or section name", "line": 0, "problem": "...", "fix": "..."}
  ],
  "dc4_issues": [
    {"decision": "decision name", "line": 0, "problem": "...", "fix": "..."}
  ],
  "dc5_issues": [
    {"unit": "unit name", "line": 0, "problem": "...", "fix": "..."}
  ],
  "dc6_issues": [
    {"field": "meaning item or design link", "line": 0, "problem": "...", "fix": "..."}
  ],
  "actionable_signal": "one concise paragraph naming the concrete defect",
  "evidence": ["short document excerpt or line reference"]
}"""


def _shell_to_human(result: ShellResult, path: Path) -> str:
    lines = [f"document: {path}", f"shell_verdict: {result.verdict}", f"placeholder_count: {result.placeholder_count}"]
    if not result.issues:
        lines.append("issues: -")
        return "\n".join(lines)
    lines.append("issues:")
    for issue in result.issues:
        location = f"line {issue.line}" if issue.line else "line ?"
        value = f" value={issue.value}" if issue.value else ""
        lines.append(
            f"- {issue.code} {location} severity={issue.severity} section={issue.section} field={issue.field}: {issue.message}{value}"
        )
    if any(issue.code == "DC1_PLACEHOLDER" for issue in result.issues):
        lines.append(
            "hint: run `python3 tools/design_doc/check_completeness.py <doc> --fill-guide` for a per-placeholder fill sheet"
        )
    return "\n".join(lines)


def _receipt_meta(task: str | None = None) -> dict[str, str]:
    meta = {"source": "self_instrument"}
    if task:
        meta["task_id"] = task.strip().upper()
    ledger = os.environ.get("TOOL_RECEIPTS_LEDGER")
    if ledger:
        meta["ledger_path"] = ledger
    return meta


def record_receipt_best_effort(args_summary: dict[str, Any], exit_code: int, task: str | None = None) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("TOOL_RECEIPTS_LEDGER"):
        return
    try:
        if str(WORKSPACE_ROOT) not in sys.path:
            sys.path.insert(0, str(WORKSPACE_ROOT))
        from tools.tool_receipts import record

        record("design_doc_check_completeness", args_summary, exit_code, meta=_receipt_meta(task))
    except Exception as exc:  # pragma: no cover - receipt failure must not affect tool behavior
        print(f"warning: failed to record tool receipt: {exc}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check design_doc completeness")
    parser.add_argument("document", help="Path to a design document markdown file")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human text")
    parser.add_argument("--fill-guide", action="store_true", help="Emit a per-placeholder fill sheet and exit 0 (UP-70 placeholder-filling mechanism)")
    parser.add_argument("--regulator", action="store_true", help="Run DC3/DC4 regulator through cli_agent")
    parser.add_argument("--regulator-tier", default="claude-zai:high", help="cli_agent primary tier")
    parser.add_argument("--timeout", type=int, default=600, help="Model subprocess timeout seconds")
    parser.add_argument("--task", help="Task ID to stamp into the tool receipt")
    return parser


def _fill_guide_to_human(guide: FillGuideResult) -> str:
    lines = [
        f"document: {guide.document_path or '-'}",
        f"placeholder_count: {guide.placeholder_count}",
    ]
    if not guide.items:
        lines.append("fill_guide: - (no placeholders remain)")
        return "\n".join(lines)
    lines.append("fill_guide:")
    for item in guide.items:
        lines.append(
            f"- [line {item.line}] {item.section} / {item.field}: {item.placeholder}"
        )
        lines.append("    -> replace with the concrete content this field asks for")
    return "\n".join(lines)


def main(argv: Optional[tuple[str, ...]] = None) -> int:
    args = _build_parser().parse_args(argv)
    args_summary = {
        "document": args.document,
        "regulator": args.regulator,
        "json": args.json,
        "fill_guide": args.fill_guide,
    }
    path = _absolute(args.document)
    try:
        text = _load_text(path)
        if args.fill_guide:
            guide = build_fill_guide(text, path)
            payload = {
                "document": str(path),
                "fill_guide": asdict(guide),
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(_fill_guide_to_human(guide))
            record_receipt_best_effort(args_summary, 0, args.task)
            return 0
        shell_adapter = DesignDocCompletenessShell()
        findings = shell_adapter.run_checks(path, text)
        shell = shell_adapter.result
        if shell is None:
            raise RuntimeError("design_doc completeness shell did not produce a result")
        regulator = None
        if args.regulator:
            regulator = run_regulator_for_text(text, args.regulator_tier, args.timeout, task=args.task)
        regulator_for_verdict = (
            {
                **regulator,
                "status": "FLAG"
                if _regulator_issue_lists_have_items(regulator)
                else regulator.get("verdict"),
            }
            if isinstance(regulator, dict)
            else None
        )
        gate_verdict = compute_verdict(findings, regulator_for_verdict, use_regulator=regulator is not None)
        final_verdict = gate_verdict.final_status
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        exit_code = 2
        record_receipt_best_effort(args_summary, exit_code, args.task)
        return exit_code

    payload = {
        "document": str(path),
        "shell": asdict(shell),
        "regulator": regulator,
        "final_verdict": final_verdict,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_shell_to_human(shell, path))
        if regulator is not None:
            print(f"regulator_verdict: {regulator.get('verdict')}")
            if regulator.get("parsed"):
                print(json.dumps(regulator["parsed"], ensure_ascii=False, indent=2))
            else:
                failure_kind = regulator.get("failure_kind")
                if failure_kind:
                    print(f"regulator_failure_kind: {failure_kind}")
                failure_reason = regulator.get("failure_reason") or regulator.get("parse_error")
                if failure_reason:
                    print(f"regulator_failure_reason: {failure_reason}")
                if regulator.get("hint"):
                    print(f"regulator_hint: {regulator.get('hint')}")
                attempts = regulator.get("attempts") or []
                if attempts:
                    trail = "; ".join(
                        f"{a.get('tier')}:{a.get('kind')}({a.get('reason') or '-'})" for a in attempts
                    )
                    print(f"regulator_attempts: {trail}")
                # Legacy line kept only for a genuine parse failure, so anything that
                # grepped regulator_parse_error still sees it when it truly applies.
                if regulator.get("parse_error") and failure_kind == "parse_failed":
                    print(f"regulator_parse_error: {regulator.get('parse_error')}")
    exit_code = 1 if final_verdict == "FLAG" else 0
    record_receipt_best_effort(args_summary, exit_code, args.task)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
