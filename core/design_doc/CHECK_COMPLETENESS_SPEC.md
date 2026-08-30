# SPEC - design_doc check_completeness

## 1. Background

`design_doc_scaffold` creates a three-layer design document skeleton. The failure
mode this checker blocks is treating that skeleton as a completed design. The
checker follows `workflow_design_doc_protocol` and the V1-V6 detector contract from
`workflow_complexity_drift_detection`.

## 2. Inputs and Outputs

Input artifact: one markdown design document generated from the design_doc scaffold
shape:

- Requirement / meaning / design faces when the tri-face scaffold is present.
- Current `on-demand-v1` documents carry `d9_contract | on-demand-v1` and a D9
  applicability table. Historical documents without that marker remain readable
  under the legacy five-field contract and are not current-contract certified.
- Layer 1 functional design. Current documents always require `success_effect`
  and `negative_requirements`; legacy documents retain five required fields.
- Layer 2/3 content is conditional on the D9 table state.
- Final Boundary table.

Output verdicts:

- `PASS`: the deterministic shell finds no DC1/DC2 issue.
- `FLAG`: placeholders remain in a filled face, current required fields are
  missing or empty, a D9 state is unwritten/invalid, a `not_applicable` row lacks
  a reason or trigger evaluation, a trigger is active while the row says
  `not_applicable`, required Layer 2/3 structure is missing, Final Boundary
  status has not chosen a state, the tri-face scaffold fails DC6 shell checks,
  or a filled design face cites an existing implementation path without a
  reference-only marker.

`check_completeness.py` exits `1` for `FLAG`, `0` for `PASS`, and `2` for input or
runtime errors. With `--regulator`, a parsed regulator `FLAG` or missing regulator
verdict also makes the CLI exit `1`.

## 3. Deterministic Shell

The shell has no LLM calls and implements DC1/DC2/DC6:

1. Scan the document for the generic placeholder pattern `<...>`.
   - Legacy documents with no `face_status` marker keep the old full-document
     scan.
   - Tri-face documents use the status gate: placeholders are flagged only in
     faces whose `face_status` is `filled`; `unwritten` faces may retain
     placeholders for asynchronous follow-up.
2. For every placeholder, report line number, current markdown section, inferred
   field or table row label, and the placeholder value.
3. Detect the explicit `d9_contract | on-demand-v1` marker. Without it, use the
   legacy compatibility path described below.
4. Locate Layer 1 required headings by title or schema name. In current mode the
   required set is `success_effect` and `negative_requirements`; in legacy mode
   the required set remains `core_need`, `success_effect`, `hard_requirements`,
   `negative_requirements`, `deliverable`.
5. Mark a Layer 1 field empty when its section has no substantive content after
   stripping markdown bullets, code fences, table separators, and placeholders.
6. In current mode, locate the D9 table with `layer`, `state`, `reason`, and
   `trigger_evaluation` columns and one row each for Layer 2 and Layer 3. Each
   named trigger must have a structural true/false evaluation. `unwritten` is
   incomplete; `not_applicable` additionally requires a substantive reason and
   must not coexist with an active trigger. `required` is valid only when at
   least one named trigger is exactly `true`; all named triggers being `false`
   is a state/trigger contradiction and is FLAGged. A valid `required` row then
   invokes the corresponding Layer 2 decision table or Layer 3 delta list
   checks. `filled` is reserved for the independent `face_status` state machine
   and is invalid as a current D9 layer state. In legacy mode, require the
   Layer 2 key decision table to have at least one data row with four filled
   cells: decision, choice, reason, rejected alternative.
7. Locate Final Boundary and require the `状态` row to choose one of `DONE`,
   `PARTIAL`, or `BLOCKED`. The unchosen scaffold string `DONE / PARTIAL / BLOCKED`
   is flagged.
8. When a tri-face scaffold is present, run DC6 shell checks:
   - `§需求面`, `§意义面`, and `§设计面` all exist.
   - Each face has `face_status` and the value is `unwritten` or `filled`.
   - Each face carries both `设计需求` and `执行需求` labels.
   - `§意义面` has a `承接总领意义` slot that points at
     `CROSS_DOMAIN_MEANING.md` (canonical location: `rules/meaning/CROSS_DOMAIN_MEANING.md`;
     three-layer anchors indexed at `rules/meaning/INDEX.md`). The check matches the
     file-name string only and does not constrain the path.
   - `§意义面` includes M1-M5 structure. If the meaning face is `filled`, the
     top-level meaning pointer must cite item `1-13` or `A/B/C`.
