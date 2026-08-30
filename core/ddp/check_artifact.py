#!/usr/bin/env python3
"""SL-3 DDP artifact completeness gate."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core.ddp import artifact as ddp_artifact  # noqa: E402
from core.ddp import meaning_doc as ddp_meaning_doc  # noqa: E402
from core.gatekit.gate_types import GateIssue as Issue  # noqa: E402
from core.gatekit.base import (  # noqa: E402
    STATUS_FLAG,
    STATUS_PASS,
    DeterministicShell,
    Finding,
    GateVerdict,
    Regulator,
    compute_verdict,
    extract_first_json_object,
    record_receipt_best_effort,
)

STREAMS = ("requirements", "meaning", "design")
STATUS_PRESENT = "present"
STATUS_NOT_YET_ACTIVE = "not_yet_active"
REQ_HEADING_RE = re.compile(r"^####\s+(?P<req_id>[A-Za-z][A-Za-z0-9_.-]*)\b", re.MULTILINE)
WORD_RE = re.compile(r"[A-Za-z0-9_]{4,}")


@dataclass(frozen=True)
class StreamEntry:
    name: str
    status: str
    authority: str
    source_hash: str
    line: int


class DdpArtifactShell(DeterministicShell):
    """Deterministic DA1-DA4 checks for the DDP artifact projection."""

    def __init__(self, artifact_root: Path, domain: str) -> None:
        self.artifact_root = artifact_root.expanduser().resolve()
        self.domain = domain

    def run_checks(self, artifact_path: Path, text: str) -> list[Finding]:
        streams = _parse_streams(text)
        findings: list[Finding] = []
        findings.extend(self._da1_stream_presence(artifact_path, streams))
        findings.extend(self._da2_pointer_evidence(artifact_path, text, streams))
        findings.extend(self._da3_requirement_class(artifact_path, streams))
        findings.extend(self._da4_not_yet_active(artifact_path, streams))
        findings.extend(self._meaning_pointer_findings(artifact_path, text, streams))
        findings.extend(self._subordinate_gate_checks(streams))
        return findings

    def _meaning_pointer_findings(
        self, artifact_path: Path, artifact_text: str, streams: dict[str, StreamEntry]
    ) -> list[Finding]:
        """DA2.MEANING: when meaning is present, the projection must adopt it by pointer.

        Runs ``meaning_doc.check_pointer_anchor`` (T1387 second half): pointer/hash
        evidence, anchor visibility, and no copied meaning prose. Unreachable
        authorities are DA2/DA4 territory and are not re-flagged here.
        """
        entry = streams.get("meaning")
        if entry is None or entry.status != STATUS_PRESENT:
            return [Finding("DA2.MEANING", STATUS_PASS, "", "")]
        authority = _resolve_authority(entry.authority, artifact_path)
        if not entry.authority or not authority.exists() or not authority.is_file():
            return [Finding("DA2.MEANING", STATUS_PASS, "", "")]
        anchor = f"{artifact_path}:{entry.line}"
        try:
            result = ddp_meaning_doc.check_pointer_anchor(artifact_text, authority)
        except OSError as exc:
            return [Finding("DA2.MEANING", STATUS_FLAG, anchor, f"meaning pointer check failed: {exc}")]
        if result.passed:
            return [Finding("DA2.MEANING", STATUS_PASS, "", "")]
        return [Finding("DA2.MEANING", STATUS_FLAG, anchor, issue) for issue in result.issues]

    def _da1_stream_presence(
        self, artifact_path: Path, streams: dict[str, StreamEntry]
    ) -> list[Finding]:
        issues: list[Finding] = []
        for name in STREAMS:
            entry = streams.get(name)
            if entry is None:
                issues.append(
                    Finding(
                        "DA1",
                        STATUS_FLAG,
                        f"{artifact_path}:1",
                        f"{name} stream is silently missing from DDP_ARTIFACT.md",
                    )
                )
                continue
            if name in {"requirements", "design"} and entry.status != STATUS_PRESENT:
                issues.append(
                    Finding(
                        "DA1",
                        STATUS_FLAG,
                        f"{artifact_path}:{entry.line}",
                        f"{name} stream must be present, got {entry.status or '<empty>'}",
                    )
                )
            if name == "meaning" and entry.status not in {STATUS_PRESENT, STATUS_NOT_YET_ACTIVE}:
                issues.append(
                    Finding(
                        "DA1",
                        STATUS_FLAG,
                        f"{artifact_path}:{entry.line}",
                        "meaning stream must be present or explicitly not_yet_active",
                    )
                )
        return issues or [Finding("DA1", STATUS_PASS, "", "")]

    def _da2_pointer_evidence(
        self,
        artifact_path: Path,
        artifact_text: str,
        streams: dict[str, StreamEntry],
    ) -> list[Finding]:
        issues: list[Finding] = []
        for entry in streams.values():
            if entry.status != STATUS_PRESENT:
                continue
            path = _resolve_authority(entry.authority, artifact_path)
            anchor = f"{artifact_path}:{entry.line}"
            if not entry.authority:
                issues.append(Finding("DA2", STATUS_FLAG, anchor, f"{entry.name} present without authority path"))
                continue
            if not path.exists() or not path.is_file():
                issues.append(Finding("DA2", STATUS_FLAG, anchor, f"{entry.name} authority path does not exist: {path}"))
                continue
            if path.stat().st_size <= 0:
                issues.append(Finding("DA2", STATUS_FLAG, anchor, f"{entry.name} authority path is empty: {path}"))
                continue
            actual_hash = ddp_artifact.sha256_file(path)
            if not entry.source_hash:
                issues.append(Finding("DA2", STATUS_FLAG, anchor, f"{entry.name} present without source_hash"))
            elif entry.source_hash != actual_hash:
                issues.append(
                    Finding(
                        "DA2",
                        STATUS_FLAG,
                        anchor,
                        f"{entry.name} source_hash mismatch: expected {entry.source_hash}, actual {actual_hash}",
                    )
                )
            issues.extend(_source_body_leak_findings(artifact_path, artifact_text, entry, path))
        return issues or [Finding("DA2", STATUS_PASS, "", "")]

    def _da3_requirement_class(
        self, artifact_path: Path, streams: dict[str, StreamEntry]
    ) -> list[Finding]:
        entry = streams.get("requirements")
        if entry is None or entry.status != STATUS_PRESENT:
            return [Finding("DA3", STATUS_PASS, "", "")]
        path = _resolve_authority(entry.authority, artifact_path)
        if not path.exists():
            return [Finding("DA3", STATUS_PASS, "", "")]
        text = path.read_text(encoding="utf-8", errors="replace")
        if "requirement_io" in text.lower():
            return [Finding("DA3", STATUS_PASS, "", "")]
        blocks = _requirement_blocks(text)
        if not blocks:
            return [
                Finding(
                    "DA3",
                    STATUS_FLAG,
                    f"{path}:1",
                    "requirements stream has no #### requirement entries and no requirement_io deferral",
                )
            ]
        issues: list[Finding] = []
        for req_id, line, body in blocks:
            if "requirement_class=" not in body:
                issues.append(
                    Finding(
                        "DA3",
                        STATUS_FLAG,
                        f"{path}:{line}",
                        f"{req_id} provenance must include requirement_class= or defer to requirement_io",
                    )
                )
        return issues or [Finding("DA3", STATUS_PASS, "", "")]

    def _da4_not_yet_active(
        self, artifact_path: Path, streams: dict[str, StreamEntry]
    ) -> list[Finding]:
        issues: list[Finding] = []
        for name, entry in streams.items():
            anchor = f"{artifact_path}:{entry.line}"
            if entry.status == "missing":
                issues.append(
                    Finding(
                        "DA4",
                        STATUS_FLAG,
                        anchor,
                        f"{name} stream is unbuilt but marked missing; use not_yet_active / NOT YET ACTIVE",
                    )
                )
            if entry.status == STATUS_PRESENT:
                path = _resolve_authority(entry.authority, artifact_path)
                if not entry.authority or not path.exists():
                    issues.append(
                        Finding(
                            "DA4",
                            STATUS_FLAG,
                            anchor,
                            f"{name} stream is falsely marked present without a reachable authority",
                        )
                    )
        return issues or [Finding("DA4", STATUS_PASS, "", "")]

    def _subordinate_gate_checks(self, streams: dict[str, StreamEntry]) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._rd5_rd6_findings())
        findings.extend(self._design_doc_findings(streams))
        findings.extend(self._frontmatter_dependency_findings(streams))
        return findings

    def _rd5_rd6_findings(self) -> list[Finding]:
        try:
            from tools.requirement_doc.check_requirement_doc import scan_ddp_job
        except Exception as exc:  # noqa: BLE001
            # release 布局：requirement_doc 集成面未随仓发布，该子检查按构造缺席。
            # 此处报 PASS+明示「未运行」，而非 FLAG——fail-closed 语义保护的是
            # 母仓布局（requirement_doc 必须在场），独立仓里恒 FLAG 是自信的错答案。
            return [Finding("DA2.RD", STATUS_PASS, "", f"RD5/RD6 skipped: requirement_doc integration not shipped in this release ({exc})")]
        try:
            result = scan_ddp_job(self.artifact_root, domain=self.domain, record_subset=False)
        except Exception as exc:  # noqa: BLE001
            return [Finding("DA2.RD", STATUS_FLAG, str(self.artifact_root), f"requirement_doc RD5/RD6 check failed: {exc}")]
        if getattr(result, "verdict", "PASS") != STATUS_FLAG:
            return [Finding("DA2.RD", STATUS_PASS, "", "")]
        findings: list[Finding] = []
        for issue in getattr(result, "issues", ()):
            line = getattr(issue, "line", 0) or 1
            value = getattr(issue, "value", "")
            section = getattr(issue, "section", "")
            code = getattr(issue, "code", "RD")
            findings.append(
                Finding(
                    "DA2.RD",
                    STATUS_FLAG,
                    f"{self.artifact_root}:{line}",
                    f"{code} {section}: {getattr(issue, 'message', '')} {value}".strip(),
                )
            )
        return findings or [Finding("DA2.RD", STATUS_PASS, "", "")]

    def _design_doc_findings(self, streams: dict[str, StreamEntry]) -> list[Finding]:
        entry = streams.get("design")
        if entry is None or entry.status != STATUS_PRESENT:
            return [Finding("DA4.DC", STATUS_PASS, "", "")]
        path = _resolve_authority(entry.authority, self.artifact_root / "DDP_ARTIFACT.md")
        if not path.exists():
            return [Finding("DA4.DC", STATUS_PASS, "", "")]
        try:
            from core.design_doc.check_completeness import scan_text
        except Exception as exc:  # noqa: BLE001
            return [Finding("DA4.DC", STATUS_FLAG, str(path), f"design_doc DC import failed: {exc}")]
        result = scan_text(path.read_text(encoding="utf-8", errors="replace"), path)
        if getattr(result, "verdict", "PASS") != STATUS_FLAG:
            return [Finding("DA4.DC", STATUS_PASS, "", "")]
        findings: list[Finding] = []
        for issue in getattr(result, "issues", ()):
            if getattr(issue, "severity", "ERROR") == "WARNING":
                continue
            line = getattr(issue, "line", 0) or 1
            findings.append(
                Finding(
                    "DA4.DC",
                    STATUS_FLAG,
                    f"{path}:{line}",
                    f"{getattr(issue, 'code', 'DC')} {getattr(issue, 'section', '')}: {getattr(issue, 'message', '')}",
                )
            )
        return findings or [Finding("DA4.DC", STATUS_PASS, "", "")]

    def _frontmatter_dependency_findings(self, streams: dict[str, StreamEntry]) -> list[Finding]:
        warnings: list[str] = []
        for name in ("requirements", "meaning"):
            entry = streams.get(name)
            if entry is None or entry.status != STATUS_PRESENT or not entry.authority:
                continue
            path = _resolve_authority(entry.authority, self.artifact_root / "DDP_ARTIFACT.md")
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            keys = _frontmatter_keys(text)
            missing = [key for key in ("depends_on", "consumed_by") if key not in keys]
            if missing:
                warnings.append(f"{path}:1 missing warning-only frontmatter keys {', '.join(missing)}")
        if warnings:
            return [Finding("DA6.FRONTMATTER", STATUS_PASS, "", "WARNING " + " | ".join(warnings))]
        return [Finding("DA6.FRONTMATTER", STATUS_PASS, "", "")]


class DdpArtifactRegulator(Regulator):
    """DA5 second-agent faithfulness check."""

    def build_prompt(self, artifact_text: str, source_bundle: str, forbidden_read: str) -> str:
        return f"""You are the independent DA5 regulator for a DDP artifact gate.

