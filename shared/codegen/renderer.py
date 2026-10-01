"""Render Jinja2 templates from validated specs."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import jinja2

from .exceptions import RenderError, TemplateNotFoundError
from .slot_extractor import validate_slots

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_TEMPLATES_DIR = REPO_ROOT / "shared" / "templates"
PACKS_DIR = REPO_ROOT / "platform-packs"
DEFAULT_PROFILE = "aws"

# Back-compat alias: some callers/tests reference TEMPLATES_DIR.
TEMPLATES_DIR = SHARED_TEMPLATES_DIR


def _template_search_dirs(profile: str | None) -> list[Path]:
    """Resolve template search order: active platform pack, shared common, shared root.

    Defaulting to the AWS pack keeps drift re-renders byte-identical after the
    AWS templates were relocated into platform-packs/aws/templates/.
    """
    dirs: list[Path] = []
    if profile:
        dirs.append(PACKS_DIR / profile / "templates")
    dirs.append(SHARED_TEMPLATES_DIR / "common")
    dirs.append(SHARED_TEMPLATES_DIR)
    return dirs

HEADER = """\
# spec_hash: {spec_hash}
# template_id: {template_id}
# template_hash: {template_hash}
# schema_version: {schema_version}
# rendered_at: {rendered_at}
"""


def _template_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _load_template(template_id: str, profile: str = DEFAULT_PROFILE) -> tuple[str, str, str]:
    for base in _template_search_dirs(profile):
        for ext in (".py.j2", ".json.j2", ".sql.j2"):
            path = base / f"{template_id}{ext}"
            if path.exists():
                source = path.read_text(encoding="utf-8")
                return source, _template_hash(source), ext
    searched = ", ".join(str(d) for d in _template_search_dirs(profile))
    raise TemplateNotFoundError(template_id, searched)


def render(
    spec: dict,
    spec_hash: str,
    template_id: str,
    schema_version: str = "v1",
    rendered_at: str | None = None,
    profile: str = DEFAULT_PROFILE,
) -> str:
    source, template_hash, ext = _load_template(template_id, profile)
    validate_slots(source, spec, template_id)

    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ts = rendered_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ctx = {
        **spec,
        "spec_hash": spec_hash,
        "template_id": template_id,
        "template_hash": template_hash,
        "schema_version": schema_version,
        "rendered_at": ts,
    }
    try:
        body = env.from_string(source).render(**ctx)
    except jinja2.TemplateError as exc:
        raise RenderError(template_id, str(exc)) from exc

    if ext in (".json.j2", ".sql.j2"):
        return body

    header = HEADER.format(
        spec_hash=spec_hash,
        template_id=template_id,
        template_hash=template_hash,
        schema_version=schema_version,
        rendered_at=ts,
    )
    return header + body
