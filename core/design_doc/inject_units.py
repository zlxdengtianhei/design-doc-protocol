#!/usr/bin/env python3
"""Emit reference-only per-unit injection prompts from a design doc §2.2 table."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SECTION_22_RE = re.compile(r"组件职责|2\.2|scope_in", re.IGNORECASE)
SKILL_NAME_RE = re.compile(r"\b(?:workflow|bestpractice)_[a-z_]+\b")
TRUNCATION_LIMIT = 200
TRUNCATION_SUFFIX = "...(原文见设计文档)"


@dataclass(frozen=True)
class Heading:
    line: int
    level: int
    title: str
    start_index: int
    end_index: int


@dataclass(frozen=True)
class UnitInjection:
    unit: str
    scope_in: str
    scope_out: str
    skill_name: str
    skill_path: str | None
    prompt: str
    warnings: tuple[str, ...]


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


def _find_heading(
    headings: tuple[Heading, ...],
    pattern: re.Pattern[str],
) -> Optional[Heading]:
    for heading in headings:
        if pattern.search(heading.title):
            return heading
    return None


def _content_lines(lines: list[str], heading: Heading) -> tuple[tuple[int, str], ...]:
    return tuple(
        (idx + 1, lines[idx])
        for idx in range(heading.start_index + 1, heading.end_index)
    )


def _split_table_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return ()
    return tuple(cell.strip() for cell in stripped.strip("|").split("|"))


def _is_table_separator(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells
    )


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


def _cell(cells: tuple[str, ...], index: Optional[int]) -> str:
    if index is None or len(cells) <= index:
        return ""
    return cells[index].strip()


def _extract_skill_name(cell: str) -> str:
    match = SKILL_NAME_RE.search(cell)
    if match:
        return match.group(0)
    return cell.strip().strip("`")


def _relative_to_workspace(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT))
    except ValueError:
        return str(path.resolve())


def _resolve_skill_path(skill_name: str) -> str | None:
    for pattern in (
        WORKSPACE_ROOT / "rules" / "skills" / f"{skill_name}.md",
        WORKSPACE_ROOT / "rules" / "skills" / "drafts" / f"{skill_name}.md",
    ):
        matches = sorted(pattern.parent.glob(pattern.name))
        if matches:
            return _relative_to_workspace(matches[0])
    return None


def _truncate_cell(text: str) -> str:
    value = " ".join(text.split())
    if len(value) <= TRUNCATION_LIMIT:
        return value
    return f"{value[:TRUNCATION_LIMIT]}{TRUNCATION_SUFFIX}"


def _skill_line(skill_name: str, skill_path: str | None) -> str:
    if skill_path:
        return f"先读方法指导 skill: {skill_path}"
    return f"skill 未找到: {skill_name}"


def _build_prompt(
    doc_path: Path,
    scope_in: str,
    scope_out: str,
    skill_name: str,
    skill_path: str | None,
) -> str:
    return "\n".join(
        (
            f"职责: {scope_in}",
            f"禁读(forbidden_read): {scope_out}",
            _skill_line(skill_name, skill_path),
            (
                "行为边界: 读 "
                f"{doc_path} §1.4 明确不做 与 §2.3 关键设计决策"
            ),
        )
    )


def parse_units(doc_path: Path) -> tuple[UnitInjection, ...]:
    text = _load_text(doc_path)
    lines = text.splitlines()
    heading = _find_heading(_headings(lines), SECTION_22_RE)
    if heading is None:
        raise ValueError("missing §2.2 component responsibility table heading")
    header, rows = _table_with_column(lines, heading, "skill_injection")
    if not header:
        raise ValueError("missing §2.2 table with skill_injection column")

    unit_index = _column_index(header, ("组件", "component", "unit"))
    in_index = _column_index(header, ("scope_in", "职责"))
    out_index = _column_index(header, ("scope_out", "forbidden_read", "禁读"))
    skill_index = _column_index(header, ("skill_injection",))
    if any(index is None for index in (unit_index, in_index, out_index, skill_index)):
        raise ValueError("§2.2 table is missing required unit/scope/skill columns")
    assert unit_index is not None
    assert in_index is not None
    assert out_index is not None
    assert skill_index is not None
    indexes = (unit_index, in_index, out_index, skill_index)
    return tuple(
        _unit_from_cells(doc_path, cells, indexes)
        for _line_no, cells in rows
        if _cell(cells, unit_index)
    )


def _unit_from_cells(
    doc_path: Path,
    cells: tuple[str, ...],
    indexes: tuple[int, int, int, int],
) -> UnitInjection:
    unit_index, in_index, out_index, skill_index = indexes
    unit = _cell(cells, unit_index)
    scope_in = _truncate_cell(_cell(cells, in_index))
    scope_out = _truncate_cell(_cell(cells, out_index))
    skill_name = _extract_skill_name(_cell(cells, skill_index))
    skill_path = _resolve_skill_path(skill_name)
    warnings = () if skill_path else (f"skill not found: {skill_name}",)
    return UnitInjection(
        unit=unit,
        scope_in=scope_in,
        scope_out=scope_out,
        skill_name=skill_name,
        skill_path=skill_path,
        prompt=_build_prompt(doc_path, scope_in, scope_out, skill_name, skill_path),
        warnings=warnings,
    )


def render_human(units: tuple[UnitInjection, ...]) -> str:
    blocks = [f"[{unit.unit}]\n{unit.prompt}" for unit in units]
    return "\n\n".join(blocks)


def filter_units(
    units: tuple[UnitInjection, ...],
    unit_name: str | None,
) -> tuple[UnitInjection, ...]:
    if not unit_name:
        return units
    selected = tuple(unit for unit in units if unit.unit == unit_name)
    if not selected:
        raise ValueError(f"unit not found: {unit_name}")
    return selected


def _receipt_meta(task: str | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {"source": "self_instrument"}
    if task:
        meta["task_id"] = task.strip().upper()
    ledger = os.environ.get("TOOL_RECEIPTS_LEDGER")
    if ledger:
        meta["ledger_path"] = ledger
    return meta


def record_receipt_best_effort(
    args_summary: dict[str, Any],
    exit_code: int,
    doc_path: Path | None,
    task: str | None,
) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "TOOL_RECEIPTS_LEDGER"
    ):
        return
    try:
        if str(WORKSPACE_ROOT) not in sys.path:
            sys.path.insert(0, str(WORKSPACE_ROOT))
        from tools.tool_receipts import record

        meta = _receipt_meta(task)
        if doc_path is not None:
            meta["artifact_paths"] = [doc_path]
        record("design_doc_inject", args_summary, exit_code, meta=meta)
    except Exception as exc:  # pragma: no cover - receipt must stay best-effort
        print(f"warning: failed to record tool receipt: {exc}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit design_doc unit injections")
    parser.add_argument("--doc", required=True, help="Path to a design document")
    parser.add_argument("--unit", help="Only emit one component by exact name")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    parser.add_argument("--task", help="Task ID to stamp into the tool receipt")
    return parser


def _json_payload(
    doc_path: Path,
    units: tuple[UnitInjection, ...],
    warnings: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "document": str(doc_path),
        "units": [asdict(unit) for unit in units],
        "warnings": list(warnings),
    }


def main(argv: Optional[tuple[str, ...]] = None) -> int:
    args = _build_parser().parse_args(argv)
    args_summary = {"doc": args.doc, "unit": args.unit, "json": args.json}
    doc_path: Path | None = None
    try:
        doc_path = _absolute(args.doc)
        units = filter_units(parse_units(doc_path), args.unit)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        record_receipt_best_effort(args_summary, 2, doc_path, args.task)
        return 2

    warnings = tuple(warning for unit in units for warning in unit.warnings)
    if args.json:
        print(
            json.dumps(
                _json_payload(doc_path, units, warnings),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_human(units))
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
    record_receipt_best_effort(args_summary, 0, doc_path, args.task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