9. DC7 removed (2026-08-30, D4 slimming audit, see the
   internal D4 slimming audit record, not included in this repo):
   the reference-only marker rule was a mechanical gate over a semantic
   obligation and produced friction without a recorded real failure it
   prevented. Its obligation moved into the regulator's DC3 judgement (design
   face must keep implementation truth in the referenced files, not in the
   design document's own description). No deterministic DC7 check remains.

The predicate is generic: markdown headings, table structure, and placeholder
patterns. T631 content does not enter the predicate.

### 3.1 D9 trigger vocabulary and claim ceiling

Layer 2 triggers are `multiple_paths`, `handoff`, `user_confirmation`, and
`cross_file_impact`. Layer 3 triggers are `existing_object_disposition`,
`implementation_writeback`, and `direct_multi_file_execution`. The checker
requires each key to occur as a `key=true|false`-style structural value and
rejects `yes/no`, `active/inactive`, `triggered/not_triggered`, and other value
aliases. It does not decide whether the value is semantically correct, whether
the reason is persuasive, or whether the selected layer would produce a
successful run.
The bidirectional state predicate is structural only: the checker does not decide
whether a trigger value is truthful, but it does reject `required` with no named
`true` trigger. The P4 claim ceiling is
`p4_d9_static_structural_reconciliation_only_no_protocol_effect_claim`.

Legacy documents are read for historical comparison only. Absence of the D9
marker does not grant the current on-demand-v1 contract and does not force a
bulk migration of old artifacts.

## 4. Regulator

The regulator is called through `cli_agent`:

```bash
python3 tools/cli_agent/router.py --primary claude-zai:high --timeout 600
```

or another explicit high-tier route such as `codex:high`. The checker passes only
the line-numbered design document text. It does not pass author reasoning, sibling
artifacts, chat history, or repository files.

Regulator tasks:

- DC3: identify fields that merely echo the requirement or use vague completion
  phrases instead of design content.
- DC4: identify Layer 2 decisions that lack a real reason or a rejected alternative
  with reason.
- DC5: identify component responsibility overlap and missing concrete forbidden
  read boundaries.
- DC6: identify meaning faces that only restate the requirement or design plan
  instead of explaining why the design exists and which root/context gap it
  addresses.
- Output strict JSON:

```json
{
  "verdict": "PASS|FLAG",
  "dc3_issues": [{"field": "...", "line": 0, "problem": "...", "fix": "..."}],
  "dc4_issues": [{"decision": "...", "line": 0, "problem": "...", "fix": "..."}],
  "dc5_issues": [{"unit": "...", "line": 0, "problem": "...", "fix": "..."}],
  "dc6_issues": [{"field": "...", "line": 0, "problem": "...", "fix": "..."}],
  "actionable_signal": "...",
  "evidence": ["..."]
}
```

`run_oracle.py` saves raw regulator output for human judgment. It does not use the
regulator result as the oracle exit gate.

## 5. Oracle Fixtures

- Real positive: `fixtures/T631_git-env-cleanup-design.md` (vendored from the internal corpus).
  Expected deterministic verdict: `FLAG`.
- Hard negative: `fixtures/pass_check_completeness_self_design.md`.
  Expected deterministic verdict: `PASS`.
- DC3 soft negative: `fixtures/dc3_echo_soft_negative.md`.
  Expected deterministic verdict: `PASS`; regulator should `FLAG` because content
  is vague requirement echo.
- Tri-face status-gate fixtures in `tests/test_check_completeness.py`:
  - Unwritten meaning face with placeholders: deterministic verdict `PASS`.
  - Filled meaning face with placeholders: deterministic verdict `FLAG`.
  - Missing meaning pointer slot: deterministic verdict `FLAG`.
  - Invalid face status: deterministic verdict `FLAG`.
- DC7 fixtures removed together with the check (2026-08-30 D4 audit); the
  obligation is covered by the regulator DC3 prompt, exercised through the
  regulator path rather than a deterministic fixture.

## 6. Validation Contract

- `python3 core/design_doc/run_oracle.py --reps 0` must exit `0`.
- Model calls must use `--timeout >= 600`.
- Regulator raw output is logged under `core/design_doc/logs/`.
- The bounded claim is limited to this detector and these verified documents.
