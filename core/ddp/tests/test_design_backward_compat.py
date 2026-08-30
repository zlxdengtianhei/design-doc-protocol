from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

pytest.importorskip("tools.requirement_doc", reason="requirement_doc 集成面未随开源仓发布（见 README 已知集成面）；该测试只在母仓布局可跑")

from tools.requirement_doc import append, scaffold  # noqa: E402


def test_old_append_signature_and_design_id_are_stable(tmp_path: Path) -> None:
    job = tmp_path / "job"
    scaffold.scaffold_job(job, ["alpha"], "REQ")
    verbatim = "Design stream requirement stays anchored."
    source_anchor = "source.md:L1"
    expected_req_id = "REQ-" + hashlib.sha256(f"{source_anchor}\n{verbatim}".encode("utf-8")).hexdigest()[:8].upper()

    result = append.append_requirement(job, "alpha", verbatim, source_anchor, "session-1", expected_req_id, "2026-07-03")

    target = job / "requirements" / "design" / "alpha.md"
    assert append.derive_req_id(verbatim, source_anchor) == expected_req_id
    assert result.target.endswith("requirements/design/alpha.md")
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert f"#### {expected_req_id}" in text
    assert "requirement_class=design" in text
    assert "task_id=unknown" in text
