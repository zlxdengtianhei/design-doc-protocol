#!/usr/bin/env python3
"""Command-line entry for the DDP composition layer.

SL-0 commands:

- ``assemble``: discover the three streams under an artifact root, render the
  ``DDP_ARTIFACT.md`` projection, write it to disk, and append a tool receipt.
  Assembly is a pure projection (AD-09): it computes only projection completeness
  from stream pointers. The real completeness gate (``check_ddp_artifact``) is
  owned by SL-3 and is NOT wired here.

- ``check``: run the SL-3 DDP completeness gate (``check_ddp_artifact``).

- ``pipeline``: assemble the projection, run the SL-3 gate, and block with a
  non-zero exit when the gate does not PASS.

- ``guide``: print concise operator guidance for the DDP CLI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from core.ddp import artifact as ddp_artifact  # noqa: E402
from core.ddp import check_artifact as ddp_check_artifact  # noqa: E402
from core.ddp import intake as ddp_intake  # noqa: E402
from core.ddp import meaning_doc as ddp_meaning_doc  # noqa: E402
from core.ddp.artifact import (  # noqa: E402
    _coverage_rows,  # noqa: E402
    assemble_manifest,
    write_artifact,
)
try:
    from tools.requirement_doc import append as requirement_append  # noqa: E402
except ImportError:  # 开源独立布局：requirement_doc 未随仓发布；intake.record_requirement 会先报显式错误
    class _AppendErrorShim(Exception):
        pass

    class _RequirementAppendShim:  # 仅为 except 子句求值提供 AppendError 符号
        AppendError = _AppendErrorShim

    requirement_append = _RequirementAppendShim()  # type: ignore[assignment]


def _coverage_summary(artifact) -> str:
    rows = _coverage_rows(artifact.streams)
    lines = ["stream | status | gap_state"]
    for row in rows:
        lines.append(f"{row.stream} | {row.status} | {row.gap_state}")
    present = sum(1 for s in artifact.streams if s.status == "present")
    return (
        "Coverage summary:\n  " + "\n  ".join(lines) + f"\n  streams present: {present}/3"
    )


def _render_coverage_rows(artifact) -> str:
    rows = _coverage_rows(artifact.streams)
    lines = ["stream | status | gap_state | locator"]
    for row in rows:
        lines.append(f"{row.stream} | {row.status} | {row.gap_state} | {row.locator}")
    return "\n".join(lines)


def _default_receipts_ledger() -> Path:
    configured = os.environ.get("TOOL_RECEIPTS_LEDGER", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return WORKSPACE_ROOT / "contexts" / "tool_receipts" / "receipts.jsonl"


def _receipt_mentions_root(row: dict, root: Path) -> bool:
    root_text = str(root)
    args = row.get("args_summary") if isinstance(row.get("args_summary"), dict) else {}
    if str(args.get("artifact_root", "")) == root_text or str(args.get("job", "")) == root_text:
        return True
    for path in row.get("artifact_paths", []) or []:
        if str(path).startswith(root_text):
            return True
    return False


def _recent_receipts_for_root(root: Path, ledger: Path, limit: int) -> list[dict]:
    if limit <= 0 or not ledger.exists():
        return []
    root_text = str(root)
    matches: list[dict] = []
    with ledger.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            if root_text not in raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if _receipt_mentions_root(row, root):
                matches.append(row)
                if len(matches) > limit:
                    matches = matches[-limit:]
    return matches


def cmd_assemble(args: argparse.Namespace) -> int:
    root = Path(args.artifact_root).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: artifact-root is not a directory: {root}", file=sys.stderr)
        return 2
    artifact = assemble_manifest(root, args.domain, verdict=args.verdict)
    output = Path(args.output).expanduser().resolve() if args.output else None
    written = write_artifact(artifact, output)
    receipt = ddp_artifact.record_assemble_receipt(
        artifact,
        written,
        exit_code=0,
        task_id=args.task_id or "",
    )
    print(f"assembled DDP artifact: {written}")
    print(_coverage_summary(artifact))
    print(f"completeness_verdict: {artifact.completeness_verdict}")
    if "record_error" in receipt:
        print(f"WARN: receipt write failed: {receipt['record_error']}", file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    root = Path(args.artifact_root).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: artifact-root is not a directory: {root}", file=sys.stderr)
        return 2
    artifact_path = Path(args.artifact).expanduser().resolve() if args.artifact else None
    try:
        verdict, checked_path = ddp_check_artifact.check_artifact(
            root,
            args.domain,
            artifact_path,
            skip_regulator=args.skip_regulator,
            regulator_tier=args.regulator_tier,
            timeout_seconds=args.timeout,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    ddp_check_artifact._print_verdict(verdict, checked_path)
    ddp_check_artifact.record_receipt_best_effort(
        "ddp_check_artifact",
        {
            "artifact_root": str(root),
            "domain": args.domain,
            "artifact": str(artifact_path) if artifact_path else None,
            "skip_regulator": args.skip_regulator,
        },
        0 if verdict.final_status == "PASS" else 1,
        task=args.task_id,
        artifact_paths=[str(checked_path)],
    )
    return 0 if verdict.final_status == "PASS" else 1


def cmd_pipeline(args: argparse.Namespace) -> int:
    root = Path(args.artifact_root).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: artifact-root is not a directory: {root}", file=sys.stderr)
        return 2
    output = Path(args.output).expanduser().resolve() if args.output else None
    artifact = assemble_manifest(root, args.domain)
    written = write_artifact(artifact, output)
    assemble_receipt = ddp_artifact.record_assemble_receipt(
        artifact,
        written,
        exit_code=0,
        task_id=args.task_id or "",
    )
    if "record_error" in assemble_receipt:
        print(f"WARN: receipt write failed: {assemble_receipt['record_error']}", file=sys.stderr)

    try:
        verdict, checked_path = ddp_check_artifact.check_artifact(
            root,
            args.domain,
            written,
            skip_regulator=args.skip_regulator,
            regulator_tier=args.regulator_tier,
            timeout_seconds=args.timeout,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        ddp_check_artifact.record_receipt_best_effort(
            "ddp_pipeline",
            {
                "artifact_root": str(root),
                "domain": args.domain,
                "output": str(written),
                "gate_status": "ERROR",
                "skip_regulator": args.skip_regulator,
            },
            2,
            task=args.task_id,
            artifact_paths=[str(written)],
        )
        return 2

    artifact = replace(artifact, completeness_verdict=verdict.final_status)
    written = write_artifact(artifact, written)
    print(f"assembled DDP artifact: {written}")
    ddp_check_artifact._print_verdict(verdict, checked_path)
    exit_code = 0 if verdict.final_status == "PASS" else 1
    ddp_check_artifact.record_receipt_best_effort(
        "ddp_check_artifact",
        {
            "artifact_root": str(root),
            "domain": args.domain,
            "artifact": str(written),
            "skip_regulator": args.skip_regulator,
            "pipeline": True,
        },
        exit_code,
        task=args.task_id,
        artifact_paths=[str(checked_path)],
    )
    ddp_check_artifact.record_receipt_best_effort(
        "ddp_pipeline",
        {
            "artifact_root": str(root),
            "domain": args.domain,
            "output": str(written),
            "gate_status": verdict.final_status,
            "skip_regulator": args.skip_regulator,
        },
        exit_code,
        task=args.task_id,
        artifact_paths=[str(checked_path)],
    )
    if exit_code != 0:
        print(f"DDP pipeline blocked: check_ddp_artifact returned {verdict.final_status}", file=sys.stderr)
    return exit_code


def cmd_meaning_scaffold(args: argparse.Namespace) -> int:
    root = Path(args.artifact_root).expanduser().resolve()
    path = ddp_meaning_doc.scaffold_meaning(root, args.domain, overwrite=args.overwrite)
    print(f"meaning authority: {path}")
    ddp_check_artifact.record_receipt_best_effort(
        "ddp_meaning_scaffold",
        {
            "artifact_root": str(root),
            "domain": args.domain,
            "overwrite": args.overwrite,
        },
        0,
        task=args.task_id,
        artifact_paths=[str(path)],
    )
    return 0


def cmd_meaning_check(args: argparse.Namespace) -> int:
    root = Path(args.artifact_root).expanduser().resolve() if args.artifact_root else None
    if args.authority:
        authority = Path(args.authority).expanduser().resolve()
    elif root is not None and args.domain:
        authority = ddp_meaning_doc.meaning_authority_path(root, args.domain)
    else:
        print("ERROR: meaning check requires --authority or --artifact-root with --domain", file=sys.stderr)
        return 2
    if not authority.exists():
        print(f"ERROR: meaning authority does not exist: {authority}", file=sys.stderr)
        return 2

    if args.artifact:
        artifact_input: str | Path = Path(args.artifact).expanduser().resolve()
        if not Path(artifact_input).exists():
            print(f"ERROR: artifact does not exist: {artifact_input}", file=sys.stderr)
            return 2
    elif root is not None and args.domain:
        artifact_path = root / "DDP_ARTIFACT.md"
        if artifact_path.exists():
            artifact_input = artifact_path
        else:
            artifact_input = ddp_artifact.render_artifact(assemble_manifest(root, args.domain))
    else:
        print("ERROR: meaning check requires --artifact or --artifact-root with --domain", file=sys.stderr)
        return 2

    try:
        result = ddp_meaning_doc.check_pointer_anchor(artifact_input, authority)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(ddp_meaning_doc.format_check_result(result))
    exit_code = 0 if result.passed else 1
    ddp_check_artifact.record_receipt_best_effort(
        "ddp_meaning_check",
        {
            "authority": str(authority),
            "domain": args.domain or "",
            "verdict": result.verdict,
        },
        exit_code,
        task=args.task_id,
        artifact_paths=[str(artifact_input)] if isinstance(artifact_input, Path) else [],
    )
    return exit_code


def cmd_intake(args: argparse.Namespace) -> int:
    try:
        verbatim = Path(args.verbatim_file).expanduser().read_text(encoding="utf-8")
        result = ddp_intake.record_requirement(
            job=args.job,
            verbatim=verbatim,
            source_anchor=args.source_anchor,
            session_id=args.session_id,
            domain=args.domain,
            phase=args.phase,
            requirement_class=args.req_class,
            req_id=args.req_id,
            date=args.date,
            task_id=args.task_id,
            dry_run=args.dry_run,
        )
    except (OSError, requirement_append.AppendError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"{result.action} {result.target} {result.req_id} sha256={result.sha256}")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    root = Path(args.job).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: job is not a directory: {root}", file=sys.stderr)
        return 2
    artifact = assemble_manifest(root, args.domain)
    print(_render_coverage_rows(artifact))
    rows = _coverage_rows(artifact.streams)
    return 1 if any(row.gap_state == "unmet" for row in rows) else 0


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.artifact_root).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: artifact-root is not a directory: {root}", file=sys.stderr)
        return 2
    artifact = assemble_manifest(root, args.domain)
    artifact_path = root / "DDP_ARTIFACT.md"
    print(f"artifact_root: {root}")
    print(f"domain: {args.domain}")
    print(f"artifact_present: {str(artifact_path.exists()).lower()}")
    print(f"projection_verdict: {artifact.completeness_verdict}")
    print(_render_coverage_rows(artifact))
    ledger = Path(args.ledger).expanduser().resolve() if args.ledger else _default_receipts_ledger()
    receipts = _recent_receipts_for_root(root, ledger, args.receipt_limit)
    print(f"recent_receipts: {len(receipts)}")
    for row in receipts:
        print(
            f"- {row.get('event_id', '?')} {row.get('tool', '?')} "
            f"exit={row.get('exit_code', '?')} task={row.get('task_id', '')}"
        )
    return 0 if artifact.completeness_verdict == "PASS" else 1


def cmd_guide(args: argparse.Namespace) -> int:
    by_intent = {
        "requirement": [
            "DDP guide: requirement",
            "1. Preserve the user's verbatim requirement and source anchor.",
            "2. Use intake to write the authority stream:",
            "   python3 -m tools.ddp.cli intake --job <job> --verbatim-file <file> --source-anchor <anchor> --req-class design --domain <domain> --session-id <session> --task-id <task>",
            "3. For execution-only requirements, use --req-class execution --phase <phase>.",
        ],
        "meaning": [
            "DDP guide: meaning",
            "1. Create or reuse the meaning authority file:",
            "   python3 -m tools.ddp.cli meaning scaffold --artifact-root <job> --domain <domain>",
            "2. Keep meaning prose in requirements/meaning/<domain>.md.",
            "3. Verify the DDP artifact points to that authority instead of copying it:",
            "   python3 -m tools.ddp.cli meaning check --artifact-root <job> --domain <domain>",
        ],
        "design": [
            "DDP guide: design",
            "1. Create the design authority under design_docs/ using the design_doc scaffold.",
            "2. Assemble a pointer-backed projection:",
            "   python3 -m tools.ddp.cli assemble --artifact-root <job> --domain <domain>",
            "3. Run the blocking DDP gate before downstream consumption:",
            "   python3 -m tools.ddp.cli pipeline --artifact-root <job> --domain <domain> --skip-regulator",
        ],
    }
    if args.intent:
        print("\n".join(by_intent[args.intent]))
        return 0
    print(
        "\n".join(
            [
                "DDP CLI operator guide",
                "",
                "Commands:",
                "  assemble  Build DDP_ARTIFACT.md from requirements/meaning/design pointers.",
                "  check     Run the SL-3 check_ddp_artifact gate against an artifact root.",
                "  pipeline  Assemble, then run check; non-PASS gate status exits non-zero.",
                "  meaning   Scaffold/check the meaning authority pointer discipline.",
                "  intake    Record design/execution requirements through requirement_doc.",
                "  coverage  Print live per-stream gap_state rows from authorities.",
                "  status    Print read-only projection status plus recent matching receipts.",
                "  guide     Print this operational summary; use --intent for stream steps.",
                "",
                "Typical flow:",
                "  python3 tools/ddp/cli.py pipeline --artifact-root <job> --domain <domain> --skip-regulator",
                "",
                "Receipts:",
                "  Set TOOL_RECEIPTS_LEDGER=<tmp-or-run-ledger> for isolated tests.",
                "  PASS pipeline evidence is a ddp_pipeline receipt with exit_code=0.",
                "  FLAG/UNKNOWN blocks downstream with a non-zero exit and no PASS pipeline event.",
            ]
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ddp",
        description="Design Doc Protocol (DDP) composition layer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_asm = sub.add_parser("assemble", help="Assemble and write DDP_ARTIFACT.md projection.")
    p_asm.add_argument("--artifact-root", required=True, help="Folder holding the three streams.")
    p_asm.add_argument("--domain", required=True, help="Domain name (e.g. ddp_design_doc_protocol).")
    p_asm.add_argument(
        "--verdict",
        default=None,
        choices=("PASS", "FLAG", "UNKNOWN"),
        help=(
            "Optional completeness verdict token to stamp. Omit to compute the "
            "projection verdict from discovered stream pointers."
        ),
    )
    p_asm.add_argument("--output", default=None, help="Output path (default: <root>/DDP_ARTIFACT.md).")
    p_asm.add_argument("--task-id", default="", help="task_id for the tool receipt.")
    p_asm.set_defaults(func=cmd_assemble)

    p_chk = sub.add_parser("check", help="Run the SL-3 DDP completeness gate.")
    p_chk.add_argument("--artifact-root", required=True)
    p_chk.add_argument("--domain", required=True)
    p_chk.add_argument("--artifact", default=None, help="Existing DDP_ARTIFACT.md path.")
    p_chk.add_argument("--skip-regulator", action="store_true", help="Bypass DA5 regulator.")
    p_chk.add_argument("--regulator-tier", default="codex:high")
    p_chk.add_argument("--timeout", type=int, default=600)
    p_chk.add_argument("--task-id", default="", help="task_id for the tool receipt.")
    p_chk.set_defaults(func=cmd_check)

    p_pipe = sub.add_parser("pipeline", help="Assemble, gate, and block on non-PASS.")
    p_pipe.add_argument("--artifact-root", required=True)
    p_pipe.add_argument("--domain", required=True)
    p_pipe.add_argument("--output", default=None, help="Output path (default: <root>/DDP_ARTIFACT.md).")
    p_pipe.add_argument("--skip-regulator", action="store_true", help="Bypass DA5 regulator.")
    p_pipe.add_argument("--regulator-tier", default="codex:high")
    p_pipe.add_argument("--timeout", type=int, default=600)
    p_pipe.add_argument("--task-id", default="", help="task_id for the tool receipt.")
    p_pipe.set_defaults(func=cmd_pipeline)

    p_meaning = sub.add_parser("meaning", help="Scaffold/check the DDP meaning authority stream.")
    meaning_sub = p_meaning.add_subparsers(dest="meaning_command", required=True)
    p_meaning_scaffold = meaning_sub.add_parser("scaffold", help="Create requirements/meaning/<domain>.md.")
    p_meaning_scaffold.add_argument("--artifact-root", required=True)
    p_meaning_scaffold.add_argument("--domain", required=True)
    p_meaning_scaffold.add_argument("--overwrite", action="store_true", help="Replace existing authority file.")
    p_meaning_scaffold.add_argument("--task-id", default="", help="task_id for the tool receipt.")
    p_meaning_scaffold.set_defaults(func=cmd_meaning_scaffold)

    p_meaning_check = meaning_sub.add_parser("check", help="Check meaning pointer/hash/anchor adoption.")
    p_meaning_check.add_argument("--artifact-root", default=None)
    p_meaning_check.add_argument("--domain", default=None)
    p_meaning_check.add_argument("--artifact", default=None, help="Existing DDP artifact path.")
    p_meaning_check.add_argument("--authority", default=None, help="Meaning authority path.")
    p_meaning_check.add_argument("--task-id", default="", help="task_id for the tool receipt.")
    p_meaning_check.set_defaults(func=cmd_meaning_check)

    p_intake = sub.add_parser("intake", help="Record a design/execution requirement through DDP intake.")
    p_intake.add_argument("--job", required=True)
    p_intake.add_argument("--verbatim-file", required=True)
    p_intake.add_argument("--source-anchor", required=True)
    p_intake.add_argument("--req-class", choices=("design", "execution"), default="design")
    p_intake.add_argument("--domain", default=None)
    p_intake.add_argument("--phase", default=None)
    p_intake.add_argument("--session-id", required=True)
    p_intake.add_argument("--task-id", default="unknown")
    p_intake.add_argument("--req-id", default=None)
    p_intake.add_argument("--date", default="<date>")
    p_intake.add_argument("--dry-run", action="store_true")
    p_intake.set_defaults(func=cmd_intake)

    p_cov = sub.add_parser("coverage", help="Print live per-stream gap_state rows from authorities.")
    p_cov.add_argument("--job", required=True)
    p_cov.add_argument("--domain", required=True)
    p_cov.set_defaults(func=cmd_coverage)

    p_status = sub.add_parser("status", help="Print read-only projection status and recent receipts.")
    p_status.add_argument("--artifact-root", required=True)
    p_status.add_argument("--domain", required=True)
    p_status.add_argument("--ledger", default=None)
    p_status.add_argument("--receipt-limit", type=int, default=5)
    p_status.set_defaults(func=cmd_status)

    p_guide = sub.add_parser("guide", help="Print concise DDP CLI operator guidance.")
    p_guide.add_argument("--intent", choices=("requirement", "meaning", "design"), default=None)
    p_guide.set_defaults(func=cmd_guide)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
