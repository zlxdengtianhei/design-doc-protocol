"""Installation ownership and host path behavior, using the installed wheel."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from ddp_install import cli


def test_custom_path_repeat_and_user_change(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "skills with spaces"
    assert cli.main(["install", "--dir", str(root)]) == 0
    skill = root / cli.SKILLS[0]
    source = cli._resource_files(cli.SKILLS[0])
    assert (skill / "SKILL.md").read_bytes() == source["SKILL.md"]
    assert cli.main(["install", "--dir", str(root)]) == 0
    assert "unchanged" in capsys.readouterr().out

    (skill / "SKILL.md").write_text("user edit\n", encoding="utf-8")
    assert cli.main(["upgrade", "--dir", str(root)]) == 2
    assert cli.main(["uninstall", "--dir", str(root)]) == 2
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "user edit\n"
    assert "user-modified" in capsys.readouterr().err


def test_upgrade_and_uninstall_preserve_unowned_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    assert cli.main(["install", "--dir", str(root)]) == 0
    skill = root / cli.SKILLS[0]
    (skill / "my-notes.md").write_text("keep me\n", encoding="utf-8")
    original = cli._resource_files

    def updated(name: str) -> dict[str, bytes]:
        payload = original(name).copy()
        if name == cli.SKILLS[0]:
            payload["new-reference.md"] = b"release update\n"
        return payload

    monkeypatch.setattr(cli, "_resource_files", updated)
    assert cli.main(["upgrade", "--dir", str(root)]) == 0
    assert (skill / "new-reference.md").read_bytes() == b"release update\n"
    assert (skill / "my-notes.md").read_text(encoding="utf-8") == "keep me\n"
    assert cli.main(["uninstall", "--dir", str(root)]) == 0
    assert (skill / "my-notes.md").read_text(encoding="utf-8") == "keep me\n"
    assert not (skill / "SKILL.md").exists()
    assert not (skill / "new-reference.md").exists()
    assert not (skill / cli.MANIFEST).exists()


def test_interactive_custom_and_project_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "chosen skills"
    monkeypatch.setattr("sys.stdin", io.StringIO(f"custom\n{custom}\n"))
    assert cli.main(["install", "--interactive"]) == 0
    for name in cli.SKILLS:
        assert (custom / name / "SKILL.md").is_file()

    project = tmp_path / "project"
    project.mkdir()
    assert cli.main(["install", "--host", "all", "--project", str(project)]) == 0
    for host, parts in cli.PROJECT_DIRS.items():
        for name in cli.SKILLS:
            assert (project.joinpath(*parts) / name / "SKILL.md").is_file(), host


def test_unowned_conflict_and_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "skills"
    existing = root / cli.SKILLS[0]
    existing.mkdir(parents=True)
    (existing / "SKILL.md").write_text("another owner\n", encoding="utf-8")
    assert cli.main(["install", "--dir", str(root)]) == 2
    assert (existing / "SKILL.md").read_text(encoding="utf-8") == "another owner\n"
    assert "ownership manifest" in capsys.readouterr().err

    def missing(_: str) -> None:
        raise ModuleNotFoundError("No module named 'required-package'", name="required-package")

    monkeypatch.setattr(cli.importlib, "import_module", missing)
    assert cli.main(["doctor"]) == 2
    assert "uv tool install --reinstall" in capsys.readouterr().err


def test_manifest_tracks_only_shipped_files(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    assert cli.main(["install", "--dir", str(root)]) == 0
    for name in cli.SKILLS:
        manifest = json.loads((root / name / cli.MANIFEST).read_text(encoding="utf-8"))
        assert manifest["product"] == cli.PRODUCT
        assert set(manifest["files"]) == set(cli._resource_files(name))
        if name in cli.RUNTIME_SKILLS:
            runtime = manifest["runtime_python"]
            installed = (root / name / "SKILL.md").read_text(encoding="utf-8")
            assert "Installed runtime" in installed and runtime in installed
            for module in cli.RUNTIME_MODULES:
                assert f"-m {module}" in installed
                no_bin = os.environ.copy()
                no_bin["PATH"] = ""
                result = subprocess.run([runtime, "-m", module, "--help"], cwd=tmp_path,
                                        env=no_bin, capture_output=True, text=True)
                assert result.returncode == 0, result.stderr
        assert cli.main(["doctor", "--dir", str(root)]) == 0


def test_bundled_markdown_links_resolve_without_author_checkout(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    assert cli.main(["install", "--dir", str(root)]) == 0
    for name in cli.SKILLS:
        for document in (root / name).rglob("*.md"):
            for link in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                target = link.split("#", 1)[0]
                if not target or target.startswith(("https://", "http://", "mailto:")):
                    continue
                assert not Path(target).is_absolute(), (document, link)
                assert (document.parent / target).is_file(), (document, link)


def test_user_scope_honors_host_config_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh-home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    args = cli._parser().parse_args(["install", "--scope", "user", "--host", "dsh", "--host", "opencode"])
    assert cli._targets(args) == [tmp_path / "dsh-home/skills", tmp_path / "xdg-config/opencode/skills"]
