# Vendored from context-infra tools/unified_gate/base.py (2026-08-30, MIT)。唯一改动：gate_types 导入重指向 core.gatekit。regulator/error_ledger 依赖为函数内延迟导入，缺失时优雅降级（STATUS_UNKNOWN / 跳过台账）。
#!/usr/bin/env python3
"""unified_gate.base — Wampir shared template for all deterministic-shell + regulator gates.

Architecture ("Wampir" shape, R-D1/R-D2):
  DeterministicShell  → reads artifact, produces list[Finding]
                        Each Finding: {check_id, status PASS/FLAG/UNKNOWN, line_anchor, message}
  Regulator           → sends artifact + source_bundle to a second agent via regulator_runner,
                        produces list[Issue] with {locator, why, required_next_action}.
                        Fail-safe: channel failure → UNKNOWN treated as FLAG.
  Verdict             → aggregates shell findings + regulator issues, follows V1-V6 criteria:
                        • V1 deterministic judgement (shell)
                        • V2 hard negatives (caller must supply fixtures)
                        • V3 actionable counterexample (regulator produces locatable Issue)
                        • V4 second independent agent (regulator has forbidden_read)
                        • V5 general predicate (no oracle-specific values in shell logic)
                        • V6 honest boundary (only bounded claim until cross-oracle validation)

Regulator dispatch MUST go through tools.infra_core.regulator_runner.
Codex worker sessions may only exercise this through the runner contract; direct
router subprocess calls are intentionally not part of this base class.

Extension pattern for new gate scenarios:
  1. Subclass ``DeterministicShell`` and implement ``run_checks()``.
     Return a list of ``Finding`` objects — one per check predicate.
  2. Subclass ``Regulator`` and implement ``build_prompt()``.
     Embed the forbidden_read contract in the prompt string.
  3. Call ``compute_verdict()`` to aggregate findings + regulator issues into a ``GateVerdict``.
  4. Wrap with argparse and ``record_receipt_best_effort()`` for CLI use.

File stays < 400 lines. All paths are absolute (WORKSPACE_ROOT-anchored).
Immutable data: Finding, Issue, GateVerdict are frozen dataclasses.
"""
from __future__ import annotations

import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from core.gatekit.gate_types import GateIssue as Issue


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# Status constants — only these three values are valid
STATUS_PASS = "PASS"
STATUS_FLAG = "FLAG"
STATUS_UNKNOWN = "UNKNOWN"

VALID_STATUSES = frozenset({STATUS_PASS, STATUS_FLAG, STATUS_UNKNOWN})

# Default regulator timeout floor — callers may increase, never decrease
MIN_REGULATOR_TIMEOUT = 600


