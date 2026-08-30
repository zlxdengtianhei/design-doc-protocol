#!/usr/bin/env python3
"""Assemble a DDP_ARTIFACT.md projection from existing file pointers."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Callable, Iterable

from core.ddp.schema import CoverageRow, DdpArtifact, StreamPointer, StreamStatus

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

try:
    from tools.tool_receipts import record  # noqa: E402
except ImportError:  # 开源独立布局：母仓台账面不在场时降级（记录纪律是母仓基建，非协议本体）
    def record(*args, **kwargs):  # type: ignore[no-redef]
        # 保持真 record() 的 dict 契约；record_error 键如实声明「未记录」
        return {"recorded": False, "record_error": "tool_receipts ledger not shipped in this release"}


DDP_HEADING_RE = re.compile(r"^####\s+(?P<req_id>[A-Za-z][A-Za-z0-9_.-]*)\b", re.MULTILINE)
MEANING_ANCHOR_RE = re.compile(r"\b(M\d+(?:\.\d+)?)\b")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_req_ids(text: str) -> tuple[str, ...]:
    return tuple(match.group("req_id") for match in DDP_HEADING_RE.finditer(text))


def _extract_meaning_anchors(text: str) -> tuple[str, ...]:
    return tuple(match.group(1) for match in MEANING_ANCHOR_RE.finditer(text))


def _status_for(stream: str, path: Path | None) -> StreamStatus:
    if path is not None and path.exists():
        return "present"
    if stream == "meaning":
        return "not_yet_active"
    return "missing"


def _resolve_stream(
    root: Path,
    name: str,
    candidates: Iterable[Path],
    anchor_extractor: Callable[[str], tuple[str, ...]] | None = None,
    req_extractor: Callable[[str], tuple[str, ...]] | None = None,
) -> StreamPointer:
    authority = next((candidate for candidate in candidates if candidate.exists()), None)
    status = _status_for(name, authority)
    source_hash = ""
    anchors: tuple[str, ...] = ()
    req_ids: tuple[str, ...] = ()
    if authority is not None and authority.exists():
        source_hash = sha256_file(authority)
        text = authority.read_text(encoding="utf-8")
        if anchor_extractor is not None:
            anchors = anchor_extractor(text)
        if req_extractor is not None:
            req_ids = req_extractor(text)
    return StreamPointer(
        name=name,  # type: ignore[arg-type]
        authority=authority,
        status=status,
        req_ids=req_ids,
        anchors=anchors,
        source_hash=source_hash,
    )


def discover_streams(root: Path, domain: str) -> tuple[StreamPointer, ...]:
    """Discover the three streams for ``domain`` under ``root``.

    Convention:
      - requirements -> ``<root>/requirements/design/<domain>.md``
      - meaning      -> ``<root>/requirements/meaning/<domain>.md``
      - design       -> ``<root>/design_docs/<domain>_design.md``
    """
    root = Path(root).expanduser().resolve()
    requirements = _resolve_stream(
        root,
        "requirements",
        [root / "requirements" / "design" / f"{domain}.md"],
        req_extractor=_extract_req_ids,
    )
    meaning = _resolve_stream(
        root,
        "meaning",
        [
            root / "requirements" / "meaning" / f"{domain}.md",
            root / "meaning" / f"{domain}.md",
        ],
        anchor_extractor=_extract_meaning_anchors,
    )
    design = _resolve_stream(
        root,
        "design",
        [
            root / "design_docs" / f"{domain}_design.md",
            root / "design_docs" / f"{domain}-design.md",
            root / "design_docs" / "design.md",
        ],
    )
    return (requirements, meaning, design)


def _coverage_rows(streams: tuple[StreamPointer, ...]) -> tuple[CoverageRow, ...]:
    rows: list[CoverageRow] = []
    for stream in streams:
        if stream.status == "present":
            gap_state = "satisfied"
        elif stream.status == "not_yet_active":
            gap_state = "deferred"
        else:
            gap_state = "unmet"
        rows.append(
            CoverageRow(
                stream=stream.name,
                status=stream.status,
                gap_state=gap_state,
                locator=str(stream.authority) if stream.authority else "",
            )
        )
    return tuple(rows)


def compute_projection_completeness(
    streams: tuple[StreamPointer, ...],
) -> tuple[str, tuple[str, ...]]:
    """Deterministically compute a projection completeness verdict (AD-09).

    The assemble step used to stamp ``UNKNOWN`` unconditionally, so a DDP artifact
    never signaled whether its own projection was complete. This computes a verdict
    from the stream pointers instead:

    - requirements and design must be ``present`` with a non-empty ``source_hash``
      (the authority file existed and was hashed).
    - meaning may be ``present`` or explicitly ``not_yet_active``; any other status
      (e.g. ``missing``) is a projection gap.

    Returns ``(verdict, reasons)`` where verdict is ``PASS`` or ``FLAG`` and reasons
    is a tuple of one-line, locator-free explanations (empty when PASS). This is a
    deterministic shell-layer signal; the deeper DA1-DA4 + regulator semantics live
    in ``tools/ddp/check_artifact.py`` and are not duplicated here.
    """
    by_name: dict[str, StreamPointer] = {stream.name: stream for stream in streams}
    reasons: list[str] = []
    for required in ("requirements", "design"):
        pointer = by_name.get(required)  # type: ignore[arg-type]
        status = pointer.status if pointer is not None else "absent"
        if status != "present":
            reasons.append(f"{required} stream not present (status={status})")
        elif not pointer.source_hash:
            reasons.append(f"{required} stream present but source_hash is empty")
    meaning = by_name.get("meaning")  # type: ignore[arg-type]
    if meaning is not None and meaning.status not in {"present", "not_yet_active"}:
        reasons.append(
            f"meaning stream status {meaning.status} must be present or not_yet_active"
        )
    verdict = "PASS" if not reasons else "FLAG"
    return verdict, tuple(reasons)


def assemble_manifest(
    root: Path,
    domain: str,
    verdict: str | None = None,
) -> DdpArtifact:
    """Build an in-memory DDP artifact from file pointers.

    When ``verdict`` is None the completeness verdict is **computed** from the
    resolved stream pointers via ``compute_projection_completeness`` (AD-09 fix:
    assemble no longer silently stamps UNKNOWN). Pass an explicit verdict only when
    a caller has a more authoritative signal (e.g. a gate result); an invalid
    string falls back to UNKNOWN.
    """
    streams = discover_streams(root, domain)
    reasons: tuple[str, ...] = ()
    if verdict is None:
        verdict, reasons = compute_projection_completeness(streams)
    else:
        valid_verdicts = ("PASS", "FLAG", "UNKNOWN")
        if verdict not in valid_verdicts:
            verdict = "UNKNOWN"
    return DdpArtifact(
        domain=domain,
        artifact_root=root,
        streams=streams,
        completeness_verdict=verdict,  # type: ignore[arg-type]
        completeness_reasons=reasons,
    )


def _stream_section(stream: StreamPointer) -> str:
    lines = [f"## {stream.name.capitalize()} Stream", ""]
    lines.append(f"- status: {stream.status}")
    if stream.authority is not None:
        lines.append(f"- authority: `{stream.authority}`")
    if stream.source_hash:
        lines.append(f"- source_hash: `{stream.source_hash}`")
    if stream.req_ids:
        lines.append(f"- req_ids: {', '.join(stream.req_ids)}")
    if stream.anchors:
        lines.append(f"- anchors: {', '.join(stream.anchors)}")
    if stream.freshness:
        lines.append(f"- freshness: {stream.freshness}")
    lines.append("")
    return "\n".join(lines)


def _coverage_section(rows: tuple[CoverageRow, ...]) -> str:
    lines = ["## Coverage", "", "| stream | status | gap_state | locator |", "|---|---|---|---|"]
    for row in rows:
        locator = f"`{row.locator}`" if row.locator else ""
        lines.append(f"| {row.stream} | {row.status} | {row.gap_state} | {locator} |")
    lines.append("")
    return "\n".join(lines)


def _render_reasons_block(reasons: tuple[str, ...]) -> str:
    """Render completeness_reasons as a YAML list, or empty when there are none."""
    if not reasons:
        return ""
    lines = ["  completeness_reasons:"]
    for reason in reasons:
        escaped = reason.replace('"', "'")
        lines.append(f'    - "{escaped}"')
    return "\n".join(lines) + "\n"


def render_artifact(artifact: DdpArtifact) -> str:
    """Render a DDP artifact as markdown."""
    streams = {s.name: s for s in artifact.streams}
    frontmatter = f"""---
