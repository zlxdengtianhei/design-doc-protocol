# DDP Artifact Spec

This file specifies the SL-0 `DDP_ARTIFACT.md` projection produced by
`tools/ddp`.

## Purpose

`DDP_ARTIFACT.md` is a derived manifest for one DDP domain. It makes the three
DDP streams visible in one place while preserving authority in the source files.

The artifact is a projection, not a source of truth.

## Inputs

Given `--artifact-root <root>` and `--domain <domain>`, SL-0 discovers:

| Stream | Candidate paths | Missing behavior |
|---|---|---|
| requirements | `<root>/requirements/design/<domain>.md` | `missing` |
| meaning | `<root>/requirements/meaning/<domain>.md`, `<root>/meaning/<domain>.md` | `not_yet_active` |
| design | `<root>/design_docs/<domain>_design.md`, `<root>/design_docs/<domain>-design.md`, `<root>/design_docs/design.md` | `missing` |

Meaning is `not_yet_active` when absent because SL-1 meaning validation is out of
scope for this slice.

## Output Shape

The generated markdown has:

1. YAML frontmatter under `ddp_artifact`
2. A title: `# DDP Artifact - <domain>` or equivalent heading text
3. One stream section each for requirements, meaning, and design
4. A coverage table

The implementation may use typographic punctuation in headings, but consumers
must rely on section labels and frontmatter keys instead of a single exact title
string.

## Frontmatter Contract

The frontmatter includes:

```yaml
ddp_artifact:
  domain: <domain>
  artifact_root: <absolute-or-resolved-root>
  streams:
    requirements:
      status: present | missing
      authority: <path-or-empty>
      source_hash: <sha256-or-empty>
    meaning:
      status: present | not_yet_active
      authority: <path-or-empty>
      source_hash: <sha256-or-empty>
    design:
      status: present | missing
      authority: <path-or-empty>
      source_hash: <sha256-or-empty>
  completeness_verdict: PASS | FLAG | UNKNOWN
  claim_ceiling: design-stage-ddp-artifact-assembly-only
  generated_by: tools/ddp/artifact.py
```

## Stream Section Contract

Each stream section includes:

- `status`
- `authority` when a source file exists
- `source_hash` when a source file exists
- stream-specific extracted metadata when available:
  - requirements: `req_ids` from `#### <req_id>` headings
  - meaning: `anchors` matching `M<number>` or `M<number>.<number>`
- `freshness`, currently `on_demand`

Authority file bodies are not copied into the artifact.

## Coverage Contract

The coverage table has columns:

| stream | status | gap_state | locator |
|---|---|---|---|

Status maps to `gap_state` as follows:

| status | gap_state |
|---|---|
| present | satisfied |
| missing | unmet |
| not_yet_active | deferred |

This coverage is an SL-0 projection only. It is not an SL-3 completeness gate.

## Receipts

`assemble` appends a best-effort `ddp_assemble` tool receipt with:

- `artifact_root`
- `domain`
- `output`
- `task_id`
- `artifact_paths`
- streams present
- stamped `completeness_verdict`
- `claim_ceiling`

Receipt failure must not make artifact assembly fail.

## Explicit Non-Goals

SL-0 does not:

- validate semantic meaning anchors
- decide whether requirements and design are mutually complete
- update requirement or design source files
- register a `tools/INDEX.md` entry by itself
- register any `unified_gate` or `phase_runtime` gate
