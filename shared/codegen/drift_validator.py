"""Verify rendered artifact headers match spec re-render (ADOP drift pattern)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .renderer import render
from .spec_loader import compute_spec_hash, load_yaml_spec

HEADER_RE = re.compile(
    r"^# spec_hash: ([a-f0-9]{64})\n"
    r"# template_id: ([\w]+)\n"
    r"# template_hash: ([a-f0-9]{64})\n"
    r"# schema_version: (v\d+)\n"
    r"# rendered_at: (.+)\n",
    re.MULTILINE,
)


@dataclass
class DriftReport:
    path: str
    ok: bool
    reason: str = ""


def parse_header(content: str) -> dict | None:
    match = HEADER_RE.match(content)
    if not match:
        return None
    return {
        "spec_hash": match.group(1),
        "template_id": match.group(2),
        "template_hash": match.group(3),
        "schema_version": match.group(4),
        "rendered_at": match.group(5),
    }


def verify_artifact(
    artifact_path: Path,
    spec_path: Path,
    schema_name: str,
    template_id: str | None = None,
) -> DriftReport:
    artifact_path = Path(artifact_path)
    spec_path = Path(spec_path)
    if not artifact_path.is_file():
        return DriftReport(str(artifact_path), False, "artifact missing")
    if not spec_path.is_file():
        return DriftReport(str(artifact_path), False, "spec missing")

    content = artifact_path.read_text(encoding="utf-8")
    spec = load_yaml_spec(spec_path)
    spec_hash = compute_spec_hash(spec)
    header = parse_header(content)

    if header is None:
        if artifact_path.suffix != ".json":
            return DriftReport(str(artifact_path), False, "missing 5-line codegen header")
        tid = template_id or spec.get("template_id")
        if not tid:
            return DriftReport(str(artifact_path), False, "JSON artifact needs template_id")
        expected = render(
            spec,
            spec_hash,
            tid,
            schema_version=spec.get("schema_version", "v1"),
        )
        if content != expected:
            return DriftReport(str(artifact_path), False, "body drift (re-render differs from file)")
        return DriftReport(str(artifact_path), True)

    if header["spec_hash"] != spec_hash:
        return DriftReport(
            str(artifact_path),
            False,
            f"spec_hash mismatch (file={header['spec_hash'][:12]}..., spec={spec_hash[:12]}...)",
        )

    expected = render(
        spec,
        spec_hash,
        header["template_id"],
        schema_version=header["schema_version"],
        rendered_at=header["rendered_at"],
    )
    if content != expected:
        return DriftReport(str(artifact_path), False, "body drift (re-render differs from file)")
    return DriftReport(str(artifact_path), True)
