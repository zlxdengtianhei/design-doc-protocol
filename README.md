# Design Doc Protocol

DDP updates existing design documents against versioned requirements and ships two agent skills. The `ddp` CLI requires Python 3.10+; installation includes its CommonMark parser. [LICENSE](LICENSE) is MIT. It does not require this repository, a model provider, or a private workspace at runtime.

## Install in one line

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. On macOS or Linux, run this single shell line from the project where you want agent skills, then choose Codex, Claude Code, DSH, OpenCode, or a custom skill parent directory when prompted:

```sh
uv tool install 'https://github.com/zlxdengtianhei/design-doc-protocol/archive/refs/heads/main.zip' && "$(uv tool dir --bin)/ddp-install" install --interactive
```

For automation, replace `--interactive` with `--host codex --scope project --project "$PWD"` (repeat `--host` for several hosts, or use `--host all`). `--scope user` installs into the selected host's personal skill directory; `--dir '/path/with spaces/skills'` selects an explicit parent directory. The command installs the `ddp` and `ddp-install` executables through uv's isolated tool environment, then copies the wheel-bundled `design-doc-protocol` and `clean-context` skills, including references and the read-only `workflow.py`, to the chosen location. The install path is separate from the project's design documents (`PROJECT/docs/design` by default).

The installed design skill and installer output include an absolute `python -m ddp` entry from the isolated tool environment, so a host can invoke it even when uv's executable directory is absent from PATH. Re-run `ddp-install upgrade` if that environment moves.

After installation, run `"$(uv tool dir --bin)/ddp" --help` and `"$(uv tool dir --bin)/ddp-install" doctor --host codex --project "$PWD"` (adjust the host or use `--dir`). A first read-only task is `ddp prepare --project-root PROJECT --change ID --request docs/design/requirements.md --target DESIGN.md`; see [CLI plan format](skills/design-doc-protocol/references/CLI.md). The installer refuses to overwrite a skill it does not own or a file changed since installation.

Upgrade CLI and skills with `uv tool install --reinstall --refresh 'https://github.com/zlxdengtianhei/design-doc-protocol/archive/refs/heads/main.zip' && "$(uv tool dir --bin)/ddp-install" upgrade --host codex --project "$PWD"`. The archive installation does not require Git. Uninstall skills with `ddp-install uninstall --host codex --project "$PWD"`, then remove the isolated CLI with `uv tool uninstall design-doc-protocol`. Only installer-owned, unchanged skill files are removed; design documents, DDP state, and user files stay in place. For errors, run `ddp-install doctor` to check the runtime and wheel resources, then `doctor` with your host or custom directory to check the installed files.

The v0.5 public `core/` tree is a historical API; the 0.6 wheel exposes `ddp` and `ddp-install` rather than importing that tree. Existing callers of `core/` should remain pinned to v0.5 until migrated to the CLI contract.

## Design first, with small updates

Keep the user's requirement as the source of intent. The current design explains
inputs, outputs, failures, observable behavior, and decisions; code documentation
supplies implementation facts. Update the existing authority and affected
consumers when a requirement changes. One person or agent can handle a small
update. Use an independent reviewer when the judgment calls for it, rather than
adding a fixed set of roles to every change.

The CLI performs version, replacement, replay, and recovery checks. The agent
judges whether the design actually satisfies the requirement and whether all
consumers were considered. `semantic_status: unknown` is deliberate: a matching
hash or complete step marker cannot prove semantic correctness.

## Storage and reading

Paths are relative to the target project, independent of the skill installation.
Existing layouts are supported through explicit path flags; no filesystem service
or shared database is required.

| Content | Default / option |
| --- | --- |
| Requirement source | Explicit `--request`; examples use `docs/design/requirements.md` |
| Current design and one change record | `docs/design/`, including `CHANGELOG.md`; `--design-root` |
| Recovery state | `.design-doc-protocol/`; `--state-dir` |
| Optional Codebase Explorer output | `docs/codebase/INDEX.md`; select pages with `--code-docs` |

Run `ddp prepare` for the chosen requirement section and target documents. Its
packet includes current hashes, selected text, and reverse Markdown reference
candidates. Candidates are hints, not a complete semantic dependency graph.
Describe the small replacements and the affected consumers using the
[plan format](skills/design-doc-protocol/references/CLI.md), then run `ddp apply`.
Related source or target changes are rejected; an unrelated requirement section
can change without invalidating a section-bound plan. Top-level ATX and Setext
headings use CommonMark source ranges, so headings inside code, HTML, lists or
quotes cannot silently truncate a requirement. Retrying the identical plan
completes an interrupted operation or returns a no-op for an already completed
change. `ddp read` requires the expected hash for a design or selected CBE page.
Put the returned version fields for any code pages used by the design into the
plan's optional `code_sources`. Those selected dependencies are checked again
on apply/recovery and by status; their relevant changes mark the record stale.
Without code sources, DDP runs independently. Paths, including a custom
`--code-docs` root, stay inside `--project-root`; use a common workspace root
when design and code documentation live in different project folders.

Updates currently edit existing UTF-8 files with unique exact replacements.
Creating/deleting design files uses the host's normal file workflow. Coordinate
one writer per file: recovery is per-file and does not promise a multi-file
transaction or arbitrary concurrent editing.

## Skills and development

- [Design Doc Protocol](skills/design-doc-protocol/SKILL.md) guides requirement
  anchoring, design updates, propagation, handoff, and acceptance.
- [Clean Context](skills/clean-context/SKILL.md) describes the five parts of a
  focused fresh handoff and how to handle actual input leakage. It does not
  require another agent for a small task or prescribe a model.
- The packaged `workflow.py` checks historical step markers only. It is optional
  compatibility tooling, not a completion or semantic gate.

The public package contains `ddp/`, `ddp_install/`, and the two canonical skills.
The old public `core/` and `docs/protocol.md` remain historical v0.5 material and
are not imported by the new runtime. Private development histories and model
credentials are not part of the installation.

For development, install this checkout in an isolated environment and run
`python -m unittest discover -s tests -v`. Publishing checks build a wheel and
exercise installation outside the source tree. Evaluate token usage over the
whole model session and the same business outcome; a shorter initial packet
alone does not establish a saving.
