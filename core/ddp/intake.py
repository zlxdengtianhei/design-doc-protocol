"""Thin DDP-facing requirement intake wrapper for SL-2."""
from __future__ import annotations

from pathlib import Path

try:
    from tools.requirement_doc import append as requirement_append
except ImportError:  # 开源独立布局：requirement_doc 集成面未随仓发布；调用时报显式错误
    requirement_append = None  # type: ignore[assignment]
from core.gatekit.base import record_receipt_best_effort


def record_requirement(
    job: Path | str,
    verbatim: str,
    source_anchor: str,
    session_id: str,
    *,
    domain: str | None = None,
    phase: str | None = None,
    requirement_class: str = "design",
    req_id: str | None = None,
    date: str = "<date>",
    task_id: str = "unknown",
    dry_run: bool = False,
) -> requirement_append.AppendResult:
    """Record one DDP requirement through the deterministic requirement_doc path."""
    if requirement_append is None:
        raise RuntimeError(
            "requirement_doc 集成面未随开源仓发布；record_requirement 需要母仓 "
            "tools.requirement_doc 或等价实现（见 README 已知集成面）"
        )
    job_path = requirement_append.resolve_job(job)
    req_class = requirement_append.require_requirement_class(requirement_class)
    if req_class == "design" and not domain:
        raise requirement_append.AppendError("domain is required when requirement_class=design")
    if req_class == "execution" and not phase:
        raise requirement_append.AppendError("phase is required when requirement_class=execution")
    final_req_id = req_id or requirement_append.derive_req_id(verbatim, source_anchor)
    result = requirement_append.append_requirement(
        job=job_path,
        domain=domain or "execution",
        verbatim=verbatim,
        source_anchor=source_anchor,
        session_id=session_id,
        req_id=final_req_id,
        date=date,
        dry_run=dry_run,
        requirement_class=req_class,
        phase=phase,
        task_id=task_id,
    )
    record_receipt_best_effort(
        "ddp_record_requirement",
        {
            "job": str(job_path),
            "domain": domain,
            "phase": phase,
            "requirement_class": req_class,
            "req_id": final_req_id,
            "dry_run": dry_run,
        },
        0,
        task=task_id,
        artifact_paths=[result.target],
    )
    return result


__all__ = ["record_requirement"]
