from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ddp import artifact as ddp_artifact  # noqa: E402
from core.ddp import check_artifact  # noqa: E402
from core.ddp import cli as ddp_cli  # noqa: E402

DOMAIN = "ddp_design_doc_protocol"
SOURCE_BODY = "Original requirement body stays in the authority source only for DDP validation."


def _build_valid_fixture(root: Path) -> dict[str, Path]:
    req = root / "requirements" / "design" / f"{DOMAIN}.md"
    req.parent.mkdir(parents=True, exist_ok=True)
    req.write_text(
        f"# Requirements - {DOMAIN}\n\n"
        f"#### {DOMAIN}-REQ-001\n"
        f"{SOURCE_BODY}\n\n"
        "provenance: source=prompt.md:L1 requirement_class=design task_id=SL-3\n",
        encoding="utf-8",
    )
    meaning = root / "requirements" / "meaning" / f"{DOMAIN}.md"
    meaning.parent.mkdir(parents=True, exist_ok=True)
    meaning.write_text("# Meaning\n\nM1.0 anchors the requirement.\n", encoding="utf-8")
    design = root / "design_docs" / f"{DOMAIN}_design.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text(_valid_design_doc(req), encoding="utf-8")
    return {"requirements": req, "meaning": meaning, "design": design}


def _valid_design_doc(req_path: Path) -> str:
    return f"""# DDP Design

## (0) Requirement Anchor

req-doc: `{req_path}`

## Layer 1 功能设计

### (core_need)

Check DDP artifact completeness from pointer-backed streams.

### (success_effect)

The gate returns PASS only when required streams and pointer evidence are complete.

### (hard_requirements)

Requirements and design streams are present, hashed, and pointer-only.

### (negative_requirements)

Do not copy source body text into the projection.

### (deliverable)

A command-line gate with actionable findings.

## Layer 2 实现设计

### 2.3 关键设计决策（含为什么）

| 决策 | 选择 | 理由 | 不选什么 |
|---|---|---|---|
| gate shape | unified_gate shell plus optional regulator | reuse shared verdict semantics | bespoke verdict code |

## Final Boundary

| 字段 | 值 |
|---|---|
| 状态 | DONE |
"""


def test_check_artifact_passes_valid_pointer_artifact(tmp_path: Path) -> None:
    _build_valid_fixture(tmp_path)

    verdict, artifact_path = check_artifact.check_artifact(
        tmp_path,
        DOMAIN,
        skip_regulator=True,
    )

    assert artifact_path == tmp_path / "DDP_ARTIFACT.md"
    assert verdict.final_status == "PASS", verdict.as_dict()


def test_missing_requirements_or_design_stream_returns_flag(tmp_path: Path) -> None:
    verdict, _artifact_path = check_artifact.check_artifact(
        tmp_path,
        DOMAIN,
        skip_regulator=True,
    )

    assert verdict.final_status == "FLAG"
    rendered = "\n".join(f.message for f in verdict.shell_findings)
    assert "requirements stream must be present" in rendered
    assert "design stream must be present" in rendered


def test_copied_verbatim_source_body_in_artifact_returns_flag(tmp_path: Path) -> None:
    _build_valid_fixture(tmp_path)
    artifact_obj = ddp_artifact.assemble_manifest(tmp_path, DOMAIN)
    artifact_path = ddp_artifact.write_artifact(artifact_obj)
    artifact_path.write_text(
        artifact_path.read_text(encoding="utf-8") + f"\n\nLeaked body: {SOURCE_BODY}\n",
        encoding="utf-8",
    )

    verdict, _artifact_path = check_artifact.check_artifact(
        tmp_path,
        DOMAIN,
        artifact_path,
        skip_regulator=True,
    )

    assert verdict.final_status == "FLAG"
    assert "source body copied into projection" in "\n".join(
        f.message for f in verdict.shell_findings
    )


def test_unbuilt_meaning_stream_without_not_yet_active_returns_flag(tmp_path: Path) -> None:
    paths = _build_valid_fixture(tmp_path)
    paths["meaning"].unlink()
    artifact_obj = ddp_artifact.assemble_manifest(tmp_path, DOMAIN)
    artifact_path = ddp_artifact.write_artifact(artifact_obj)
    text = artifact_path.read_text(encoding="utf-8")
    artifact_path.write_text(text.replace("status: not_yet_active", "status: missing"), encoding="utf-8")

    verdict, _artifact_path = check_artifact.check_artifact(
        tmp_path,
        DOMAIN,
        artifact_path,
        skip_regulator=True,
    )

    assert verdict.final_status == "FLAG"
    assert "not_yet_active" in "\n".join(f.message for f in verdict.shell_findings)


def test_cli_check_runs_sl3_gate_and_returns_zero_or_one(tmp_path: Path) -> None:
    _build_valid_fixture(tmp_path)

    assert (
        ddp_cli.main(
            [
                "check",
                "--artifact-root",
                str(tmp_path),
                "--domain",
                DOMAIN,
                "--skip-regulator",
            ]
        )
        == 0
    )


def test_check_artifact_regulator_stub_pass_preserves_gate_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build_valid_fixture(tmp_path)

    def fake_run(
        self, artifact_text: str, source_bundle: str = "", forbidden_read: str = ""
    ) -> dict[str, object]:
        return {
            "status": "PASS",
            "issues": [],
            "returncode": 0,
            "stderr": "",
            "parse_error": None,
            "raw_text": '{"verdict":"PASS","issues":[]}',
        }

    monkeypatch.setattr(check_artifact.DdpArtifactRegulator, "run", fake_run)

    verdict, _artifact_path = check_artifact.check_artifact(tmp_path, DOMAIN)

    assert verdict.final_status == "PASS", verdict.as_dict()
    assert verdict.source == "all"


