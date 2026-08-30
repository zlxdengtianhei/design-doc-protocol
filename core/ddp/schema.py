#!/usr/bin/env python3
"""Typed models for the Design Doc Protocol (DDP) additive composition layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

StreamName = Literal["requirements", "meaning", "design"]
ReqClass = Literal["design", "execution"]
StreamStatus = Literal["present", "missing", "not_yet_active"]


@dataclass(frozen=True)
class StreamPointer:
    """A pointer-backed stream entry; never a copy of the authority."""

    name: StreamName
    authority: Path | None
    status: StreamStatus
    req_ids: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()
    source_hash: str = ""
    freshness: str = "on_demand"


@dataclass(frozen=True)
class DdpArtifact:
    """In-memory representation of a DDP artifact manifest."""

    domain: str
    artifact_root: Path
    streams: tuple[StreamPointer, ...]
    completeness_verdict: Literal["PASS", "FLAG", "UNKNOWN"] = "UNKNOWN"
    claim_ceiling: str = "design-stage-ddp-artifact-assembly-only"
    generated_by: str = "tools/ddp/artifact.py"
    # AD-09: deterministic reasons explaining a computed completeness_verdict.
    # Empty when verdict is PASS or explicitly caller-supplied. Populated by
    # assemble_manifest when it computes the verdict from the stream pointers.
    completeness_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverageRow:
    """One row in the live coverage projection."""

    stream: StreamName
    status: StreamStatus
    gap_state: Literal["satisfied", "partial", "unmet", "blocked", "deferred"] = "unmet"
    locator: str = ""
