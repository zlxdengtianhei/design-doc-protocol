#!/usr/bin/env python3
"""Meaning-stream helpers for the DDP projection layer.

The meaning stream remains an authority file under ``requirements/meaning``.
This module only scaffolds that authority and checks whether a DDP projection
adopts it by pointer/hash instead of copying prose into a parallel truth source.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

MEANING_ANCHOR_RE = re.compile(r"\b(M\d+(?:\.\d+)?)\b")
COPIED_MEANING_FLAG = "meaning copied instead of pointed"


@dataclass(frozen=True)
class MeaningCheckResult:
    """Result of checking pointer-backed meaning adoption."""

    verdict: str
    issues: tuple[str, ...]
    authority: Path
    source_hash: str
    anchors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file's bytes."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def meaning_authority_path(root: Path, domain: str) -> Path:
    """Return the canonical meaning authority path for ``domain``."""
    return Path(root).expanduser().resolve() / "requirements" / "meaning" / f"{domain}.md"


def scaffold_meaning(root: Path, domain: str, *, overwrite: bool = False) -> Path:
    """Create ``requirements/meaning/<domain>.md`` if needed.

    Existing files are preserved unless ``overwrite=True`` is passed.
    """
    path = meaning_authority_path(root, domain)
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# Meaning - {domain}",
                "",
                "<!--",
                "Add meaning anchors here, for example:",
                "- M1: <meaning claim>",
                "- M1.0: <sub-anchor>",
                "-->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def extract_meaning_anchors(text: str) -> tuple[str, ...]:
    """Extract unique meaning anchors such as ``M1``, ``M1.0``, and ``M2``."""
    seen: set[str] = set()
    anchors: list[str] = []
    for match in MEANING_ANCHOR_RE.finditer(text):
        anchor = match.group(1)
        if anchor not in seen:
            seen.add(anchor)
            anchors.append(anchor)
    return tuple(anchors)


def _read_text(value: str | Path) -> str:
    if isinstance(value, Path):
        return value.read_text(encoding="utf-8")
    return value


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _body_prose_snippets(text: str) -> tuple[str, ...]:
    snippets: list[str] = []
    in_frontmatter = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        if line.startswith("#") or line.startswith("<!--") or line.startswith("-->"):
            continue
        if line.startswith("- authority:") or line.startswith("- source_hash:"):
            continue
        normalized = _normalize(line)
        if len(normalized) >= 20 and re.search(r"[A-Za-z]", normalized):
            snippets.append(normalized)
    return tuple(snippets)


def check_pointer_anchor(
    artifact: str | Path,
    meaning_authority: Path,
) -> MeaningCheckResult:
    """Check that ``artifact`` adopts ``meaning_authority`` by pointer/hash.

    PASS requires pointer evidence (authority path or source hash), all extracted
    anchors to remain visible in the projection, and no copied meaning prose.
    """
    authority = Path(meaning_authority).expanduser().resolve()
    authority_text = authority.read_text(encoding="utf-8")
    artifact_text = _read_text(artifact)
    source_hash = sha256_file(authority)
    anchors = extract_meaning_anchors(authority_text)

    issues: list[str] = []
    path_tokens = {str(authority), authority.as_posix()}
    has_pointer = any(token in artifact_text for token in path_tokens) or source_hash in artifact_text
    if not has_pointer:
        issues.append("meaning pointer evidence absent")

    for anchor in anchors:
        if anchor not in artifact_text:
            issues.append(f"meaning anchor absent: {anchor}")

    normalized_artifact = _normalize(artifact_text)
    copied = [
        snippet
        for snippet in _body_prose_snippets(authority_text)
        if snippet and snippet in normalized_artifact
    ]
    if copied:
        issues.append(COPIED_MEANING_FLAG)

    return MeaningCheckResult(
        verdict="PASS" if not issues else "FLAG",
        issues=tuple(issues),
        authority=authority,
        source_hash=source_hash,
        anchors=anchors,
    )


def format_check_result(result: MeaningCheckResult) -> str:
    """Render a compact deterministic check result."""
    lines = [
        f"verdict: {result.verdict}",
        f"authority: {result.authority}",
        f"source_hash: {result.source_hash}",
        "anchors: " + ", ".join(result.anchors),
    ]
    for issue in result.issues:
        lines.append(f"FLAG: {issue}")
    return "\n".join(lines)