def test_check_artifact_regulator_stub_flag_preserves_fail_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build_valid_fixture(tmp_path)

    def fake_run(
        self, artifact_text: str, source_bundle: str = "", forbidden_read: str = ""
    ) -> dict[str, object]:
        return {
            "status": "FLAG",
            "issues": [
                {
                    "locator": "DDP_ARTIFACT.md:1",
                    "why": "stub regulator counterexample",
                    "required_next_action": "repair the pointer projection",
                }
            ],
            "returncode": 0,
            "stderr": "",
            "parse_error": None,
            "raw_text": '{"verdict":"FLAG","issues":[{"locator":"DDP_ARTIFACT.md:1"}]}',
        }

    monkeypatch.setattr(check_artifact.DdpArtifactRegulator, "run", fake_run)

    verdict, _artifact_path = check_artifact.check_artifact(tmp_path, DOMAIN)

    assert verdict.final_status == "FLAG", verdict.as_dict()
    assert verdict.source == "regulator"
    assert verdict.regulator_issues[0].locator == "DDP_ARTIFACT.md:1"


def test_check_artifact_regulator_stub_unknown_remains_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build_valid_fixture(tmp_path)

    def fake_run(
        self, artifact_text: str, source_bundle: str = "", forbidden_read: str = ""
    ) -> dict[str, object]:
        return {
            "status": "UNKNOWN",
            "issues": [],
            "returncode": -1,
            "stderr": "provider busy",
            "parse_error": "provider busy",
            "raw_text": "",
        }

    monkeypatch.setattr(check_artifact.DdpArtifactRegulator, "run", fake_run)

    verdict, _artifact_path = check_artifact.check_artifact(tmp_path, DOMAIN)

    assert verdict.final_status == "FLAG", verdict.as_dict()
    assert verdict.source == "regulator"
    assert verdict.regulator_raw is not None
    assert verdict.regulator_raw["status"] == "UNKNOWN"


def test_gate_registry_interim_check_ddp_artifact_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gate_registry = pytest.importorskip("tools.phase_runtime.gate_registry", reason="phase_runtime 门禁登记面未随开源仓发布（D4 移交项）；只在母仓布局可跑")

    _build_valid_fixture(tmp_path)

    assert "check_ddp_artifact" in gate_registry.known_gate_ids()
    original_gate_command = gate_registry.manifest.gate_command

    def shell_only_gate_command(gate_id: str, arg: str) -> list[str]:
        command = original_gate_command(gate_id, arg)
        if gate_id == "check_ddp_artifact":
            return [*command, "--skip-regulator"]
        return command

    monkeypatch.setattr(gate_registry.manifest, "gate_command", shell_only_gate_command)
    result = gate_registry.run_gate_pass_predicate(f"gate_pass:check_ddp_artifact:{tmp_path}")

    assert result.passed, result.detail


@pytest.mark.integration
def test_gate_registry_interim_check_ddp_artifact_overlay_real_regulator(tmp_path: Path) -> None:
    gate_registry = pytest.importorskip("tools.phase_runtime.gate_registry", reason="phase_runtime 门禁登记面未随开源仓发布（D4 移交项）；只在母仓布局可跑")

    if os.environ.get("RUN_PROVIDER_INTEGRATION") != "1":
        pytest.skip("set RUN_PROVIDER_INTEGRATION=1 to spend provider credits on the real regulator path")
    _build_valid_fixture(tmp_path)

    assert "check_ddp_artifact" in gate_registry.known_gate_ids()
    result = gate_registry.run_gate_pass_predicate(f"gate_pass:check_ddp_artifact:{tmp_path}")

    assert result.passed, result.detail


def test_meaning_pointer_adoption_reported_pass_on_valid_artifact(tmp_path: Path) -> None:
    _build_valid_fixture(tmp_path)

    verdict, _artifact_path = check_artifact.check_artifact(
        tmp_path,
        DOMAIN,
        skip_regulator=True,
    )

    assert verdict.final_status == "PASS", verdict.as_dict()
    meaning_findings = [f for f in verdict.shell_findings if f.check_id == "DA2.MEANING"]
    assert meaning_findings, "DA2.MEANING check must run when meaning stream is present"
    assert all(f.status == "PASS" for f in meaning_findings)


def test_meaning_copied_prose_in_artifact_flags_da2_meaning(tmp_path: Path) -> None:
    _build_valid_fixture(tmp_path)
    artifact_obj = ddp_artifact.assemble_manifest(tmp_path, DOMAIN)
    artifact_path = ddp_artifact.write_artifact(artifact_obj)
    # Pointer evidence stays intact; the copied meaning body alone must trip the gate.
    copied_body = "M1.0 anchors the requirement."
    artifact_path.write_text(
        artifact_path.read_text(encoding="utf-8") + f"\n{copied_body}\n",
        encoding="utf-8",
    )

    verdict, _checked = check_artifact.check_artifact(
        tmp_path,
        DOMAIN,
        artifact_path,
        skip_regulator=True,
    )

    assert verdict.final_status == "FLAG"
    rendered = "\n".join(f"{f.check_id} {f.message}" for f in verdict.shell_findings)
    assert "DA2.MEANING" in rendered
    assert "meaning copied instead of pointed" in rendered
