"""Parse required_slots header from Jinja templates."""

from .exceptions import MissingSlotError


def parse_required_slots_header(template_source: str) -> set[str]:
    for line in template_source.splitlines():
        stripped = line.strip()
        if stripped.startswith("{#") and "required_slots:" in stripped:
            _, _, slots_str = stripped.partition("required_slots:")
            slots_str = slots_str.rstrip("#}").strip()
            return {s.strip() for s in slots_str.split(",") if s.strip()}
    return set()


def validate_slots(template_source: str, spec: dict, template_id: str) -> None:
    declared = parse_required_slots_header(template_source)
    if not declared:
        return
    missing = declared - set(spec.keys())
    if missing:
        raise MissingSlotError(template_id, missing)
