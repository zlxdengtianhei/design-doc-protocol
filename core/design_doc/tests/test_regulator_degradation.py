#!/usr/bin/env python3
"""Held-out tests for the regulator retry/degradation path (no live model call).

These lock the fix for the 2026-07-12 defect where a regulator *dispatch* failure
(all channels down — e.g. a ``types.UnionType`` ImportError under Python 3.9)
surfaced an empty ``raw_text`` that ``check_completeness`` mislabeled as the parser
error ``no_json_object_found`` and a contentless ``UNKNOWN`` verdict. The tool now:

- distinguishes a dispatch failure (no model text delivered) from a parse failure
  (text delivered but unparseable) and surfaces the runner's real reason + a hint;
- retries the next ladder tier on a transient dispatch failure and on a
  delivered-but-unparseable reply (with a stricter JSON-only reminder);
- hardens the JSON extractor against code fences, stray prose braces, and
  truncation.

All model calls are faked through ``check_completeness._regulator_invoker``.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.design_doc import check_completeness  # noqa: E402

DOC = "# tiny design doc\n\nbody\n"


class _FakeVerdict:
    """Mimics regulator_runner.RegulatorVerdict's surface used by the tool."""

    def __init__(self, status: str, raw_text: str = "", reason: str = "") -> None:
        self.status = status
        self.raw_text = raw_text
        self.reason = reason

    def as_dict(self) -> dict:
        return {"status": self.status, "raw_text": self.raw_text, "reason": self.reason}


class _FakeInvoker:
    """Returns queued responses; the last item repeats if calls exceed the queue."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, prompt: str, tier: str, timeout_seconds: int):
        self.calls.append((prompt, tier, timeout_seconds))
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        item = self._responses[idx]
        if isinstance(item, Exception):
            raise item
        return item


_RAW = check_completeness.REGULATOR_RAW_DELIVERED
_FLAG_JSON = '{"verdict": "FLAG", "dc3_issues": [], "dc4_issues": [], "dc5_issues": [{"unit": "x", "line": 1, "problem": "p", "fix": "f"}], "dc6_issues": []}'
_PASS_JSON = '{"verdict": "PASS", "dc3_issues": [], "dc4_issues": [], "dc5_issues": [], "dc6_issues": []}'


def _run(monkeypatch, responses, tier="codex:high", max_attempts=3):
    invoker = _FakeInvoker(responses)
    monkeypatch.setattr(check_completeness, "_regulator_invoker", invoker)
    result = check_completeness.run_regulator_for_text(
        DOC, tier, 600, task="TREG", max_attempts=max_attempts
    )
    return result, invoker


# --- dispatch failure is no longer mislabeled as a parser error -------------


def test_dispatch_failure_surfaces_real_reason_not_parse_error(monkeypatch) -> None:
    reason = "cannot import name 'UnionType' from 'types'"
    result, invoker = _run(monkeypatch, [_FakeVerdict("FLAG", raw_text="", reason=reason)])

    assert result["verdict"] == "UNKNOWN"
    assert result["degraded"] is True
    assert result["failure_kind"] == "dispatch_failed"
    assert "UnionType" in result["failure_reason"]
    # The misleading legacy label must NOT be presented for a dispatch failure.
    assert result["parse_error"] is None
    assert "python" in result["hint"].lower()
    # A deterministic dispatch failure must not burn the other tiers.
    assert len(invoker.calls) == 1


def test_transient_dispatch_failure_escalates_to_next_tier(monkeypatch) -> None:
    result, invoker = _run(
        monkeypatch,
        [
            _FakeVerdict("FLAG", raw_text="", reason="timeout after 600s"),
            _FakeVerdict(_RAW, raw_text=_PASS_JSON, reason="custom_response_contract"),
        ],
    )

    assert result["verdict"] == "PASS"
    assert result["degraded"] is False
    assert len(invoker.calls) == 2
    assert invoker.calls[1][1] == "claude-zai:high"  # degraded to the next ladder tier


def test_invoker_exception_is_caught_and_reported(monkeypatch) -> None:
    result, invoker = _run(monkeypatch, [RuntimeError("router blew up")])

    assert result["verdict"] == "UNKNOWN"
    assert result["failure_kind"] == "dispatch_failed"
    assert "router blew up" in result["failure_reason"]
    assert len(invoker.calls) == 1


# --- delivered-but-unparseable retries with a stricter reminder -------------


def test_unparseable_then_parseable_degrades_across_tiers(monkeypatch) -> None:
    result, invoker = _run(
        monkeypatch,
        [
            _FakeVerdict(_RAW, raw_text="I reviewed it and it looks complete.", reason="custom_response_contract"),
            _FakeVerdict(_RAW, raw_text=_FLAG_JSON, reason="custom_response_contract"),
        ],
    )

    assert result["verdict"] == "FLAG"
    assert result["dc5_issues"]
    assert result["degraded"] is False
    kinds = [a["kind"] for a in result["attempts"]]
    assert kinds == ["parse_failed", "parsed"]
    # The retry appended the strict JSON-only reminder.
    assert check_completeness.STRICT_JSON_REMINDER in invoker.calls[1][0]
    assert check_completeness.STRICT_JSON_REMINDER not in invoker.calls[0][0]


def test_all_tiers_unparseable_returns_degraded_parse_failed(monkeypatch) -> None:
    prose = _FakeVerdict(_RAW, raw_text="looks fine to me", reason="custom_response_contract")
    result, invoker = _run(monkeypatch, [prose, prose, prose])

    assert result["verdict"] == "UNKNOWN"
    assert result["degraded"] is True
    assert result["failure_kind"] == "parse_failed"
    assert result["parse_error"] == "no_json_object_found"
    assert len(invoker.calls) == 3  # walked the whole ladder
    assert "raw_text" in result["hint"]


def test_first_tier_parseable_makes_no_extra_calls(monkeypatch) -> None:
    result, invoker = _run(monkeypatch, [_FakeVerdict(_RAW, raw_text=_FLAG_JSON, reason="custom_response_contract")])

    assert result["verdict"] == "FLAG"
    assert result["degraded"] is False
    assert len(invoker.calls) == 1


# --- JSON extractor hardening ------------------------------------------------


def test_parse_regulator_json_handles_code_fence() -> None:
    raw = "```json\n" + _PASS_JSON + "\n```"
    parsed, error = check_completeness.parse_regulator_json(raw)
    assert error is None
    assert parsed["verdict"] == "PASS"


def test_parse_regulator_json_skips_prose_brace_before_object() -> None:
    raw = "Here is my review {see the object below}:\n" + _FLAG_JSON
    parsed, error = check_completeness.parse_regulator_json(raw)
    assert error is None
    assert parsed["verdict"] == "FLAG"
    assert parsed["dc5_issues"]


def test_parse_regulator_json_truncated_object_reports_truncated() -> None:
    raw = '{"verdict": "FLAG", "dc5_issues": [{"unit": "x"'  # never closes
    parsed, error = check_completeness.parse_regulator_json(raw)
    assert parsed is None
    assert error == "truncated_json"


def test_parse_regulator_json_prose_only_reports_no_json() -> None:
    parsed, error = check_completeness.parse_regulator_json("The document looks complete to me.")
    assert parsed is None
    assert error == "no_json_object_found"


def test_parse_regulator_json_trailing_prose_after_object() -> None:
    raw = _FLAG_JSON + "\n\nThat is my assessment."
    parsed, error = check_completeness.parse_regulator_json(raw)
    assert error is None
    assert parsed["verdict"] == "FLAG"
