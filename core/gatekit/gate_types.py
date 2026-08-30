# Vendored from context-infra tools/infra_core/gate_types.py (2026-08-30, MIT). 与母仓同演进，勿在此处分叉修订。
"""Shared immutable issue types for gate and regulator contracts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GateIssue:
    """One actionable gate/regulator issue.

    locator: file:line, field path, or named artifact location.
    why: concrete reason this is a problem, not "insufficient detail".
    required_next_action: what the author must change to repair this.
    """

    locator: str
    why: str
    required_next_action: str


__all__ = ["GateIssue"]
