"""Tests for the SL-1 DDP meaning-stream helper."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ddp import artifact as ddp_artifact  # noqa: E402
from core.ddp import meaning_doc  # noqa: E402

DOMAIN = "ddp_design_doc_protocol"


def _write_meaning(root: Path) -> Path:
    path = root / "requirements" / "meaning" / f"{DOMAIN}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# Meaning - {DOMAIN}",
                "",
                "M1.0: Meaning is adopted by pointer to the authority stream.",
                "M2: Projection files must not copy this meaning body prose.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_scaffold_creates_canonical_path_and_preserves_existing_file(tmp_path):
    path = meaning_doc.scaffold_meaning(tmp_path, DOMAIN)
    assert path == tmp_path / "requirements" / "meaning" / f"{DOMAIN}.md"
    assert path.exists()

    path.write_text("existing meaning authority\n", encoding="utf-8")
    second = meaning_doc.scaffold_meaning(tmp_path, DOMAIN)

    assert second == path
    assert path.read_text(encoding="utf-8") == "existing meaning authority\n"


def test_pointer_resolves_for_generated_ddp_artifact(tmp_path):
    meaning_path = _write_meaning(tmp_path)
    artifact = ddp_artifact.assemble_manifest(tmp_path, DOMAIN)
    rendered = ddp_artifact.render_artifact(artifact)

    result = meaning_doc.check_pointer_anchor(rendered, meaning_path)

    assert result.verdict == "PASS"
    assert result.passed
    assert result.anchors == ("M1.0", "M2")


def test_hard_negative_flags_copied_meaning_body_instead_of_pointer(tmp_path):
    meaning_path = _write_meaning(tmp_path)
    copied_artifact = """
# DDP Artifact - bad

## Meaning Stream

M1.0: Meaning is adopted by pointer to the authority stream.
M2: Projection files must not copy this meaning body prose.
"""

    result = meaning_doc.check_pointer_anchor(copied_artifact, meaning_path)
    rendered = meaning_doc.format_check_result(result)

    assert result.verdict == "FLAG"
    assert "meaning pointer evidence absent" in result.issues
    assert meaning_doc.COPIED_MEANING_FLAG in result.issues
    assert "meaning copied instead of pointed" in rendered


def test_anchor_extraction_covers_subanchors_and_integer_anchors():
    text = "M1.0 names a sub-anchor. M2 names a sibling. M2 repeated."

    assert meaning_doc.extract_meaning_anchors(text) == ("M1.0", "M2")
