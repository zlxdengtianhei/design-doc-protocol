# DDP Tool

`core/ddp` is the Design Doc Protocol tool package for SL-0 through SL-3
surfaces.

It assembles a pointer-backed `DDP_ARTIFACT.md` projection from three existing
authority streams:

- requirements: `requirements/design/<domain>.md`
- meaning: `requirements/meaning/<domain>.md` or `meaning/<domain>.md`
- design: `design_docs/<domain>_design.md`, `design_docs/<domain>-design.md`, or
  `design_docs/design.md`

The projection records file paths, source hashes, stream status, extracted
requirement IDs, meaning anchors, and a coverage table. It does not copy the
authority bodies into the generated artifact.

## Layers And Commands

### SL-0: Artifact projection

Assemble and write a projection:

```bash
python3 -m tools.ddp.cli assemble \
  --artifact-root <job-or-run-root> \
  --domain <domain> \
  --output <path>/DDP_ARTIFACT.md \
  --task-id <task-id>
```

### SL-3: Completeness gate

Run the DDP artifact completeness gate:

```bash
python3 -m tools.ddp.cli check \
  --artifact-root <job-or-run-root> \
  --domain <domain>
```

Assemble the projection and then run the SL-3 gate in one command:

```bash
python3 -m tools.ddp.cli pipeline \
  --artifact-root <job-or-run-root> \
  --domain <domain>
```

### SL-1: Meaning stream

`core/ddp/meaning_doc.py` owns the meaning authority helpers:

- `scaffold_meaning(...)` creates `requirements/meaning/<domain>.md`.
- `extract_meaning_anchors(...)` extracts visible meaning anchors.
- `check_pointer_anchor(...)` checks that the artifact points to the meaning
  authority by path/hash/anchors instead of copying meaning prose.

CLI:

```bash
python3 -m tools.ddp.cli meaning scaffold \
  --artifact-root <job-or-run-root> \
  --domain <domain>

python3 -m tools.ddp.cli meaning check \
  --artifact-root <job-or-run-root> \
  --domain <domain>
```

### SL-2: Intake routing

`core/ddp/intake.py` owns the thin DDP-facing requirement intake wrapper:

- `record_requirement(...)` routes design/execution requirements through the
  deterministic `requirement_doc/append.py（母仓集成面，未随仓）` path.

CLI:

```bash
python3 -m tools.ddp.cli intake \
  --job <job-or-run-root> \
  --verbatim-file <requirement.txt> \
  --source-anchor <source:path-or-line> \
  --req-class design \
  --domain <domain> \
  --session-id <session> \
  --task-id <task>

python3 -m tools.ddp.cli intake \
  --job <job-or-run-root> \
  --verbatim-file <requirement.txt> \
  --source-anchor <source:path-or-line> \
  --req-class execution \
  --phase <phase> \
  --session-id <session> \
  --task-id <task>
```

### Live coverage and status

`coverage` computes live per-stream `gap_state` rows from the authority files;
it writes no projection file. It exits non-zero when any stream is `unmet`.

```bash
python3 -m tools.ddp.cli coverage \
  --job <job-or-run-root> \
  --domain <domain>
```

`status` is read-only. It prints whether `DDP_ARTIFACT.md` exists, the current
projection verdict computed from authorities, live coverage rows, and recent
matching receipts from `TOOL_RECEIPTS_LEDGER` or the central receipts ledger.

```bash
python3 -m tools.ddp.cli status \
  --artifact-root <job-or-run-root> \
  --domain <domain>
```

`guide --intent requirement|meaning|design` prints the deterministic next
operation for each stream.

### SL-3: Artifact gate

`core/ddp/check_artifact.py` owns `check_ddp_artifact`:

- DA1-DA4 deterministic checks cover stream presence, pointer/hash evidence,
  requirement-class routing, and not-yet-active semantics.
- DA5 regulator checks pointer-not-copy and coverage faithfulness from the
  supplied source bundle.
- `python3 -m tools.ddp.cli check` and `python3 -m tools.ddp.cli pipeline`
  expose this gate.

## Projection Boundary

`assemble` computes the projection-level `completeness_verdict` by default from
the discovered stream pointers: requirements and design must be present and
hashed; meaning may be present or explicitly `not_yet_active`. Passing
`--verdict PASS`, `--verdict FLAG`, or `--verdict UNKNOWN` overrides that
computed projection token for callers that already have a stronger verdict.

`pipeline` assembles the projection, runs the SL-3 gate, and then re-stamps the
written artifact with the gate verdict. The projection-level computation is only
the AD-09 shell signal; deeper DA1-DA5 completeness is still owned by the SL-3
gate above.

## Tests

```bash
python3 -m pytest core/ddp/tests/test_artifact.py
```
