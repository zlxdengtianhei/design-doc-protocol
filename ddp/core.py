"""Version-bound, single-writer updates to authoritative design files.

The source request and target documents are the authority. The state directory
holds only recovery material; it is never a second design document store.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt


class DDPError(Exception):
    """An actionable input, version, or recovery failure."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _root(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise DDPError(f"root is not a directory: {p}")
    return p


def _configured(project: Path, value: str | Path | None, default: str, *, must_exist: bool) -> Path:
    raw = Path(value) if value is not None else Path(default)
    path = (raw if raw.is_absolute() else project / raw).resolve()
    if not path.is_relative_to(project):
        raise DDPError(f"configured path escapes project root: {raw}")
    if must_exist and not path.is_dir():
        raise DDPError(f"configured directory missing: {path}")
    return path


def _inside(root: Path, value: str | Path, *, existing: bool = True) -> Path:
    """Reject traversal and symlink escapes, including a symlink final target."""
    raw = Path(value)
    if raw.is_absolute():
        candidate = raw
    else:
        if not raw.parts or ".." in raw.parts:
            raise DDPError(f"invalid relative path: {value}")
        candidate = root / raw
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise DDPError(f"path escapes allowed root {root}: {value}")
    if candidate.is_symlink():
        raise DDPError(f"symlink file paths are not supported: {candidate}")
    if existing and not candidate.is_file():
        raise DDPError(f"file missing: {candidate}; restore it or prepare a new version")
    if not existing and candidate.exists() and not candidate.is_file():
        raise DDPError(f"target is not a regular file: {candidate}")
    return candidate


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise DDPError(f"cannot read {path}: {exc}") from exc


def _text(data: bytes, path: Path) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DDPError(f"not UTF-8: {path}") from exc


def _section(text: str, heading: str | None) -> str:
    if not heading:
        return text
    if "\x00" in text:
        raise DDPError("NUL in Markdown source; omit heading to bind the whole file")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")  # markdown-it source maps count only normalized newlines.
    try:
        tokens = MarkdownIt("commonmark").parse(normalized)
    except Exception as exc:
        raise DDPError(f"cannot select Markdown heading: {exc}; omit heading to bind the whole file") from exc
    headings: list[tuple[int, int, str]] = []
    nested = set()
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        if not token.map or not re.fullmatch(r"h[1-6]", token.tag) or index + 1 >= len(tokens) or tokens[index + 1].type != "inline":
            raise DDPError("unmapped Markdown heading; omit heading to bind the whole file")
        start = token.map[0]
        if not isinstance(start, int) or not 0 <= start < len(lines):
            raise DDPError("invalid Markdown source map; omit heading to bind the whole file")
        title = tokens[index + 1].content.strip()
        if token.level == 0:
            headings.append((start, int(token.tag[1]), title))
        else:
            nested.add(title)
    found = [(index, level) for index, level, title in headings if title == heading]
    if len(found) != 1:
        detail = "inside a container" if not found and heading in nested else f"{len(found)} matches"
        raise DDPError(f"heading {heading!r} has {detail}; choose one unique top-level heading or omit heading to bind the whole file")
    start, level = found[0]
    end = next((index for index, depth, _title in headings if index > start and depth <= level), len(lines))
    return "\n".join(lines[start:end]).rstrip("\n") + "\n"


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _source_current(path: Path, source: dict[str, str]) -> tuple[bool, str]:
    data = _read(path)
    actual = sha(data)
    if source.get("heading") and source.get("section_sha256"):
        try:
            section = _section(_text(data, path), source["heading"])
        except DDPError:
            return False, actual
        return sha(section.encode("utf-8")) == source["section_sha256"], actual
    return actual == source["sha256"], actual


def _design_path(project: Path, design: Path, value: str, *, existing: bool = True) -> Path:
    """Plan paths are project-relative; --target paths are design-root-relative."""
    raw = Path(value)
    if raw.is_absolute():
        return _inside(design, raw, existing=existing)
    prefix = design.relative_to(project).parts
    if raw.parts[:len(prefix)] == prefix:
        return _inside(design, project / raw, existing=existing)
    return _inside(design, raw, existing=existing)


