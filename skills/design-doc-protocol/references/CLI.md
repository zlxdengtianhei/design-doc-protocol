# DDP CLI plan format

The package exposes `python -m ddp` and the installed console command `ddp`. Both return JSON on stdout, errors on stderr, and exit 2 for input, version or recovery conflicts. Python 3.10+ and the packaged `markdown-it-py==4.0.0` dependency are required. `ddp --help` lists all parameters.

`prepare` reads an explicit requirement path within `--project-root`, a chosen heading if supplied, selected `--target` files within `--design-root`, and reverse Markdown references as candidates. It does not write files. The JSON output gives project-relative paths and SHA-256 hashes. Add one `--target-heading HEADING` per target to include only that unique section in the packet while retaining the full-file hash. Copy the request path, SHA-256, heading and section SHA-256 (when present) and each target path/hash into the plan below; modify only the small replacement fields. A change to another section of the same requirement file does not stale a heading-bound plan; a change to the chosen section does. A target's `old` text must occur exactly once in its version. The current first slice edits existing UTF-8 design files; create a genuinely new file through the host's normal process, then prepare its first update. Deletion is not supported.

```json
{
  "change_id": "csv-header-01",
  "request": {"path": "docs/design/requirements.md", "sha256": "64 lowercase hex digits from prepare", "heading": "CSV export", "section_sha256": "64 lowercase hex digits from prepare"},
  "edits": [
    {"path": "docs/design/export.md", "expected_sha256": "64 lowercase hex digits from prepare", "old": "Empty export returns [].", "new": "Empty CSV export retains the header and has zero data rows."}
  ],
  "code_sources": [
    {"path": "docs/codebase/export-module.md", "sha256": "64 lowercase hex digits from ddp read", "heading": "Export API", "section_sha256": "64 lowercase hex digits from ddp read"}
  ],
  "consumers": [
    {"path": "docs/design/export.md", "decision": "changed", "reason": "authority for CSV export"},
    {"path": "docs/design/auth.md", "decision": "unchanged", "reason": "authentication does not consume export behavior"}
  ]
}
```

Use `ddp apply --project-root PROJECT --plan PLAN.json` or `--plan -` to read standard input. All edits are prevalidated before a document is written. A recovery journal appears under `--state-dir/operations`; do not hand-edit it. The one `ddp-change` JSON block in `CHANGELOG.md` contains the source version, changed paths and hashes, and consumer decisions. Retry the same plan after a stopped run. If a source or target changed outside the operation, stop and prepare a new plan. The CLI assumes one coordinated writer per file; a separate process modifying a file during the tiny read-to-replace interval is outside its guarantee.

`code_sources` is optional. Include only code documentation pages actually used to make this design change. Copy `path`, `sha256`, and, for a selected heading, `heading` and `section_sha256` from `ddp read` output. The program drops `content` if a full read result is supplied; no page body is stored in the journal or CHANGELOG. The selected sources enter the operation identity and are checked before initial apply and every replay, including recovery after partial writes. A changed or missing selected page makes `status` stale or incomplete conflict. A heading-bound page may change elsewhere without invalidating this dependency; an entire-page binding becomes stale on any file change. Plans without `code_sources` remain independent and retain their earlier operation digest.

Use `ddp read --project-root PROJECT --path FILE --expected-sha256 HASH` for a pinned design file. With `--code-docs ROOT`, `FILE` is relative to that optional read-only root. `--heading` selects one unique top-level Markdown heading, ATX or Setext. A Markdown parser identifies headings outside fenced code, HTML comments and containers; headings inside a quote or list are not selectable. An ambiguous or missing heading fails with guidance to omit `--heading` and bind the whole file. The read result's `path` is relative to PROJECT and can be used in `code_sources`; custom `--code-docs` roots may be anywhere **within** PROJECT. If design, code docs and state live in different subdirectories, choose their common ancestor as `--project-root` and pass explicit roots. A root outside PROJECT is rejected. `ddp status --project-root PROJECT --change ID` reports mechanical state and always leaves semantic status unknown.