# ---------------------------------------------------------------------------
# Immutable data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One deterministic-shell check result.

    check_id:    short label like "PF1" or "D2" — matches V1 naming.
    status:      PASS | FLAG | UNKNOWN.
    line_anchor: file:line or path/field locator (empty string if not applicable).
    message:     human-readable description. Empty for PASS, non-empty for FLAG/UNKNOWN.
    """

    check_id: str
    status: str
    line_anchor: str
    message: str

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Finding.status must be one of {VALID_STATUSES}, got {self.status!r}")


@dataclass(frozen=True)
class GateVerdict:
    """Aggregated gate verdict following V1-V6 criteria.

    final_status:   PASS | FLAG — UNKNOWN always becomes FLAG (fail-safe).
    shell_findings: tuple of Finding from deterministic shell.
    regulator_issues: tuple of Issue from second agent (empty if regulator skipped/passed).
    regulator_raw:  raw regulator response dict for traceability (None if not run).
    source:         "shell" | "regulator" | "all" — which layer produced the verdict.
    """

    final_status: str
    shell_findings: tuple[Finding, ...]
    regulator_issues: tuple[Issue, ...]
    regulator_raw: Optional[dict[str, Any]]
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "final_status": self.final_status,
            "shell_findings": [asdict(f) for f in self.shell_findings],
            "regulator_issues": [asdict(i) for i in self.regulator_issues],
            "regulator_raw": self.regulator_raw,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# DeterministicShell base class
# ---------------------------------------------------------------------------


class DeterministicShell(ABC):
    """Abstract base for the deterministic (non-LLM) shell layer.

    Subclasses implement ``run_checks()`` to produce a list of Finding objects.
    The shell must be:
      - Reproducible: same input → same output (no randomness, no LLM).
      - Line-anchored: FLAG findings carry a file:line or field locator.
      - General-predicate: no oracle-specific hardcoded values in logic (V5).

    Example subclass::

        class MyShell(DeterministicShell):
            def run_checks(self, artifact_path: Path, text: str) -> list[Finding]:
                issues = []
                if "<PLACEHOLDER>" in text:
                    line = next(i for i, l in enumerate(text.splitlines(), 1) if "<PLACEHOLDER>" in l)
                    issues.append(Finding("MY1", STATUS_FLAG, f"{artifact_path}:{line}", "placeholder found"))
                return issues or [Finding("MY1", STATUS_PASS, "", "")]
    """

    @abstractmethod
    def run_checks(self, artifact_path: Path, text: str) -> list[Finding]:
        """Run all deterministic checks on the artifact text.

        Args:
            artifact_path: absolute path to the artifact (for line anchors).
            text:          full UTF-8 content of the artifact.

        Returns:
            Non-empty list of Finding objects. PASS findings have empty message.
            FLAG findings have non-empty line_anchor + message.
        """

    def execute(self, artifact_path: Path) -> tuple[list[Finding], str]:
        """Load artifact and run checks. Returns (findings, text).

        Raises:
            OSError: if the artifact cannot be read.
        """
        text = artifact_path.read_text(encoding="utf-8", errors="replace")
        findings = self.run_checks(artifact_path, text)
        return findings, text

    def shell_status(self, findings: list[Finding]) -> str:
        statuses = {f.status for f in findings}
        if STATUS_FLAG in statuses:
            return STATUS_FLAG
        if STATUS_UNKNOWN in statuses:
            return STATUS_UNKNOWN
        return STATUS_PASS


# ---------------------------------------------------------------------------
# Regulator base class
# ---------------------------------------------------------------------------


class Regulator(ABC):
    """Abstract base for the second-agent (LLM) regulator layer.

    Subclasses implement ``build_prompt()`` to produce the regulator's task
    description with embedded forbidden_read constraints.

    ARCHITECTURAL CONSTRAINT:
        Regulator dispatch MUST go through regulator_runner. Worker sessions
        should only exercise this path through controlled runner tests.

    Fail-safe rule:
        If the runner channel fails or returns non-parseable output, the
        regulator status is UNKNOWN, which propagates to FLAG in the verdict.
        This is intentional: a regulator that cannot produce a verdict is not
        an absent regulator — it is a failed signal that must be treated as FLAG.
    """

    def __init__(
        self,
        regulator_tier: str = "codex:high",
        timeout_seconds: int = MIN_REGULATOR_TIMEOUT,
    ) -> None:
        if timeout_seconds < MIN_REGULATOR_TIMEOUT:
            raise ValueError(f"timeout_seconds must be >= {MIN_REGULATOR_TIMEOUT}")
        self._tier = regulator_tier
        self._timeout = timeout_seconds

    @abstractmethod
    def build_prompt(
        self,
        artifact_text: str,
        source_bundle: str,
        forbidden_read: str,
    ) -> str:
        """Produce the full prompt for the second agent.

        The prompt MUST embed:
        1. A forbidden_read section listing what the regulator must NOT consult.
        2. The artifact text (or relevant excerpt).
        3. A strict JSON schema for the expected response.
        4. Instructions to name locatable counterexamples (V3).

        Args:
            artifact_text: full text of the artifact being checked.
            source_bundle: additional source context the regulator may read.
            forbidden_read: list of items the regulator must not consult.
        """

    @abstractmethod
    def parse_response(self, raw_text: str) -> tuple[list[Issue], Optional[str]]:
        """Parse the regulator JSON response into a list of Issues.

        Returns:
            (issues, error_message) — error_message is None on success.
            On parse failure return ([], "error description").
        """

    def run(
        self,
        artifact_text: str,
        source_bundle: str = "",
        forbidden_read: str = "Do not read repository files or chat history outside the supplied artifact.",
    ) -> dict[str, Any]:
        """Run the regulator runner and return a raw result dict.

        Returns a dict with keys:
          status:        PASS | FLAG | UNKNOWN
          issues:        list of Issue dicts (empty on PASS or parse failure)
          returncode:    0 when runner delivered raw text, -1 on runner failure.
          stderr:        runner failure text.
          parse_error:   error string if JSON parsing failed (None otherwise)
          raw_text:      raw LLM output text
        """
        prompt = self.build_prompt(artifact_text, source_bundle, forbidden_read)
        try:
            from tools.infra_core.regulator_adapter import response_contract_from_prompt
            from tools.infra_core.regulator_runner import STATUS_RAW_DELIVERED, run_regulator as run_unified_regulator
        except Exception as exc:  # noqa: BLE001
            _emit_unified_gate_error(
                reason=f"runner_import_exception:{type(exc).__name__}",
                message=str(exc),
                tier=self._tier,
            )
            return {
                "status": STATUS_UNKNOWN,
                "issues": [],
                "returncode": -1,
                "stderr": str(exc),
                "parse_error": f"runner_import_exception:{exc}",
                "raw_text": "",
            }

        try:
            runner_verdict = run_unified_regulator(
                prompt,
                must_read=["unified_gate supplied artifact/source bundle prompt"],
                forbidden_read=[forbidden_read],
                tier=self._tier,
                timeout=self._timeout,
                response_contract=response_contract_from_prompt(prompt),
            )
        except Exception as exc:  # noqa: BLE001
            _emit_unified_gate_error(
                reason=f"runner_exception:{type(exc).__name__}",
                message=str(exc),
                tier=self._tier,
            )
            return {
                "status": STATUS_UNKNOWN,
                "issues": [],
                "returncode": -1,
                "stderr": str(exc),
                "parse_error": f"runner_exception:{exc}",
                "raw_text": "",
            }

        raw_text = runner_verdict.raw_text
        if runner_verdict.status != STATUS_RAW_DELIVERED:
            _emit_unified_gate_error(
                reason=runner_verdict.reason or "runner_no_raw_contract",
                message=runner_verdict.reason or "regulator runner did not deliver raw text",
                tier=self._tier,
            )
            return {
                "status": STATUS_UNKNOWN,
                "issues": [],
                "returncode": -1,
                "stderr": runner_verdict.reason,
                "parse_error": runner_verdict.reason or "runner_no_raw_contract",
                "raw_text": raw_text,
                "runner": runner_verdict.as_dict(),
            }

        issues, parse_error = self.parse_response(raw_text)
        if parse_error:
            _emit_unified_gate_error(
                reason=parse_error,
                message=parse_error,
                tier=self._tier,
                raw_text=raw_text,
            )
        if parse_error or not issues and _raw_contains_flag(raw_text):
            status = STATUS_UNKNOWN if parse_error else STATUS_FLAG
        elif issues:
            status = STATUS_FLAG
        else:
            status = STATUS_PASS

        return {
            "status": status,
            "issues": [asdict(i) for i in issues],
            "returncode": 0,
            "stderr": "",
            "parse_error": parse_error,
            "raw_text": raw_text,
            "runner": runner_verdict.as_dict(),
        }


def _raw_contains_flag(text: str) -> bool:
    """Heuristic: if no JSON parsed but text mentions FLAG/FAIL, treat as FLAG."""
    upper = text.upper()
    return "FLAG" in upper or '"STATUS": "FLAG"' in upper or '"VERDICT": "FAIL"' in upper


def _emit_unified_gate_error(
    *,
    reason: str,
    message: str,
    tier: str,
    raw_text: str = "",
) -> None:
    try:
        from tools.error_ledger.auto_emit import emit_auto_error

        normalized_reason = _stable_error_reason(reason)
        emit_auto_error(
            category=_unified_gate_category(normalized_reason),
            signal_source=_unified_gate_signal_source(normalized_reason),
            provider=tier,
            domain="unified_gate",
            chain_step=f"unified_gate/regulator/{normalized_reason}",
            error_code=normalized_reason,
            what=f"unified_gate regulator failure {normalized_reason}: {message}",
            evidence="tools/unified_gate/base.py:Regulator.run",
            resolution="Inspect regulator runner output and gate parser contract.",
            resolution_status="unresolved",
            recurrence=f"auto_unified_gate:{normalized_reason}:{tier}",
            task_id=os.environ.get("TODO_ID") or os.environ.get("CONTEXT_INFRA_TASK_ID") or None,
            session_id=os.environ.get("CODEX_SESSION_ID") or None,
        )
    except Exception:
        return


def _stable_error_reason(value: str) -> str:
    text = str(value or "unknown").strip()
    if ":" in text:
        text = text.split(":", 1)[0]
    text = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in text)
    return text[:80].strip("_") or "unknown"


def _unified_gate_category(reason: str) -> str:
    lower = reason.lower()
    if "json" in lower or "parse" in lower or "no_json" in lower:
        return "provider_behavior"
    if "timeout" in lower:
        return "provider_silent_failure"
    return "tool_failure"


def _unified_gate_signal_source(reason: str) -> str:
    lower = reason.lower()
    if "timeout" in lower or "no_json" in lower:
        return "silent"
    return "router_soft"


# ---------------------------------------------------------------------------
# Verdict aggregation (V1-V6)
# ---------------------------------------------------------------------------


def compute_verdict(
    findings: list[Finding],
    regulator_result: Optional[dict[str, Any]],
    use_regulator: bool = True,
) -> GateVerdict:
    """Aggregate shell findings + regulator result into a GateVerdict.

    V1: deterministic shell produces FLAG → final_status = FLAG regardless of regulator.
    V3/V4: regulator FLAG or UNKNOWN → final_status = FLAG (fail-safe).
    V6: only PASS when both layers clear.

    Args:
        findings:         list of Finding from DeterministicShell.
        regulator_result: dict from Regulator.run(), or None if regulator skipped.
        use_regulator:    if False, regulator result is ignored and source = "shell".

    Returns:
        GateVerdict (frozen, immutable).
    """
    shell_status = _aggregate_shell_status(findings)
    # Fail-closed (SLICE-0): shell UNKNOWN must never reach GateVerdict.final_status.
    # Coerce once here, before both branches, so the shell-only path cannot leak UNKNOWN
    # and the regulator path cannot let shell UNKNOWN silently pass when the regulator is
    # clean. The regulator-on branch routes FLAG shell_status to source="shell", so a
    # shell-origin UNKNOWN still reports shell as the blocking layer.
    if shell_status == STATUS_UNKNOWN:
        shell_status = STATUS_FLAG
    regulator_issues: list[Issue] = []

    if not use_regulator or regulator_result is None:
        final_status = shell_status
        source = "shell"
        return GateVerdict(
            final_status=final_status,
            shell_findings=tuple(findings),
            regulator_issues=(),
            regulator_raw=regulator_result,
            source=source,
        )

    # Regulator was run — parse its issues
    raw_issues = regulator_result.get("issues", [])
    regulator_issues = [
        Issue(
            locator=str(item.get("locator", "")),
            why=str(item.get("why", "")),
            required_next_action=str(item.get("required_next_action", "")),
        )
        for item in raw_issues
        if isinstance(item, dict)
    ]
    reg_status = str(regulator_result.get("status", STATUS_UNKNOWN))

    # Fail-safe: UNKNOWN → FLAG
    if reg_status == STATUS_UNKNOWN:
        reg_effective = STATUS_FLAG
    else:
        reg_effective = reg_status

    # Combine: shell FLAG takes precedence; then regulator
    if shell_status == STATUS_FLAG:
        final_status = STATUS_FLAG
        source = "shell"
    elif reg_effective == STATUS_FLAG:
        final_status = STATUS_FLAG
        source = "regulator"
    else:
        final_status = STATUS_PASS
        source = "all"

    return GateVerdict(
        final_status=final_status,
        shell_findings=tuple(findings),
        regulator_issues=tuple(regulator_issues),
        regulator_raw=regulator_result,
        source=source,
    )


def _aggregate_shell_status(findings: list[Finding]) -> str:
    statuses = {f.status for f in findings}
    if STATUS_FLAG in statuses:
        return STATUS_FLAG
    if STATUS_UNKNOWN in statuses:
        return STATUS_UNKNOWN
    return STATUS_PASS


# ---------------------------------------------------------------------------
# JSON extraction helper (shared by all gates)
# ---------------------------------------------------------------------------


def extract_first_json_object(text: str) -> Optional[str]:
    """Extract the first complete JSON object from text, tolerating surrounding prose."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for idx, char in enumerate(text[start:], start=start):
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
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


