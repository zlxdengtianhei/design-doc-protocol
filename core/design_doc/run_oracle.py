#!/usr/bin/env python3
"""Validation harness for design_doc check_completeness."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


TOOL_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = TOOL_DIR / "fixtures"
LOG_DIR = TOOL_DIR / "logs"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

REAL_T631 = (
    WORKSPACE_ROOT
    / "core"
    / "design_doc"
    / "fixtures"
    / "T631_git-env-cleanup-design.md"
)

TEXT_FIXTURES = (
    ("positive_real_T631", REAL_T631, "FLAG"),
    ("negative_pass_self_design", FIXTURE_DIR / "pass_check_completeness_self_design.md", "PASS"),
    ("soft_negative_dc3_echo", FIXTURE_DIR / "dc3_echo_soft_negative.md", "PASS"),
)

REGULATOR_FIXTURES = (
    ("soft_negative_dc3_echo", FIXTURE_DIR / "dc3_echo_soft_negative.md"),
)

if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import check_completeness  # noqa: E402


def _absolute(path: Path) -> Path:
    return path.expanduser().resolve()


def _issue_summary(shell: check_completeness.ShellResult) -> str:
    if not shell.issues:
        return "-"
    counts: dict[str, int] = {}
    for issue in shell.issues:
        counts[issue.code] = counts.get(issue.code, 0) + 1
    return ", ".join(f"{key}x{value}" for key, value in sorted(counts.items()))


def _placeholder_locations(shell: check_completeness.ShellResult, limit: int = 40) -> str:
    placeholders = [issue for issue in shell.issues if issue.code == "DC1_PLACEHOLDER"]
    if not placeholders:
        return "-"
    rendered = [
        f"{issue.field}@{issue.line}:{issue.value}"
        for issue in placeholders[:limit]
    ]
    if len(placeholders) > limit:
        rendered.append(f"... +{len(placeholders) - limit} more")
    return "; ".join(rendered)


def deterministic_rows() -> tuple[dict[str, Any], ...]:
    return tuple(_row_for_fixture(name, path, expected) for name, path, expected in TEXT_FIXTURES)


def _row_for_fixture(name: str, path: Path, expected: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    shell = check_completeness.scan_text(text)
    actual = shell.verdict
    return {
        "fixture": name,
        "path": str(_absolute(path)),
        "issues": _issue_summary(shell),
        "placeholder_count": shell.placeholder_count,
        "placeholder_locations": _placeholder_locations(shell),
        "expected": expected,
        "actual": actual,
        "status": "PASS" if actual == expected else "FAIL",
        "shell": asdict(shell),
    }


def _table_lines(rows: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    header = "fixture | placeholders | issues | expected | actual | PASS/FAIL"
    separator = "--- | ---: | --- | --- | --- | ---"
    body = tuple(
        f"{row['fixture']} | {row['placeholder_count']} | {row['issues']} | "
        f"{row['expected']} | {row['actual']} | {row['status']}"
        for row in rows
    )
    return (header, separator) + body


def _rough_hits(raw_text: str) -> dict[str, bool]:
    lowered = raw_text.lower()
    return {
        "contains_flag": "flag" in lowered or '"verdict": "flag"' in lowered,
        "contains_dc3": "dc3" in lowered,
        "contains_echo_or_vague": any(term in raw_text for term in ("回显", "空泛", "vague", "echo")),
        "contains_success_effect": "success_effect" in raw_text or "成功效果" in raw_text,
        "contains_decision": "决策" in raw_text or "decision" in lowered,
    }


def regulator_runs(reps: int, regulator_tier: str, timeout_seconds: int) -> tuple[dict[str, Any], ...]:
    return tuple(
        _run_one_regulator(rep, fixture_name, fixture_path, regulator_tier, timeout_seconds)
        for rep in range(1, reps + 1)
        for fixture_name, fixture_path in REGULATOR_FIXTURES
    )


def _run_one_regulator(
    rep: int,
    fixture_name: str,
    fixture_path: Path,
    regulator_tier: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    document_text = fixture_path.read_text(encoding="utf-8")
    result = check_completeness.run_regulator_for_text(document_text, regulator_tier, timeout_seconds)
    raw_text = str(result.get("raw_text", ""))
    return {
        "rep": rep,
        "fixture": fixture_name,
        "path": str(_absolute(fixture_path)),
        "result": result,
        "rough_hits": _rough_hits(raw_text),
    }


def _log_path(ts: Optional[str]) -> Path:
    stamp = ts if ts else datetime.now().strftime("%Y%m%d_%H%M%S")
    return _absolute(LOG_DIR / f"oracle_run_{stamp}.md")


def _render_log(
    rows: tuple[dict[str, Any], ...],
    regulator: tuple[dict[str, Any], ...],
    reps: int,
    log_path: Path,
    timeout_seconds: int,
) -> str:
    deterministic_table = "\n".join(_table_lines(rows))
    placeholder_details = "\n".join(
        f"- {row['fixture']}: {row['placeholder_locations']}" for row in rows
    )
    return (
        "# design_doc check_completeness Oracle Run\n\n"
        f"- log_path: `{log_path}`\n"
        f"- tool_dir: `{_absolute(TOOL_DIR)}`\n"
        f"- real_positive: `{_absolute(REAL_T631)}`\n"
        f"- reps: `{reps}`\n"
        f"- model_timeout_seconds: `{timeout_seconds}`\n\n"
        "## A. Deterministic Discrimination\n\n"
        f"{deterministic_table}\n\n"
        "### Placeholder Locations\n\n"
        f"{placeholder_details}\n\n"
        "## B. Regulator Raw Outputs\n\n"
        f"{_render_regulator_section(regulator, reps)}\n"
    )


def _render_regulator_section(regulator: tuple[dict[str, Any], ...], reps: int) -> str:
    if reps == 0:
        return "`--reps 0`: regulator LLM calls skipped by contract."
    if not regulator:
        return "No regulator targets were configured."
    return "\n\n".join(_render_one_regulator_run(item) for item in regulator)


def _render_one_regulator_run(item: dict[str, Any]) -> str:
    result = item.get("result", {})
    raw = str(result.get("raw_text", ""))
    parsed = result.get("parsed")
    parsed_text = json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else "-"
    rough_hits = json.dumps(item.get("rough_hits", {}), ensure_ascii=False, indent=2)
    router_summary = json.dumps(
        {
            "returncode": result.get("returncode"),
            "stderr": result.get("stderr"),
            "router_parse_error": result.get("router_parse_error"),
            "parse_error": result.get("parse_error"),
            "router_error": (result.get("router") or {}).get("error"),
            "attempts": (result.get("router") or {}).get("attempts"),
        },
        ensure_ascii=False,
        indent=2,
    )
    return (
        f"### rep {item['rep']} fixture {item['fixture']}\n\n"
        f"path: `{item['path']}`\n\n"
        "router_summary:\n"
        f"```json\n{router_summary}\n```\n\n"
        "rough_hits:\n"
        f"```json\n{rough_hits}\n```\n\n"
        "parsed:\n"
        f"```json\n{parsed_text}\n```\n\n"
        "raw:\n"
        f"```text\n{raw}\n```"
    )


def write_log(
    rows: tuple[dict[str, Any], ...],
    regulator: tuple[dict[str, Any], ...],
    reps: int,
    ts: Optional[str],
    timeout_seconds: int,
) -> Path:
    path = _log_path(ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_log(rows, regulator, reps, path, timeout_seconds), encoding="utf-8")
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run design_doc completeness oracle fixtures")
    parser.add_argument("--reps", type=int, default=1, help="Regulator repetitions; 0 skips LLM calls")
    parser.add_argument("--ts", default=None, help="Timestamp suffix for logs/oracle_run_<ts>.md")
    parser.add_argument("--regulator-tier", default="claude-zai:high", help="cli_agent primary tier")
    parser.add_argument("--timeout", type=int, default=600, help="model subprocess timeout seconds")
    return parser


def main(argv: Optional[tuple[str, ...]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.reps < 0:
        print("--reps must be >= 0", file=sys.stderr)
        return 2
    if args.reps > 0 and args.timeout < 600:
        print("--timeout must be >= 600 for model calls", file=sys.stderr)
        return 2
    try:
        rows = deterministic_rows()
        regulator = () if args.reps == 0 else regulator_runs(args.reps, args.regulator_tier, args.timeout)
        log_path = write_log(rows, regulator, args.reps, args.ts, args.timeout)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print("\n".join(_table_lines(rows)))
    print(f"log_path: {log_path}")
    return 0 if all(row["status"] == "PASS" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