ddp_artifact:
  domain: {artifact.domain}
  artifact_root: {artifact.artifact_root}
  streams:
    requirements:
      status: {streams['requirements'].status}
      authority: {streams['requirements'].authority or ''}
      source_hash: {streams['requirements'].source_hash}
    meaning:
      status: {streams['meaning'].status}
      authority: {streams['meaning'].authority or ''}
      source_hash: {streams['meaning'].source_hash}
    design:
      status: {streams['design'].status}
      authority: {streams['design'].authority or ''}
      source_hash: {streams['design'].source_hash}
  completeness_verdict: {artifact.completeness_verdict}
  claim_ceiling: {artifact.claim_ceiling}
  generated_by: {artifact.generated_by}
{_render_reasons_block(artifact.completeness_reasons)}---
"""
    body = [
        f"# DDP Artifact — {artifact.domain}",
        "",
        "> This file is a projection. Authority remains in the pointed-to source files, not here.",
        "",
    ]
    for name in ("requirements", "meaning", "design"):
        body.append(_stream_section(streams[name]))
    body.append(_coverage_section(_coverage_rows(artifact.streams)))
    return frontmatter + "\n".join(body)


def write_artifact(artifact: DdpArtifact, output_path: Path | None = None) -> Path:
    """Write the rendered artifact to disk and return the path."""
    target = Path(output_path) if output_path else artifact.artifact_root / "DDP_ARTIFACT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_artifact(artifact), encoding="utf-8")
    return target


def record_assemble_receipt(
    artifact: DdpArtifact,
    output_path: Path,
    exit_code: int,
    task_id: str = "",
) -> dict:
    """Append a tool receipt for ``ddp assemble``.

    Receipt writing is best-effort; failures are logged but do not change the exit code.
    """
    try:
        return record(
            tool="ddp_assemble",
            args={
                "artifact_root": str(artifact.artifact_root),
                "domain": artifact.domain,
                "output": str(output_path),
            },
            exit_code=exit_code,
            meta={
                "task_id": task_id,
                "artifact_paths": [str(output_path)],
                "domain": artifact.domain,
                "streams_present": [s.name for s in artifact.streams if s.status == "present"],
                "completeness_verdict": artifact.completeness_verdict,
                "completeness_reasons": list(artifact.completeness_reasons),
                "claim_ceiling": artifact.claim_ceiling,
            },
        )
    except Exception as exc:  # pragma: no cover - receipt failure must not break assembly
        return {"record_error": str(exc)}