# ---------------------------------------------------------------------------
# Receipt helper (wraps tools.tool_receipts.receipt without import errors)
# ---------------------------------------------------------------------------


UNRECORDED_VERDICT_SOURCE = "unrecorded"


def _verdict_provenance(verdict: Optional["GateVerdict"]) -> dict[str, str]:
    """Provenance fields for a receipt: which layer produced the verdict.

    A caller that supplies no verdict gets ``unrecorded`` rather than a missing
    key. That distinction is the whole point: a silently absent field reads the
    same as "the regulator arm ran and passed", which is exactly the confusion
    this function exists to remove.
    """
    if verdict is None:
        return {
            "verdict_source": UNRECORDED_VERDICT_SOURCE,
            "verdict_status": UNRECORDED_VERDICT_SOURCE,
        }
    return {
        "verdict_source": str(getattr(verdict, "source", UNRECORDED_VERDICT_SOURCE)),
        "verdict_status": str(getattr(verdict, "final_status", UNRECORDED_VERDICT_SOURCE)),
    }


def record_receipt_best_effort(
    tool_name: str,
    args_summary: dict[str, Any],
    exit_code: int,
    task: Optional[str] = None,
    artifact_paths: Optional[list[str]] = None,
    verdict: Optional["GateVerdict"] = None,
) -> None:
    """Record a tool receipt, silently ignoring all failures.

    This must not affect gate behaviour — a receipt failure is logged to stderr
    but does not change the gate exit code or verdict.

    Skipped in pytest context unless TOOL_RECEIPTS_LEDGER env var is set.

    Args:
        verdict: the GateVerdict this receipt describes. Supplying it records
            which layer decided (shell / regulator / all); omitting it records
            ``unrecorded`` so the omission itself stays visible downstream.
    """
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("TOOL_RECEIPTS_LEDGER"):
        return
    # New dict — the caller's mapping is never mutated.
    args_summary = {**args_summary, **_verdict_provenance(verdict)}
    try:
        if str(WORKSPACE_ROOT) not in sys.path:
            sys.path.insert(0, str(WORKSPACE_ROOT))
        from tools.tool_receipts.receipt import record  # type: ignore[import]

        meta: dict[str, Any] = {"source": "self_instrument"}
        if task:
            meta["task_id"] = task.strip().upper()
        if artifact_paths:
            meta["artifact_paths"] = artifact_paths
        ledger = os.environ.get("TOOL_RECEIPTS_LEDGER")
        if ledger:
            meta["ledger_path"] = ledger
        record(tool_name, args_summary, exit_code, meta=meta)
    # channel: silent consumer=test_system_usage.usage_probe reason=receipt write is best-effort; a failed write must not change gate exit codes; undercount surfaces in the usage-probe window
    except Exception as exc:  # noqa: BLE001  # pragma: no cover
        print(f"warning: failed to record tool receipt for {tool_name}: {exc}", file=sys.stderr)