def read(project_root: str | Path, path: str, expected_sha256: str, *, heading: str | None = None,
         code_docs: str | Path | None = None) -> dict[str, Any]:
    project = _root(project_root)
    allowed = _configured(project, code_docs, "docs/codebase", must_exist=True) if code_docs else project
    target = _inside(allowed, path)
    data = _read(target)
    actual = sha(data)
    if actual != expected_sha256:
        raise DDPError(f"stale read {target}: expected {expected_sha256}, actual {actual}; obtain an explicit new version")
    content = _section(_text(data, target), heading)
    return {"path": _relative(project, target), "sha256": actual,
            "heading": heading, "section_sha256": sha(content.encode("utf-8")) if heading else None,
            "content": content}


def prepare(project_root: str | Path, change_id: str, request: str, targets: list[str], *,
            request_heading: str | None = None, design_root: str | Path | None = None,
            state_dir: str | Path | None = None, code_docs: str | Path | None = None,
            target_headings: list[str] | None = None) -> dict[str, Any]:
    project = _root(project_root)
    design = _configured(project, design_root, "docs/design", must_exist=True)
    source = _inside(project, request)
    request_bytes = _read(source)
    request_excerpt = _section(_text(request_bytes, source), request_heading)
    if not change_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", change_id):
        raise DDPError("change id must be 1-100 letters, digits, dot, underscore or hyphen")
    if not targets:
        raise DDPError("choose at least one authority target")
    if target_headings and len(target_headings) != len(targets):
        raise DDPError("--target-heading must be supplied once per --target")
    selected = []
    for index, value in enumerate(targets):
        target = _inside(design, value)
        data = _read(target)
        heading = target_headings[index] if target_headings else None
        selected.append({"path": _relative(project, target), "sha256": sha(data),
                         "heading": heading, "content": _section(_text(data, target), heading)})
    refs = set()
    for target in selected:
        refs.add(Path(target["path"]).name)
        refs.add(target["path"])
    candidates = []
    for path in sorted(design.rglob("*.md")):
        if path.is_symlink() or not path.resolve().is_relative_to(design) or _relative(project, path) in {t["path"] for t in selected}:
            continue
        content = _text(_read(path), path)
        matched = sorted(ref for ref in refs if ref in content)
        if matched:
            candidates.append({"path": _relative(project, path), "matches": matched, "sha256": sha(content.encode("utf-8"))})
    code = None
    if code_docs:
        code = _configured(project, code_docs, "docs/codebase", must_exist=True)
    return {"change_id": change_id, "request": {"path": _relative(project, source),
            "sha256": sha(request_bytes), "heading": request_heading,
            "section_sha256": sha(request_excerpt.encode("utf-8")) if request_heading else None,
            "content": request_excerpt},
            "targets": selected, "reference_candidates": candidates,
            "code_docs": _relative(project, code) if code else None,
            "state_dir": str(_configured(project, state_dir, ".design-doc-protocol", must_exist=False)),
            "note": "Candidates are a search aid, not a complete semantic impact list. Declare every consumer changed or unchanged with a reason."}


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".ddp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temp, path.stat().st_mode & 0o777)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _load_plan(plan: dict[str, Any]) -> tuple[str, dict[str, str], list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
    if not isinstance(plan, dict):
        raise DDPError("plan must be a JSON object")
    change = plan.get("change_id")
    if not isinstance(change, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", change):
        raise DDPError("invalid change_id")
    source = plan.get("request")
    if not isinstance(source, dict) or not isinstance(source.get("path"), str) or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", ""))):
        raise DDPError("request requires path and sha256 from prepare")
    if source.get("heading") is not None:
        if not isinstance(source["heading"], str) or not source["heading"] or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("section_sha256", ""))):
            raise DDPError("heading-bound request needs heading and section_sha256 from prepare")
    edits = plan.get("edits")
    if not isinstance(edits, list) or not edits:
        raise DDPError("edits must be a nonempty list")
    consumers = plan.get("consumers")
    if not isinstance(consumers, list) or not consumers:
        raise DDPError("consumers must list decisions with reasons")
    for item in consumers:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("path", "decision", "reason")) or item["decision"] not in {"changed", "unchanged"}:
            raise DDPError("each consumer needs path, decision changed/unchanged, and reason")
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("path"), str) or not isinstance(edit.get("old"), str) or not isinstance(edit.get("new"), str):
            raise DDPError("each edit needs path, old and new strings")
        if edit["old"] == edit["new"] or not edit["old"]:
            raise DDPError("each edit must replace one nonempty old string with different new text")
        if not re.fullmatch(r"[0-9a-f]{64}", str(edit.get("expected_sha256", ""))):
            raise DDPError("each edit needs expected_sha256 from prepare")
    code_sources = plan.get("code_sources", [])
    if not isinstance(code_sources, list):
        raise DDPError("code_sources must be a list of explicitly consumed pages")
    for item in code_sources:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            raise DDPError("each code source needs the path and sha256 returned by read")
        if item.get("heading") is not None and (not isinstance(item["heading"], str) or not item["heading"] or
                                                not re.fullmatch(r"[0-9a-f]{64}", str(item.get("section_sha256", "")))):
            raise DDPError("heading-bound code source needs heading and section_sha256 returned by read")
    return change, source, edits, consumers, code_sources


