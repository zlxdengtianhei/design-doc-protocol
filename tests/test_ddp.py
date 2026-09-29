"""Behavioral regression for the standalone incremental DDP path."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ddp import DDPError, apply, prepare, read, status
from ddp import core


class DDPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.design = self.root / "docs/design"
        self.design.mkdir(parents=True)
        (self.design / "requirements.md").write_text("# CSV export\nEmpty export returns [].\n")
        (self.design / "export.md").write_text("# Export\nEmpty export returns [].\n")
        (self.design / "cli.md").write_text("# CLI\nSee export.md. Empty export returns [].\n")
        (self.design / "auth.md").write_text("# Auth\nPasswords remain private.\n")
        self.before_auth = (self.design / "auth.md").read_bytes()

    def packet(self):
        return prepare(self.root, "csv-header", "docs/design/requirements.md", ["export.md", "cli.md"],
                       request_heading="CSV export")

    def plan(self):
        packet = self.packet()
        return {"change_id": "csv-header",
                "request": {k: packet["request"][k] for k in ("path", "sha256", "heading", "section_sha256")},
                "edits": [{"path": t["path"], "expected_sha256": t["sha256"],
                           "old": "Empty export returns [].",
                           "new": "Empty CSV export preserves the column header and has zero data rows."}
                          for t in packet["targets"]],
                "consumers": [
                    {"path": "docs/design/export.md", "decision": "changed", "reason": "authority for export behavior"},
                    {"path": "docs/design/cli.md", "decision": "changed", "reason": "CLI user contract"},
                    {"path": "docs/design/auth.md", "decision": "unchanged", "reason": "authentication has no export dependency"}]}

    def test_incremental_repeat_and_restart(self):
        p = self.plan()
        self.assertIn("docs/design/cli.md", [x["path"] for x in prepare(
            self.root, "csv-header", "docs/design/requirements.md", ["export.md"])["reference_candidates"]])
        first = apply(self.root, p)
        body = (self.design / "export.md").read_bytes()
        log = (self.design / "CHANGELOG.md").read_bytes()
        self.assertEqual(first["written"], 2)
        self.assertEqual(apply(self.root, p)["written"], 0)
        self.assertEqual((self.design / "export.md").read_bytes(), body)
        self.assertEqual((self.design / "CHANGELOG.md").read_bytes(), log)
        self.assertEqual(log.count(b"```ddp-change"), 1)
        self.assertEqual((self.design / "auth.md").read_bytes(), self.before_auth)
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_current")
        self.assertEqual(status(self.root, "csv-header")["semantic_status"], "unknown")

    def test_interrupted_after_first_document_recovers(self):
        p = self.plan()
        with self.assertRaisesRegex(DDPError, "injected interruption"):
            apply(self.root, p, fail_after=1)
        self.assertFalse((self.design / "CHANGELOG.md").exists())
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "incomplete_retryable")
        self.assertEqual({Path(x["path"]).name: x["state"] for x in status(self.root, "csv-header")["recovery"]["files"]},
                         {"export.md": "done", "cli.md": "pending"})
        result = apply(self.root, p)
        self.assertEqual(result["written"], 1)
        self.assertEqual((self.design / "CHANGELOG.md").read_bytes().count(b"```ddp-change"), 1)

    def test_interrupted_before_record_recovers(self):
        p = self.plan()
        real_atomic = core._atomic
        def fail_log(path, data):
            if path.name == "CHANGELOG.md":
                raise OSError("simulated crash before record")
            return real_atomic(path, data)
        with patch.object(core, "_atomic", side_effect=fail_log):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                apply(self.root, p)
        self.assertEqual(apply(self.root, p)["written"], 0)
        self.assertEqual((self.design / "CHANGELOG.md").read_bytes().count(b"```ddp-change"), 1)

    def test_stale_source_and_target_are_rejected(self):
        p = self.plan()
        (self.design / "requirements.md").write_text("# CSV export\nEmpty export retains headers.\n")
        with self.assertRaisesRegex(DDPError, "stale request"):
            apply(self.root, p)
        self.assertFalse((self.design / "CHANGELOG.md").exists())
        self.assertNotEqual(self.packet()["request"]["sha256"], p["request"]["sha256"])
        p = self.plan()
        (self.design / "cli.md").write_text("Third party edit.\n")
        with self.assertRaisesRegex(DDPError, "stale target"):
            apply(self.root, p)
        self.assertIn("returns []", (self.design / "export.md").read_text())

    def test_unrelated_requirement_section_does_not_stale_plan(self):
        p = self.plan()
        with (self.design / "requirements.md").open("a") as handle:
            handle.write("\n# Authentication\nTokens protect login.\n")
        self.assertEqual(apply(self.root, p)["written"], 2)
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_current")
        (self.design / "requirements.md").write_text("# CSV export\nEmpty exports now keep headers.\n# Authentication\nTokens protect login.\n")
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_stale")

    def test_prevalidation_and_unsafe_paths(self):
        p = self.plan()
        p["edits"][1]["old"] = "Empty"
        (self.design / "cli.md").write_text("Empty and Empty\n")
        p["edits"][1]["expected_sha256"] = core.sha((self.design / "cli.md").read_bytes())
        with self.assertRaisesRegex(DDPError, "matches 2"):
            apply(self.root, p)
        self.assertIn("returns []", (self.design / "export.md").read_text())
        p = self.plan()
        p["edits"][0]["path"] = "../outside.md"
        with self.assertRaises(DDPError):
            apply(self.root, p)
        p = self.plan()
        p["consumers"][2]["path"] = "../outside.md"
        with self.assertRaises(DDPError):
            apply(self.root, p)
        (self.design / "escape.md").symlink_to(self.root / "outside.md")
        p = self.plan()
        p["edits"][0]["path"] = "escape.md"
        with self.assertRaises(DDPError):
            apply(self.root, p)
        p = self.plan()
        (self.design / "requirements.md").unlink()
        with self.assertRaisesRegex(DDPError, "file missing"):
            apply(self.root, p)
        self.assertFalse((self.design / "CHANGELOG.md").exists())

    def test_read_cbe_explicit_version_and_cli_from_external_cwd(self):
        code = self.root / "docs/codebase"
        code.mkdir()
        (code / "module.md").write_text("# Module\nSelected behavior.\n")
        version = core.sha((code / "module.md").read_bytes())
        self.assertEqual(read(self.root, "module.md", version, code_docs=code)["content"], "# Module\nSelected behavior.\n")
        self.assertEqual(read(self.root, "module.md", version, code_docs="docs/codebase")["content"], "# Module\nSelected behavior.\n")
        (code / "module.md").write_text("# Module\nChanged.\n")
        with self.assertRaisesRegex(DDPError, "stale read"):
            read(self.root, "module.md", version, code_docs=code)
        command = [sys.executable, "-m", "ddp", "prepare", "--project-root", str(self.root),
                   "--change", "csv-header", "--request", "docs/design/requirements.md",
                   "--target", "export.md"]
        import os
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        run = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["targets"][0]["path"], "docs/design/export.md")
        bad = subprocess.run([sys.executable, "-m", "ddp", "apply", "--project-root", str(self.root),
                              "--plan", "-"], cwd=self.root, env=env, input="{", capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("invalid plan JSON", bad.stderr)

    def test_explicit_relative_roots_are_project_relative(self):
        p = self.plan()
        self.assertEqual(apply(self.root, p, design_root="docs/design", state_dir=".design-doc-protocol")["written"], 2)
        self.assertEqual(status(self.root, "csv-header", design_root="docs/design")["mechanical_state"], "recorded_current")

    def test_prefix_and_hyphenated_change_ids_remain_independent(self):
        original = self.plan()
        first = {**original, "change_id": "retry-503",
                 "edits": [original["edits"][0]],
                 "consumers": [original["consumers"][0]]}
        second = {**original, "change_id": "retry",
                  "edits": [original["edits"][1]],
                  "consumers": [original["consumers"][1]]}
        self.assertEqual(apply(self.root, first)["written"], 1)
        self.assertEqual(status(self.root, "retry")["mechanical_state"], "unrecorded")
        self.assertEqual(status(self.root, "retry")["journals"], [])
        self.assertEqual(apply(self.root, second)["written"], 1)
        self.assertEqual(apply(self.root, first)["written"], 0)
        self.assertEqual(apply(self.root, second)["written"], 0)
        self.assertEqual(status(self.root, "retry-503")["mechanical_state"], "recorded_current")
        self.assertEqual(status(self.root, "retry")["mechanical_state"], "recorded_current")
        self.assertEqual(len(status(self.root, "retry")["journals"]), 1)
        self.assertIn("/retry-", status(self.root, "retry")["journals"][0])
        self.assertEqual((self.design / "CHANGELOG.md").read_bytes().count(b"```ddp-change"), 2)

    def test_same_id_different_operation_and_journal_identity_rejected(self):
        p = self.plan()
        apply(self.root, p)
        changed = {**p, "edits": [{**p["edits"][0], "new": "A different value."}, p["edits"][1]]}
        with self.assertRaisesRegex(DDPError, "another incomplete or completed operation"):
            apply(self.root, changed)
        journal_path = next((self.root / ".design-doc-protocol/operations").glob("*.json"))
        journal = json.loads(journal_path.read_text())
        journal["change_id"] = "other-id"
        journal_path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(DDPError, "journal identity"):
            apply(self.root, p)
        with self.assertRaisesRegex(DDPError, "journal identity"):
            status(self.root, "csv-header")

    def test_legacy_journal_with_exact_filename_can_resume(self):
        p = self.plan()
        with self.assertRaisesRegex(DDPError, "injected interruption"):
            apply(self.root, p, fail_after=1)
        journal_path = next((self.root / ".design-doc-protocol/operations").glob("*.json"))
        journal = json.loads(journal_path.read_text())
        del journal["change_id"]  # State written by the previous package version.
        journal_path.write_text(json.dumps(journal))
        self.assertEqual(apply(self.root, p)["written"], 1)
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_current")

    def test_fenced_markdown_heading_does_not_hide_related_requirement(self):
        request = self.design / "requirements.md"
        for fence in ("```sh", "~~~sh"):
            with self.subTest(fence=fence):
                closer = fence[0] * 3
                request.write_text("# CSV export\nExample:\n" + fence +
                                   "\n# shell comment\n# CSV export\n" + fence[0] * 2 +
                                   "\nStill code.\n" + closer +
                                   "\nEmpty export returns [].\n# Auth\nUnrelated.\n")
                packet = self.packet()
                self.assertIn("Empty export returns [].", packet["request"]["content"])
                self.assertIn("# shell comment", packet["request"]["content"])
                plan = self.plan()
                request.write_text(request.read_text().replace("Unrelated.", "Changed unrelated."))
                self.assertEqual(apply(self.root, plan)["written"], 2)
                self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_current")
                request.write_text(request.read_text().replace("Empty export returns [].", "Empty export retains headers."))
                self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_stale")
                with self.assertRaisesRegex(DDPError, "stale request"):
                    apply(self.root, plan)
                # Restore authority and operation state for the second fence variant.
                (self.design / "export.md").write_text("# Export\nEmpty export returns [].\n")
                (self.design / "cli.md").write_text("# CLI\nSee export.md. Empty export returns [].\n")
                (self.design / "CHANGELOG.md").unlink()
                for journal in (self.root / ".design-doc-protocol/operations").iterdir():
                    journal.unlink()

    def test_fence_to_eof_and_duplicate_real_heading(self):
        request = self.design / "requirements.md"
        request.write_text("# CSV export\n~~~text\n# Auth\nStill code.\n")
        excerpt = self.packet()["request"]["content"]
        self.assertIn("Still code.", excerpt)
        request.write_text("# CSV export\nFirst.\n# Auth\nOther.\n# CSV export\nSecond.\n")
        with self.assertRaisesRegex(DDPError, "2 matches"):
            self.packet()

    def test_html_comment_and_container_headings_do_not_hide_requirement(self):
        request = self.design / "requirements.md"
        request.write_text("# CSV export\n<!--\n# shell notes\n-->\n"
                           "> # Quoted heading\n- # List heading\n"
                           "Empty export returns [].\n# Auth\nUnrelated.\n")
        packet = self.packet()
        self.assertIn("Empty export returns [].", packet["request"]["content"])
        self.assertIn("# shell notes", packet["request"]["content"])
        with self.assertRaisesRegex(DDPError, "whole file"):
            prepare(self.root, "nested", "docs/design/requirements.md", ["export.md"],
                    request_heading="Quoted heading")
        plan = self.plan()
        request.write_text(request.read_text().replace("Unrelated.", "Changed auth."))
        self.assertEqual(apply(self.root, plan)["written"], 2)
        request.write_text(request.read_text().replace("Empty export returns [].", "Empty export keeps headers."))
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_stale")
        with self.assertRaisesRegex(DDPError, "stale request"):
            apply(self.root, plan)

    def test_setext_crlf_and_unicode_separator_keep_source_map(self):
        request = self.design / "requirements.md"
        request.write_bytes(("# CSV export\r\nA line with unicode separator.\r\n"
                             "Empty export returns [].\r\n\r\nBilling\r\n=======\r\nUnrelated.\r\n").encode("utf-8"))
        packet = self.packet()
        self.assertIn("Empty export returns [].", packet["request"]["content"])
        self.assertNotIn("Unrelated.", packet["request"]["content"])
        plan = self.plan()
        request.write_bytes(request.read_bytes().replace(b"Unrelated.", b"New billing."))
        self.assertEqual(apply(self.root, plan)["written"], 2)
        request.write_bytes(request.read_bytes().replace(b"Empty export returns [].", b"Empty export keeps headers."))
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_stale")

    def test_explicit_code_source_binding_and_staleness(self):
        code = self.root / "knowledge/generated"
        code.mkdir(parents=True)
        page = code / "module.md"
        page.write_text("# Export API\nReturns CSV.\n# Other\nUnrelated.\n")
        pinned = read(self.root, "module.md", core.sha(page.read_bytes()),
                      heading="Export API", code_docs="knowledge/generated")
        plan = self.plan()
        plan["code_sources"] = [pinned]  # Direct read output is accepted; content is not persisted.
        page.write_text(page.read_text().replace("Unrelated.", "Other detail."))
        self.assertEqual(apply(self.root, plan)["written"], 2)
        state = status(self.root, "csv-header")
        self.assertEqual(state["mechanical_state"], "recorded_current")
        self.assertEqual(state["code_sources"][0]["dependency_current"], True)
        record = json.loads((self.design / "CHANGELOG.md").read_text().split("```ddp-change\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual(record["code_sources"][0]["path"], "knowledge/generated/module.md")
        self.assertNotIn("content", record["code_sources"][0])
        journal = json.loads(next((self.root / ".design-doc-protocol/operations").iterdir()).read_text())
        self.assertEqual(journal["code_sources"], record["code_sources"])
        page.write_text(page.read_text().replace("Returns CSV.", "Returns JSON."))
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "recorded_stale")
        with self.assertRaisesRegex(DDPError, "stale code source"):
            apply(self.root, plan)

    def test_code_source_change_blocks_new_apply_and_partial_recovery(self):
        code = self.root / "alternate/code-docs"
        code.mkdir(parents=True)
        page = code / "module.md"
        page.write_text("# Export\nCode currently returns [].\n")
        pinned = read(self.root, "module.md", core.sha(page.read_bytes()), code_docs="alternate/code-docs")
        plan = self.plan()
        plan["code_sources"] = [{"path": pinned["path"], "sha256": pinned["sha256"]}]
        page.write_text("# Export\nCode now returns headers.\n")
        with self.assertRaisesRegex(DDPError, "stale code source"):
            apply(self.root, plan)
        self.assertIn("returns []", (self.design / "export.md").read_text())
        self.assertFalse((self.design / "CHANGELOG.md").exists())
        page.write_text("# Export\nCode currently returns [].\n")
        with self.assertRaisesRegex(DDPError, "injected interruption"):
            apply(self.root, plan, fail_after=1)
        page.unlink()
        self.assertEqual(status(self.root, "csv-header")["mechanical_state"], "incomplete_conflict")
        with self.assertRaisesRegex(DDPError, "code source"):
            apply(self.root, plan)
        self.assertIn("returns []", (self.design / "cli.md").read_text())

    def test_cli_binds_selected_code_page_from_custom_root(self):
        code = self.root / "generated/reference"
        code.mkdir(parents=True)
        page = code / "export.md"
        page.write_text("# Export API\nThe code returns an empty array.\n")
        import os
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        def cli(*args, input_text=None):
            return subprocess.run([sys.executable, "-m", "ddp", *args], cwd=self.root,
                                  env=env, input=input_text, capture_output=True, text=True)
        pinned = cli("read", "--project-root", str(self.root), "--code-docs", "generated/reference",
                     "--path", "export.md", "--expected-sha256", core.sha(page.read_bytes()))
        self.assertEqual(pinned.returncode, 0, pinned.stderr)
        code_source = json.loads(pinned.stdout)
        plan = self.plan()
        plan["code_sources"] = [code_source]
        applied = cli("apply", "--project-root", str(self.root), "--plan", "-", input_text=json.dumps(plan))
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["written"], 2)
        page.write_text("# Export API\nThe code returns a header.\n")
        checked = cli("status", "--project-root", str(self.root), "--change", "csv-header")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["mechanical_state"], "recorded_stale")

    def test_legacy_plan_digest_and_code_source_symlink_stale(self):
        old_plan = self.plan()
        expected = core.sha(core.canonical({key: old_plan[key] for key in ("change_id", "request", "edits", "consumers")}))
        self.assertEqual(apply(self.root, old_plan)["operation"], expected)
        self.assertNotIn("code_sources", status(self.root, "csv-header")["record"])
        code = self.root / "generated"
        code.mkdir()
        page = code / "page.md"
        page.write_text("# API\nOriginal.\n")
        pinned = read(self.root, "page.md", core.sha(page.read_bytes()), code_docs="generated")
        p = self.plan()
        p["change_id"] = "with-code"
        p["code_sources"] = [pinned]
        # The previous operation changed targets; prepare a new target version.
        p["edits"][0]["expected_sha256"] = core.sha((self.design / "export.md").read_bytes())
        p["edits"][0]["old"] = "Empty CSV export preserves the column header and has zero data rows."
        p["edits"][0]["new"] = "Updated export policy."
        p["edits"][1]["expected_sha256"] = core.sha((self.design / "cli.md").read_bytes())
        p["edits"][1]["old"] = "Empty CSV export preserves the column header and has zero data rows."
        p["edits"][1]["new"] = "Updated export policy."
        apply(self.root, p)
        page.unlink()
        page.symlink_to(self.root / "outside.md")
        self.assertEqual(status(self.root, "with-code")["mechanical_state"], "recorded_stale")

    def test_invalid_code_source_paths_do_not_write(self):
        plan = self.plan()
        plan["code_sources"] = [{"path": "../outside.md", "sha256": "0" * 64}]
        with self.assertRaises(DDPError):
            apply(self.root, plan)
        plan["code_sources"] = [{"path": str(self.root / "absolute.md"), "sha256": "0" * 64}]
        with self.assertRaisesRegex(DDPError, "project-relative"):
            apply(self.root, plan)
        self.assertIn("returns []", (self.design / "export.md").read_text())

    def test_false_section_hash_is_rejected_even_at_same_file_version(self):
        plan = self.plan()
        plan["request"]["section_sha256"] = "0" * 64
        with self.assertRaisesRegex(DDPError, "stale request"):
            apply(self.root, plan)
        self.assertFalse((self.design / "CHANGELOG.md").exists())


if __name__ == "__main__":
    unittest.main()
