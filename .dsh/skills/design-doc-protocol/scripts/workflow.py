#!/usr/bin/env python3
"""Read-only CHANGELOG marker hint for Design Doc Protocol.

Scans `ddp-workflow` fenced JSON blocks. Does not judge semantic quality,
call a model, write files, skip stages, block product writes, or dispatch.
Exit 0 means markers look complete only — never protocol or task success.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from json.decoder import scanstring
from pathlib import Path
from typing import Any

VALID_STATES = frozenset({"todo", "done", "needs_work", "not_applicable"})
FIXED_STEPS = (
    "intake",
    "decompose",
    "cp_a",
    "cp_b",
    "propagate",
    "structure",
    "cp_c",
    "record",
    "external_review",
)
FENCE_OPEN = re.compile(r"^```([^\n]*)$")
FENCE_CLOSE = re.compile(r"^```\s*$")
INFO_TOKEN = "ddp-workflow"
_WS = " \t\r\n"
_DECODER = json.JSONDecoder()


@dataclass
class Fence:
    start_line: int
    end_line: int
    info: str
    body: str


@dataclass
class Issue:
    kind: str
    line: int | None = None
    step: str | None = None
    owner: str | None = None
    state: str | None = None
    domain: str | None = None
    change_id: str | None = None
    detail: str | None = None

    def render(self) -> str:
        parts = [f"kind={self.kind}"]
        if self.line is not None:
            parts.append(f"line={self.line}")
        if self.change_id:
            parts.append(f"change_id={self.change_id}")
        if self.step:
            parts.append(f"step={self.step}")
        if self.owner:
            parts.append(f"owner={self.owner}")
        if self.state:
            parts.append(f"state={self.state}")
        if self.domain:
            parts.append(f"domain={self.domain}")
        if self.detail:
            parts.append(f"detail={self.detail}")
        return "- " + " ".join(parts)


@dataclass
class CheckResult:
    change_id: str
    log_path: str
    issues: list[Issue] = field(default_factory=list)
    parse_error: bool = False
    input_error: str | None = None
    input_path: str | None = None

    @property
    def exit_code(self) -> int:
        if self.input_error or self.parse_error:
            return 2
        if self.issues:
            return 1
        return 0


def _info_has_token(info: str) -> bool:
    tokens = info.strip().split()
    return INFO_TOKEN in tokens


def find_fences(text: str) -> list[Fence]:
    lines = text.splitlines()
    fences: list[Fence] = []
    i = 0
    while i < len(lines):
        open_match = FENCE_OPEN.match(lines[i])
        if not open_match:
            i += 1
            continue
        info = open_match.group(1).strip()
        if not _info_has_token(info):
            i += 1
            continue
        # 1-based line of the first body row. i is the opening fence (0-based).
        start = i + 2
        i += 1
        body_lines: list[str] = []
        closed = False
        while i < len(lines):
            if FENCE_CLOSE.match(lines[i]):
                closed = True
                break
            body_lines.append(lines[i])
            i += 1
        end_line = i + 1 if closed else len(lines)
        fences.append(
            Fence(
                start_line=start,
                end_line=end_line,
                info=info,
                body="\n".join(body_lines),
            )
        )
        i += 1
    return fences


def _skip_ws(text: str, index: int) -> int:
    length = len(text)
    while index < length and text[index] in _WS:
        index += 1
    return index


def _locate_json_path_from(
    text: str, index: int, path: tuple[str | int, ...]
) -> int:
    """Return 0-based source index of the JSON node at path, starting at index."""
    index = _skip_ws(text, index)
    if index >= len(text):
        raise ValueError("empty_json")
    if not path:
        return index
    head, rest = path[0], path[1:]
    if isinstance(head, str):
        if text[index] != "{":
            raise ValueError("expected_object")
        index = _skip_ws(text, index + 1)
        if index < len(text) and text[index] == "}":
            raise ValueError("missing_key")
        while True:
            index = _skip_ws(text, index)
            if index >= len(text) or text[index] != '"':
                raise ValueError("expected_key")
            key_start = index
            key, after_key = scanstring(text, index + 1)
            index = _skip_ws(text, after_key)
            if index >= len(text) or text[index] != ":":
                raise ValueError("expected_colon")
            value_start = _skip_ws(text, index + 1)
            if key == head:
                if not rest:
                    return key_start
                return _locate_json_path_from(text, value_start, rest)
            _, after_val = _DECODER.raw_decode(text, value_start)
            index = _skip_ws(text, after_val)
            if index < len(text) and text[index] == "}":
                raise ValueError("missing_key")
            if index >= len(text) or text[index] != ",":
                raise ValueError("expected_comma")
            index += 1
    if isinstance(head, int):
        if text[index] != "[":
            raise ValueError("expected_array")
        index = _skip_ws(text, index + 1)
        if index < len(text) and text[index] == "]":
            raise ValueError("missing_index")
        current = 0
        while True:
            index = _skip_ws(text, index)
            if current == head:
                return _locate_json_path_from(text, index, rest)
            _, after_val = _DECODER.raw_decode(text, index)
            index = _skip_ws(text, after_val)
            if index < len(text) and text[index] == "]":
                raise ValueError("missing_index")
            if index >= len(text) or text[index] != ",":
                raise ValueError("expected_comma")
            index += 1
            current += 1
    raise ValueError("bad_path")


def _locate_json_path(text: str, path: tuple[str | int, ...]) -> int | None:
    """Index of a JSON node in valid source, or None if the path is absent."""
    try:
        return _locate_json_path_from(text, 0, path)
    except (ValueError, json.JSONDecodeError):
        return None


def _line_of_path(fence: Fence, path: tuple[str | int, ...]) -> int:
    """1-based file line of a parsed JSON member; fallback is the body start."""
    pos = _locate_json_path(fence.body, path)
    if pos is None:
        return fence.start_line
    return fence.start_line + fence.body.count("\n", 0, pos)


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def check_steps(payload: dict[str, Any], fence: Fence) -> list[Issue]:
    issues: list[Issue] = []
    domains_raw = payload.get("domains", [])
    if domains_raw is None:
        domains_raw = []
    if not isinstance(domains_raw, list) or any(
        not isinstance(item, str) or not item.strip() for item in domains_raw
    ):
        issues.append(
            Issue(
                kind="invalid_domains",
                line=fence.start_line,
                detail="domains_must_be_list_of_nonempty_strings",
            )
        )
        domains: list[str] = []
    else:
        domains = [item.strip() for item in domains_raw]

    steps_raw = payload.get("steps")
    if not isinstance(steps_raw, list):
        issues.append(
            Issue(
                kind="invalid_steps",
                line=fence.start_line,
                detail="steps_must_be_list",
            )
        )
        steps_raw = []

    seen_steps: dict[str, int] = {}
    present: set[str] = set()
    for index, item in enumerate(steps_raw):
        if not isinstance(item, dict):
            issues.append(
                Issue(
                    kind="invalid_step",
                    line=_line_of_path(fence, ("steps", index)),
                    detail=f"step_index_{index}_not_object",
                )
            )
            continue
        step = item.get("step")
        owner = _as_str(item.get("owner"))
        state = _as_str(item.get("state"))
        line = _line_of_path(fence, ("steps", index, "step"))
        if not _nonempty_text(step):
            issues.append(
                Issue(
                    kind="missing_step_name",
                    line=line,
                    owner=owner,
                )
            )
            continue
        step = step.strip()
        if step in seen_steps:
            issues.append(
                Issue(
                    kind="duplicate_step",
                    line=line,
                    step=step,
                    owner=owner,
                )
            )
        else:
            seen_steps[step] = line
        present.add(step)
        if state is None or not state.strip():
            issues.append(
                Issue(
                    kind="missing_state",
                    line=line,
                    step=step,
                    owner=owner,
                )
            )
        else:
            state = state.strip()
            if state not in VALID_STATES:
                issues.append(
                    Issue(
                        kind="unknown_state",
                        line=line,
                        step=step,
                        owner=owner,
                        state=state,
                    )
                )
            elif state == "done" and not _nonempty_text(item.get("evidence")):
                issues.append(
                    Issue(
                        kind="done_without_evidence",
                        line=line,
                        step=step,
                        owner=owner,
                    )
                )
            elif state == "not_applicable" and not _nonempty_text(item.get("note")):
                issues.append(
                    Issue(
                        kind="not_applicable_without_note",
                        line=line,
                        step=step,
                        owner=owner,
                    )
                )
            elif state in {"todo", "needs_work"}:
                issues.append(
                    Issue(
                        kind="incomplete",
                        line=line,
                        step=step,
                        owner=owner,
                        state=state,
                    )
                )
        if not _nonempty_text(owner):
            issues.append(
                Issue(
                    kind="missing_owner",
                    line=line,
                    step=step,
                    state=state,
                )
            )

    for name in FIXED_STEPS:
        if name not in present:
            issues.append(Issue(kind="missing_step", step=name))
    for domain in domains:
        expected = f"design:{domain}"
        if expected not in present:
            issues.append(
                Issue(
                    kind="missing_domain_step",
                    step=expected,
                    domain=domain,
                )
            )
    return issues


def check_log(log_path: Path, change_id: str) -> CheckResult:
    result = CheckResult(change_id=change_id, log_path=str(log_path))
    if not log_path.is_file():
        result.input_error = "log_not_found"
        result.input_path = str(log_path)
        return result
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError as exc:
        result.input_error = "log_unreadable"
        result.input_path = str(log_path)
        result.issues.append(
            Issue(kind="log_unreadable", detail=str(exc), line=None)
        )
        return result

    fences = find_fences(text)
    parsed: list[tuple[Fence, dict[str, Any]]] = []
    for fence in fences:
        if not fence.body.strip():
            result.parse_error = True
            result.issues.append(
                Issue(
                    kind="json_error",
                    line=fence.start_line,
                    detail="empty_block",
                )
            )
            continue
        try:
            payload = json.loads(fence.body)
        except json.JSONDecodeError as exc:
            result.parse_error = True
            result.issues.append(
                Issue(
                    kind="json_error",
                    line=fence.start_line + max(exc.lineno - 1, 0),
                    detail=exc.msg,
                )
            )
            continue
        if not isinstance(payload, dict):
            result.parse_error = True
            result.issues.append(
                Issue(
                    kind="json_error",
                    line=fence.start_line,
                    detail="root_not_object",
                )
            )
            continue
        parsed.append((fence, payload))

    ids: dict[str, list[int]] = {}
    for fence, payload in parsed:
        raw_id = payload.get("change_id")
        if _nonempty_text(raw_id):
            cid = raw_id.strip()
            ids.setdefault(cid, []).append(_line_of_path(fence, ("change_id",)))
        else:
            result.issues.append(
                Issue(kind="missing_change_id", line=fence.start_line)
            )

    for cid, lines in ids.items():
        if len(lines) > 1:
            for line in lines:
                result.issues.append(
                    Issue(kind="duplicate_id", line=line, change_id=cid)
                )

    matches = [
        (fence, payload)
        for fence, payload in parsed
        if _nonempty_text(payload.get("change_id"))
        and payload["change_id"].strip() == change_id
    ]
    if not matches:
        if not result.parse_error:
            result.issues.append(
                Issue(kind="change_not_found", change_id=change_id)
            )
        return result
    if len(matches) > 1:
        return result

    fence, payload = matches[0]
    result.issues.extend(check_steps(payload, fence))
    return result


def render(result: CheckResult) -> str:
    lines = ["workflow_check"]
    if result.input_error:
        extra = f" path={result.input_path}" if result.input_path else ""
        lines.append(f"error: {result.input_error}{extra}")
        lines.append("exit_hint: 2")
        return "\n".join(lines) + "\n"
    lines.append(f"change_id: {result.change_id}")
    lines.append(f"log: {result.log_path}")
    if result.exit_code == 0:
        lines.append("result: markers_complete_only")
    else:
        lines.append("result: issues")
    lines.append(f"exit_hint: {result.exit_code}")
    lines.append("")
    lines.append("issues:")
    if not result.issues:
        lines.append("- none")
    else:
        for issue in result.issues:
            lines.append(issue.render())
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only marker hint for ddp-workflow CHANGELOG blocks. "
            "Does not judge protocol completion."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Check one change_id in a CHANGELOG")
    check.add_argument("--log", required=True, help="Path to CHANGELOG.md")
    check.add_argument("--change", required=True, help="change_id to inspect")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        return 0 if code in (0, None) else 2
    result = check_log(Path(args.log), args.change)
    sys.stdout.write(render(result))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