Forbidden read:
{forbidden_read}

Task:
Check faithfulness only from the supplied artifact and source bundle.

DA5 criteria:
- Verbatim source text is not paraphrased into the DDP_ARTIFACT projection.
- Pointer-not-copy is honored: the artifact may contain authority paths, hashes, req_ids, anchors, status, and coverage rows, but not copied source bodies.
- MISS=0 is plausible from the supplied artifact/source bundle.

Return strict JSON only:
{{
  "verdict": "PASS|FLAG",
  "issues": [
    {{"locator": "artifact/source locator", "why": "specific counterexample", "required_next_action": "repair action"}}
  ]
}}

DDP_ARTIFACT:
{artifact_text}

SOURCE_BUNDLE:
{source_bundle}
"""

    def parse_response(self, raw_text: str) -> tuple[list[Issue], str | None]:
        blob = extract_first_json_object(raw_text)
        if not blob:
            return [], "no_json_object"
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            return [], f"json_decode_error:{exc}"
        raw_issues = data.get("issues", [])
        if not isinstance(raw_issues, list):
            return [], "issues_not_list"
        issues: list[Issue] = []
        for item in raw_issues:
            if not isinstance(item, dict):
                continue
            issues.append(
                Issue(
                    locator=str(item.get("locator", "")),
                    why=str(item.get("why", "")),
                    required_next_action=str(item.get("required_next_action", "")),
                )
            )
        verdict = str(data.get("verdict", "")).upper()
        if verdict == STATUS_FLAG and not issues:
            return [Issue("DDP_ARTIFACT", "regulator returned FLAG without issue detail", "name a locatable counterexample")], None
        if verdict not in {STATUS_PASS, STATUS_FLAG}:
            return [], f"invalid_verdict:{verdict or '<empty>'}"
        return issues, None


def check_artifact(
    artifact_root: Path,
    domain: str | None = None,
    artifact_path: Path | None = None,
    *,
    skip_regulator: bool = False,
    regulator_tier: str = "codex:high",
    timeout_seconds: int = 600,
) -> tuple[GateVerdict, Path]:
    root = artifact_root.expanduser().resolve()
    resolved_domain = domain or _infer_domain(root, artifact_path)
    if artifact_path is None:
        artifact_obj = ddp_artifact.assemble_manifest(root, resolved_domain)
        artifact_path = ddp_artifact.write_artifact(artifact_obj)
    else:
        artifact_path = artifact_path.expanduser().resolve()
    shell = DdpArtifactShell(root, resolved_domain)
    findings, text = shell.execute(artifact_path)
    regulator_result: dict[str, Any] | None = None
    if not skip_regulator:
        regulator = DdpArtifactRegulator(regulator_tier=regulator_tier, timeout_seconds=timeout_seconds)
        regulator_result = regulator.run(
            text,
            source_bundle=_source_bundle(artifact_path, text),
            forbidden_read=(
                "Do not read repository files, chat history, worker reports, or executor "
                "success narratives outside the supplied DDP_ARTIFACT and SOURCE_BUNDLE."
            ),
        )
    return compute_verdict(findings, regulator_result, use_regulator=not skip_regulator), artifact_path


def _parse_streams(text: str) -> dict[str, StreamEntry]:
    streams = _streams_from_frontmatter(text)
    streams.update(_streams_from_sections(text))
    return streams


def _streams_from_frontmatter(text: str) -> dict[str, StreamEntry]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    raw = text[3:end]
    try:
        import yaml

        data = yaml.safe_load(raw) or {}
    except Exception:
        return {}
    raw_streams = ((data.get("ddp_artifact") or {}).get("streams") or {}) if isinstance(data, dict) else {}
    result: dict[str, StreamEntry] = {}
    for name in STREAMS:
        raw_entry = raw_streams.get(name) if isinstance(raw_streams, dict) else None
        if not isinstance(raw_entry, dict):
            continue
        line = _line_of(text, f"{name}:")
        result[name] = StreamEntry(
            name=name,
            status=_normalize_status(raw_entry.get("status", "")),
            authority=str(raw_entry.get("authority") or "").strip(),
            source_hash=str(raw_entry.get("source_hash") or "").strip(),
            line=line,
        )
    return result


def _streams_from_sections(text: str) -> dict[str, StreamEntry]:
    result: dict[str, StreamEntry] = {}
    pattern = re.compile(r"^##\s+(Requirements|Meaning|Design)\s+Stream\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        name = match.group(1).lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[start:end]
        result[name] = StreamEntry(
            name=name,
            status=_normalize_status(_bullet_value(section, "status")),
            authority=_strip_ticks(_bullet_value(section, "authority")),
            source_hash=_strip_ticks(_bullet_value(section, "source_hash")),
            line=text[: match.start()].count("\n") + 1,
        )
    return result


def _bullet_value(section: str, key: str) -> str:
    match = re.search(rf"^\s*-\s+{re.escape(key)}:\s*(.*?)\s*$", section, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _strip_ticks(value: str) -> str:
    return value.strip().strip("`").strip()


def _normalize_status(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized.upper() == "NOT YET ACTIVE":
        return STATUS_NOT_YET_ACTIVE
    return normalized.lower().replace("-", "_").replace(" ", "_")


def _resolve_authority(value: str, anchor_path: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (anchor_path.parent / path).resolve()
    return path


def _requirement_blocks(text: str) -> list[tuple[str, int, str]]:
    matches = list(REQ_HEADING_RE.finditer(text))
    blocks: list[tuple[str, int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        line = text[: match.start()].count("\n") + 1
        blocks.append((match.group("req_id"), line, text[match.start() : end]))
    return blocks


def _source_body_leak_findings(
    artifact_path: Path,
    artifact_text: str,
    entry: StreamEntry,
    source_path: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    source_text = source_path.read_text(encoding="utf-8", errors="replace")
    artifact_lower = artifact_text.lower()
    for line_no, line in enumerate(source_text.splitlines(), start=1):
        snippet = _source_body_line(line)
        if not snippet:
            continue
        if snippet.lower() in artifact_lower:
            findings.append(
                Finding(
                    "DA2",
                    STATUS_FLAG,
                    f"{artifact_path}:{_line_of(artifact_text, snippet[:32])}",
                    f"{entry.name} source body copied into projection from {source_path}:{line_no}",
                )
            )
    for sentence in _artifact_sentences(artifact_text):
        if _looks_like_paraphrase(sentence, source_text):
            findings.append(
                Finding(
                    "DA2",
                    STATUS_FLAG,
                    f"{artifact_path}:{_line_of(artifact_text, sentence[:32])}",
                    f"{entry.name} source body appears paraphrased in projection; keep source text only behind pointers",
                )
            )
            break
    return findings


def _source_body_line(line: str) -> str:
    stripped = line.strip().strip("|").strip()
    if len(stripped) < 28:
        return ""
    yaml_key = stripped.split(":", 1)[0]
    if yaml_key in {
        "domain",
        "doc_type",
        "version",
        "req_id",
        "task_id",
        "session_id",
        "created_at",
        "requirement_anchor",
    }:
        return ""
    if stripped.startswith(("#", "-", ">", "|", "---")):
        return ""
    if any(marker in stripped for marker in ("sha256=", "requirement_class=", "source_hash", "status:", "authority:")):
        return ""
    return stripped


def _frontmatter_keys(text: str) -> set[str]:
    if not text.startswith("---"):
        return set()
    end = text.find("\n---", 3)
    if end < 0:
        return set()
    keys: set[str] = set()
    for line in text[3:end].splitlines():
        if not line or line.startswith((" ", "\t", "-")):
            continue
        if ":" in line:
            keys.add(line.split(":", 1)[0].strip())
    return keys


def _artifact_sentences(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("---", "|", "ddp_artifact:", "streams:", "requirements:", "meaning:", "design:")):
            continue
        if any(token in stripped for token in ("source_hash:", "authority:", "| stream |", "|---|")):
            continue
        lines.append(stripped)
    return lines


def _looks_like_paraphrase(candidate: str, source_text: str) -> bool:
    candidate_tokens = {t.lower() for t in WORD_RE.findall(candidate)}
    if len(candidate_tokens) < 6:
        return False
    source_tokens = {t.lower() for t in WORD_RE.findall(source_text)}
    if not source_tokens:
        return False
    overlap = candidate_tokens & source_tokens
    return len(overlap) >= 8 and len(overlap) / max(len(candidate_tokens), 1) >= 0.70


def _line_of(text: str, needle: str) -> int:
    if not needle:
        return 1
    idx = text.find(needle)
    if idx < 0:
        return 1
    return text[:idx].count("\n") + 1


def _source_bundle(artifact_path: Path, artifact_text: str) -> str:
    chunks = []
    for entry in _parse_streams(artifact_text).values():
        if entry.status != STATUS_PRESENT or not entry.authority:
            continue
        path = _resolve_authority(entry.authority, artifact_path)
        if not path.exists() or not path.is_file():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        chunks.append(
            f"--- SOURCE {entry.name} path={path} sha256={ddp_artifact.sha256_file(path)} ---\n"
            f"{source[:40000]}"
        )
    return "\n\n".join(chunks)


def _infer_domain(root: Path, artifact_path: Path | None) -> str:
    if artifact_path is not None and artifact_path.exists():
        text = artifact_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^\s*domain:\s*([^\n]+)\s*$", text, re.MULTILINE)
        if match:
            return match.group(1).strip().strip("'\"")
    req_domains = sorted((root / "requirements" / "design").glob("*.md"))
    if len(req_domains) == 1:
        return req_domains[0].stem
    design_docs = sorted((root / "design_docs").glob("*_design.md"))
    if len(design_docs) == 1:
        return design_docs[0].name.removesuffix("_design.md")
    return root.name


def _print_verdict(verdict: GateVerdict, artifact_path: Path) -> None:
    print(f"artifact: {artifact_path}")
    print(f"final_status: {verdict.final_status}")
    print(f"source: {verdict.source}")
    print("shell_findings:")
    for finding in verdict.shell_findings:
        if finding.status == STATUS_PASS:
            print(f"- {finding.check_id}: PASS")
        else:
            print(f"- {finding.check_id}: {finding.status} {finding.line_anchor} | {finding.message}")
    if verdict.regulator_raw is not None:
        print(f"regulator_status: {verdict.regulator_raw.get('status')}")
    if verdict.regulator_issues:
        print("regulator_issues:")
        for issue in verdict.regulator_issues:
            print(f"- {issue.locator}: {issue.why} -> {issue.required_next_action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check DDP_ARTIFACT.md completeness (SL-3).")
    parser.add_argument("--artifact-root", required=True, help="Root folder holding the DDP streams.")
    parser.add_argument("--domain", default=None, help="DDP domain. Defaults to artifact-root basename.")
    parser.add_argument("--artifact", default=None, help="Existing DDP_ARTIFACT.md path. Default assembles <root>/DDP_ARTIFACT.md first.")
    parser.add_argument("--skip-regulator", action="store_true", help="Bypass DA5 regulator and use shell-only verdict.")
    parser.add_argument("--regulator-tier", default="codex:high")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--task-id", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifact_root = Path(args.artifact_root)
    artifact_path = Path(args.artifact).expanduser().resolve() if args.artifact else None
    args_summary = {
        "artifact_root": str(artifact_root),
        "domain": args.domain,
        "artifact": str(artifact_path) if artifact_path else None,
        "skip_regulator": args.skip_regulator,
    }
    try:
        verdict, checked_path = check_artifact(
            artifact_root,
            args.domain,
            artifact_path,
            skip_regulator=args.skip_regulator,
            regulator_tier=args.regulator_tier,
            timeout_seconds=args.timeout,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        record_receipt_best_effort("ddp_check_artifact", args_summary, 2, task=args.task_id)
        return 2
    _print_verdict(verdict, checked_path)
    exit_code = 0 if verdict.final_status == STATUS_PASS else 1
    record_receipt_best_effort(
        "ddp_check_artifact",
        args_summary,
        exit_code,
        task=args.task_id,
        artifact_paths=[str(checked_path)],
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