def _normalize_code_sources(project: Path, sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized = []
    seen = set()
    for item in sources:
        if Path(item["path"]).is_absolute():
            raise DDPError(f"code source path must be project-relative: {item['path']}")
        path = _inside(project, item["path"], existing=False)
        name = _relative(project, path)
        if name in seen:
            raise DDPError(f"duplicate code source: {name}")
        seen.add(name)
        version = {"path": name, "sha256": item["sha256"]}
        if item.get("heading") is not None:
            version.update({"heading": item["heading"], "section_sha256": item["section_sha256"]})
        normalized.append(version)
    return normalized


def _code_source_facts(project: Path, sources: list[dict[str, str]]) -> list[dict[str, Any]]:
    facts = []
    for item in sources:
        try:
            path = _inside(project, item["path"], existing=False)
            current, actual = _source_current(path, item) if path.is_file() else (False, None)
        except DDPError:
            current, actual = False, None
        facts.append({"path": item["path"], "expected_sha256": item["sha256"],
                      "current_sha256": actual, "dependency_current": current})
    return facts


def _record(change: str, digest: str, source: dict[str, str], changed: list[dict[str, str]], consumers: list[dict[str, str]], code_sources: list[dict[str, str]]) -> bytes:
    obj = {"change_id": change, "operation": digest, "request": source,
           "changed": changed, "consumers": consumers}
    if code_sources:
        obj["code_sources"] = code_sources
    return ("\n```ddp-change\n" + json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n").encode("utf-8")


def _find_record(log: bytes, change: str) -> dict[str, Any] | None:
    found = []
    for m in re.finditer(rb"(?:^|\n)```ddp-change\n(.*?)\n```", log, re.S):
        try:
            data = json.loads(m.group(1))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DDPError(f"malformed ddp-change record: {exc}") from exc
        if data.get("change_id") == change:
            found.append(data)
    if len(found) > 1:
        raise DDPError(f"CHANGELOG contains duplicate records for {change}")
    return found[0] if found else None


def _operations_dir(project: Path, state: Path) -> Path:
    directory = state / "operations"
    if not directory.resolve().is_relative_to(project):
        raise DDPError(f"recovery directory escapes project root: {directory}")
    return directory


def _exact_journals(project: Path, state: Path, change: str) -> list[Path]:
    """The change ID is a complete filename field, even when it has hyphens."""
    directory = _operations_dir(project, state)
    if not directory.is_dir():
        return []
    pattern = re.compile(rf"{re.escape(change)}-([0-9a-f]{{64}})\.json\Z")
    return sorted(path for path in directory.iterdir() if pattern.fullmatch(path.name))


def _load_journal(path: Path, change: str) -> dict[str, Any]:
    if path.is_symlink():
        raise DDPError(f"journal identity is unsafe symlink: {path}")
    match = re.fullmatch(rf"{re.escape(change)}-([0-9a-f]{{64}})\.json", path.name)
    if not match:
        raise DDPError(f"journal identity does not match change {change}: {path}")
    try:
        journal = json.loads(_read(path))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DDPError(f"invalid recovery journal {path}: {exc}") from exc
    if not isinstance(journal, dict) or journal.get("digest") != match.group(1) or journal.get("change_id", change) != change:
        raise DDPError(f"journal identity does not match change {change}: {path}")
    # Pre-identity journals are accepted only by exact filename plus digest.
    return journal


def apply(project_root: str | Path, plan: dict[str, Any], *, design_root: str | Path | None = None,
          state_dir: str | Path | None = None, fail_after: int | None = None) -> dict[str, Any]:
    """Apply a whole prevalidated batch; recover by passing the identical plan again.

    fail_after is a test-only fault injection point after N document replacements.
    """
    project = _root(project_root)
    design = _configured(project, design_root, "docs/design", must_exist=True)
    state = _configured(project, state_dir, ".design-doc-protocol", must_exist=False)
    change, source, edits, consumers, raw_code_sources = _load_plan(plan)
    source_path = _inside(project, source["path"])
    source_ok, source_actual = _source_current(source_path, source)
    if not source_ok:
        raise DDPError(f"stale request {source_path}: expected version {source['sha256']}, actual {source_actual}; run prepare again")
    code_sources = _normalize_code_sources(project, raw_code_sources)
    for fact in _code_source_facts(project, code_sources):
        if not fact["dependency_current"]:
            raise DDPError(f"stale code source {fact['path']}: expected {fact['expected_sha256']}, actual {fact['current_sha256']}; read its explicit new version")
    digest_input = {"change_id": change, "request": source, "edits": edits, "consumers": consumers}
    if code_sources:
        digest_input["code_sources"] = code_sources
    digest = sha(canonical(digest_input))
    operation_path = _operations_dir(project, state) / f"{change}-{digest}.json"
    journals = _exact_journals(project, state, change)
    for path in journals:
        _load_journal(path, change)
    other_operations = [path for path in journals if path != operation_path]
    if other_operations:
        raise DDPError(f"change {change} has another incomplete or completed operation; inspect status before a new plan")
    log_path = _inside(design, "CHANGELOG.md", existing=False)
    paths = []
    seen = set()
    for edit in edits:
        path = _design_path(project, design, edit["path"], existing=False)
        key = path.resolve()
        if key in seen or key in {log_path.resolve(), source_path.resolve()}:
            raise DDPError(f"duplicate, source, or CHANGELOG edit path: {edit['path']}")
        seen.add(key)
        if not path.is_file():
            raise DDPError(f"target missing: {path}; create it explicitly before preparing a new version")
        prior = _read(path)
        old_hash = edit["expected_sha256"]
        if sha(prior) == old_hash:
            content = _text(prior, path)
            count = content.count(edit["old"])
            if count != 1:
                raise DDPError(f"replacement in {path} matches {count} times; needs exactly one; no files written")
            updated = content.replace(edit["old"], edit["new"], 1).encode("utf-8")
        else:
            # Derive the post-image from the journal if this operation started before.
            if not operation_path.is_file():
                raise DDPError(f"stale target {path}: expected {old_hash}, actual {sha(prior)}; run prepare again")
            journal = _load_journal(operation_path, change)
            expected_post = journal.get("post", {}).get(_relative(project, path))
            if sha(prior) != expected_post:
                raise DDPError(f"stale target {path}: changed outside this operation; inspect and prepare again")
            updated = prior
        paths.append((path, prior, updated, old_hash))
    edited_names = {_relative(project, p) for p, *_ in paths}
    normalized_consumers = []
    decisions = {}
    for item in consumers:
        consumer_path = _design_path(project, design, item["path"])
        name = _relative(project, consumer_path)
        if name in decisions:
            raise DDPError(f"duplicate consumer: {name}")
        decisions[name] = item["decision"]
        normalized_consumers.append({**item, "path": name})
    if any(decisions.get(name) != "changed" for name in edited_names):
        raise DDPError("every edited path needs a changed consumer decision")
    if any(name not in edited_names for name, decision in decisions.items() if decision == "changed"):
        raise DDPError("a changed consumer needs a corresponding edit")
    log_before = _read(log_path) if log_path.is_file() else b"# Design changes\n"
    prior_record = _find_record(log_before, change)
    if prior_record and prior_record.get("operation") != digest:
        raise DDPError(f"change {change} already has a different operation; choose a new change id")
    changed = [{"path": _relative(project, p), "before": before, "after": sha(updated)} for p, _prior, updated, before in paths]
    if prior_record and any(sha(_read(p)) != sha(updated) for p, _prior, updated, _before in paths):
        raise DDPError("CHANGELOG claims completion but target differs; inspect before retry")
    if operation_path.is_file():
        journal = _load_journal(operation_path, change)
        if (journal.get("digest") != digest or
                journal.get("post") != {x["path"]: x["after"] for x in changed} or
                journal.get("before") != {x["path"]: x["before"] for x in changed} or
                journal.get("request") != source or
                journal.get("code_sources", []) != code_sources):
            raise DDPError("recovery journal conflicts with plan; inspect before retry")
    else:
        operation_path.parent.mkdir(parents=True, exist_ok=True)
        journal = {"change_id": change, "digest": digest, "request": source,
              "before": {x["path"]: x["before"] for x in changed},
              "post": {x["path"]: x["after"] for x in changed}}
        if code_sources:
            journal["code_sources"] = code_sources
        _atomic(operation_path, canonical(journal))
    written = 0
    for path, prior, updated, _before in paths:
        if prior != updated:
            _atomic(path, updated)
            written += 1
            if fail_after is not None and written == fail_after:
                raise DDPError(f"injected interruption after {written} document replacement(s); retry identical plan")
    if not prior_record:
        _atomic(log_path, log_before + _record(change, digest, source, changed, normalized_consumers, code_sources))
    return {"change_id": change, "operation": digest, "status": "recovered_or_applied" if written else "no_op",
            "written": written, "changelog": _relative(project, log_path), "changed": changed}


def status(project_root: str | Path, change_id: str, *, design_root: str | Path | None = None,
           state_dir: str | Path | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", change_id):
        raise DDPError("invalid change id")
    project = _root(project_root)
    design = _configured(project, design_root, "docs/design", must_exist=True)
    state = _configured(project, state_dir, ".design-doc-protocol", must_exist=False)
    log = _inside(design, "CHANGELOG.md", existing=False)
    record = _find_record(_read(log), change_id) if log.is_file() else None
    journals = _exact_journals(project, state, change_id)
    for path in journals:
        _load_journal(path, change_id)
    facts = []
    recovery = None
    recorded_source = None
    code_facts = []
    if record:
        source = record["request"]
        source_path = _inside(project, source["path"], existing=False)
        source_ok, actual = _source_current(source_path, source) if source_path.is_file() else (False, None)
        recorded_source = {"path": source["path"], "expected_sha256": source["sha256"],
                           "current_sha256": actual, "dependency_current": source_ok}
        code_facts = _code_source_facts(project, record.get("code_sources", []))
        for item in record["changed"]:
            path = _design_path(project, design, item["path"], existing=False)
            facts.append({"path": item["path"], "current_sha256": sha(_read(path)) if path.is_file() else None,
                          "recorded_sha256": item["after"]})
    elif len(journals) == 1:
        journal = _load_journal(journals[0], change_id)
        code_facts = _code_source_facts(project, journal.get("code_sources", []))
        source = journal["request"]
        source_path = _inside(project, source["path"], existing=False)
        source_ok, source_current = _source_current(source_path, source) if source_path.is_file() else (False, None)
        recovery_files = []
        for name, after in journal["post"].items():
            path = _design_path(project, design, name, existing=False)
            actual = sha(_read(path)) if path.is_file() else None
            recovery_files.append({"path": name, "state": "done" if actual == after else
                                   "pending" if actual == journal["before"].get(name) else "conflict",
                                   "current_sha256": actual})
        recovery = {"source_current": source_current, "source_expected": source["sha256"],
                    "files": recovery_files, "retry_identical_plan": source_ok
                    and all(x["state"] != "conflict" for x in recovery_files)
                    and all(x["dependency_current"] for x in code_facts)}
    mechanical = ("recorded_current" if record and recorded_source["dependency_current"] and
                  all(x["current_sha256"] == x["recorded_sha256"] for x in facts) and
                  all(x["dependency_current"] for x in code_facts)
                  else "recorded_stale" if record else
                  "incomplete_retryable" if recovery and recovery["retry_identical_plan"] else
                  "incomplete_conflict" if recovery else "unrecorded")
    return {"change_id": change_id, "recorded": bool(record), "record": record,
            "recorded_source": recorded_source,
            "journals": [_relative(project, p) for p in journals], "files": facts,
            "code_sources": code_facts, "recovery": recovery,
            "mechanical_state": mechanical,
            "semantic_status": "unknown"}
