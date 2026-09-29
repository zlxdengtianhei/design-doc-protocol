"""JSON CLI for the DDP update and read contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import DDPError, apply, prepare, read, status


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ddp", description="Version-bound design document updates")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("prepare", "apply", "read", "status"):
        command = sub.add_parser(name)
        command.add_argument("--project-root", required=True)
        if name in {"prepare", "apply", "status"}:
            command.add_argument("--design-root")
            command.add_argument("--state-dir")
        if name == "prepare":
            command.add_argument("--change", required=True)
            command.add_argument("--request", required=True)
            command.add_argument("--request-heading")
            command.add_argument("--target", action="append", required=True,
                                 help="Path within design root; repeat for each authority file")
            command.add_argument("--target-heading", action="append",
                                 help="Optional unique Markdown heading, once per --target, to limit the packet excerpt")
            command.add_argument("--code-docs")
        elif name == "apply":
            command.add_argument("--plan", required=True, help="JSON plan file, or - for stdin")
        elif name == "read":
            command.add_argument("--path", required=True)
            command.add_argument("--expected-sha256", required=True)
            command.add_argument("--heading")
            command.add_argument("--code-docs", help="If supplied, --path is within this read-only root")
        else:
            command.add_argument("--change", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.project_root, args.change, args.request, args.target,
                             request_heading=args.request_heading, design_root=args.design_root,
                             state_dir=args.state_dir, code_docs=args.code_docs,
                             target_headings=args.target_heading)
        elif args.command == "apply":
            raw = sys.stdin.read() if args.plan == "-" else Path(args.plan).read_text(encoding="utf-8")
            try:
                plan = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise DDPError(f"invalid plan JSON: {exc}") from exc
            result = apply(args.project_root, plan, design_root=args.design_root, state_dir=args.state_dir)
        elif args.command == "read":
            result = read(args.project_root, args.path, args.expected_sha256,
                          heading=args.heading, code_docs=args.code_docs)
        else:
            result = status(args.project_root, args.change, design_root=args.design_root, state_dir=args.state_dir)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (DDPError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "command": args.command}, ensure_ascii=False), file=sys.stderr)
        return 2
