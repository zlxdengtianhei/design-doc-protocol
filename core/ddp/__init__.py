"""Design Doc Protocol (DDP) additive composition layer.

SL-0 surface: assemble a three-stream (requirements / meaning / design) DDP artifact
projection from existing file pointers. Authority stays in the pointed-to source files;
this package never copies authority content into the projection (AD-09 / AD-18).

This package COMPOSES existing tools (``requirement_doc``, ``design_doc``,
``provenance_mark``, ``tool_receipts``); it does not rewrite or fork them (AD-01).
"""
from __future__ import annotations

from core.ddp.artifact import (
    assemble_manifest,
    discover_streams,
    render_artifact,
    sha256_file,
    write_artifact,
)
from core.ddp.schema import (
    CoverageRow,
    DdpArtifact,
    ReqClass,
    StreamName,
    StreamPointer,
    StreamStatus,
)

__all__ = [
    "CoverageRow",
    "DdpArtifact",
    "ReqClass",
    "StreamName",
    "StreamPointer",
    "StreamStatus",
    "assemble_manifest",
    "discover_streams",
    "render_artifact",
    "sha256_file",
    "write_artifact",
]
