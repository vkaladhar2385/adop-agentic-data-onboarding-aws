"""Render Jinja2 templates from validated specs."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import jinja2

from .exceptions import RenderError, TemplateNotFoundError
from .slot_extractor import validate_slots

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "shared" / "templates"

HEADER = """\
# spec_hash: {spec_hash}
# template_id: {template_id}
# template_hash: {template_hash}
# schema_version: {schema_version}
# rendered_at: {rendered_at}
"""


def _template_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _load_template(template_id: str) -> tuple[str, str, str]:
    for ext in (".py.j2", ".json.j2"):
        path = TEMPLATES_DIR / f"{template_id}{ext}"
        if path.exists():
            source = path.read_text(encoding="utf-8")
            return source, _template_hash(source), ext
    raise TemplateNotFoundError(template_id, str(TEMPLATES_DIR))


def render(
    spec: dict,
    spec_hash: str,
    template_id: str,
    schema_version: str = "v1",
    rendered_at: str | None = None,
) -> str:
    source, template_hash, ext = _load_template(template_id)
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

    if ext == ".json.j2":
        return body

    header = HEADER.format(
        spec_hash=spec_hash,
        template_id=template_id,
        template_hash=template_hash,
        schema_version=schema_version,
        rendered_at=ts,
    )
    return header + body
