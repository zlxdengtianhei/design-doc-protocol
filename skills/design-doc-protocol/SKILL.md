---
name: design-doc-protocol
description: Update authoritative design documents when requirements change, trace affected consumers, recover incremental edits, and prepare a small implementation handoff.
---

# Design Doc Protocol

Use this skill when a new or corrected requirement changes a design, its consumers, or an implementation handoff. The authority stays in the project's existing design files. The `ddp` CLI checks file versions and applies exact changes; you decide whether the design and propagation satisfy the requirement.

## Start from the requirement

Locate the user's actual requirement and latest correction. Distinguish that text from summaries, suggestions and your own design choice. Choose the existing authority file for each affected concept. The default design root is `PROJECT/docs/design`; pass `--design-root` to use an existing layout. The requirement file is always explicit via `--request`. Program recovery state defaults to `PROJECT/.design-doc-protocol` and the one human change entry goes in the design root's `CHANGELOG.md`. Optional code documentation is read from an explicit `--code-docs` root. No other product or service is required.

For an update, run `ddp prepare --project-root PROJECT --change ID --request PATH --request-heading HEADING --target DESIGN_FILE` (repeat `--target` for each chosen authority). Its JSON gives the selected requirement section, each target's current hash and content, and Markdown reference candidates. Select targets by meaning; candidate matches can reveal missed consumers, but zero matches does not prove there are none. The CLI prints the packet to stdout so it can be trimmed to this task's necessary context.

## Design and propagate

The person or agent responsible for each design domain writes its authoritative meaning. For small updates, one role may handle design, propagation and deterministic checks. Use another role when the task needs a separate judgment; the protocol does not prescribe a fixed number of agents or a model family. In the current design, state the relevant input, output, failure and observable success behavior. When multiple documents consume a changed contract, search references and concepts beyond the CLI candidates. For every identified consumer, record `changed` or `unchanged` with a concrete reason. Update only the authority and consumers that need it. A reviewer may still find omissions; hashes and reference matches do not decide semantic completeness.

Create the small JSON plan described in [CLI plan format](references/CLI.md). It binds the requirement hash, each target's expected hash and an exact one-match replacement. Run `ddp apply --project-root PROJECT --plan PLAN.json`. If it reports a stale source or target, inspect the changed file and run `prepare` again before making a new plan. If the process stops during an operation, retry the identical plan: the CLI checks prior and post versions and completes remaining files and the one CHANGELOG entry. A completed retry is a no-op. Coordinate a single writer for each file; this is per-file recovery, not a multi-file transaction or arbitrary concurrent editing.

Use `ddp status --project-root PROJECT --change ID` to inspect the record and current hashes. `semantic_status: unknown` is intentional: verify the user's behavior with the real consumer and record failures or remaining uncertainty. The historical fixed-marker checker, when present, only reports marker completeness; its exit zero never means design acceptance. Follow the host's authorization and publication mechanism.

## Handoff and fresh roles

For an implementation handoff, include the goal and consumer, the requirement's exact source and program-reported version, only the necessary design sections, expected behavior with a failure case, allowed write area, open decisions, and who receives the result. When short target code and business tests are necessary and available, have a program include their pinned contents in the same packet so the recipient can act without repeated lookup. Do not hand-calculate hashes or size estimates. `ddp read --project-root PROJECT --path FILE --expected-sha256 HASH [--heading HEADING]` reads a pinned section; add `--code-docs ROOT` for a selected code documentation page. For that command, `--path` is relative to the selected code-docs root. Its returned JSON `path` is PROJECT-relative: for example, input `files/page.md` under `docs/codebase` returns `docs/codebase/files/page.md`. Copy that returned locator unchanged into the plan. When a code documentation page informs the design change, copy its program-returned version fields into the plan's optional `code_sources`; `apply` and `status` then check exactly those dependencies. A changed or missing version is an error, never an invitation to silently use the newest document. Compare whole-run provider usage and the same business outcome when evaluating token cost; initial packet length alone cannot establish savings.

When creating a new role, use the companion [Clean Context skill](../clean-context/SKILL.md) if it is installed; otherwise fulfill the same five-part handoff directly: task and role, necessary sources, properties to protect (such as independent judgment), actual fresh context and carrier, and output with a named consumer. Check what the host actually injects. Ordinary unrelated reading calls for stopping and disclosing the expansion. If answer or author-process leakage defeats a stated protected judgment, only that affected judgment must be redone with a clean role. A small task in the current role does not require another agent.

## Completion

Confirm the design's target behavior through a real reader or implementer, check the changed and unchanged consumers, and record the evidence in the existing change entry or host task record. Report the versions and scope actually checked. An implementation that can run and a reviewer who did not author it provide stronger evidence than a complete marker set.
