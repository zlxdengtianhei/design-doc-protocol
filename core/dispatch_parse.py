# Vendored from context-infra tools/todo/dispatch_parse.py (2026-08-30, MIT)。纯解析无副效应。
#!/usr/bin/env python3
"""Shared parsing helpers for TODO dispatch/show consumers."""
from __future__ import annotations

import re


class DispatchParseError(Exception):
    """User-facing failure while parsing TODO command output."""


def parse_dispatch(output: str) -> tuple[str, dict[str, str]]:
    original_marker = "## 原始 prompt 逐字原文"
    metadata_marker = "## 任务元数据"
    reuse_marker = "## 复用既有成果指针"
    if original_marker not in output or metadata_marker not in output:
        raise DispatchParseError("todo dispatch output is missing required report sections")

    original = output.split(original_marker, 1)[1].split(metadata_marker, 1)[0].strip()
    metadata_block = output.split(metadata_marker, 1)[1]
    if reuse_marker in metadata_block:
        metadata_block = metadata_block.split(reuse_marker, 1)[0]

    metadata: dict[str, str] = {}
    for line in metadata_block.splitlines():
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        metadata[key.strip()] = value.strip()

    if not original:
        raise DispatchParseError("todo dispatch returned an empty original prompt")
    return original, metadata


def parse_show(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    first_line = output.splitlines()[0] if output.splitlines() else ""
    if first_line.startswith("### "):
        title_line = first_line.replace("###", "").strip()
        fields["T-id"] = title_line.split(":", 1)[0].strip()
        if ":" in title_line:
            title = title_line.split(":", 1)[1].strip()
            title = re.sub(r"\s+\[[^\]]+\]\s*$", "", title).strip()
            fields["Title"] = title

    for line in output.splitlines():
        match = re.match(r"- \*\*(?P<key>[^*]+)\*\*:\s*(?P<value>.*)$", line)
        if match:
            fields[match.group("key").strip()] = match.group("value").strip()

    description = fields.get("Description", "")
    phase_match = re.search(r"phase\s*[:：]\s*([^|]+?)(?:\s*\||$)", description, re.IGNORECASE)
    if phase_match:
        fields["phase"] = phase_match.group(1).strip()
    return fields


def normalize_task_id(task_id: str) -> str:
    task_id = task_id.strip().upper()
    if task_id and not task_id.startswith("T"):
        task_id = f"T{task_id}"
    return task_id
