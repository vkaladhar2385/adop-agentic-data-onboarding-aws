"""Block agent writes to renderer-owned artifacts unless ADOP_RENDERER_TOKEN is set."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TOKEN_ENV = "ADOP_RENDERER_TOKEN"

# Renderer-owned scripts only (not local_runner, spark_transforms, register_catalog, etc.).
_GENERATED_SCRIPT_RE = re.compile(
    r"workloads[/\\][^/\\]+[/\\]scripts[/\\]"
    r"(?:extract[/\\]ingest_to_bronze\.py|"
    r"transform[/\\]bronze_to_silver\.py|"
    r"transform[/\\]silver_to_gold\.py|"
    r"quality[/\\]run_quality_checks\.py)$",
    re.IGNORECASE,
)
_SFN_RE = re.compile(
    r"workloads[/\\][^/\\]+[/\\]orchestration[/\\][^/\\]+_state_machine\.json$",
    re.IGNORECASE,
)
_DAG_RE = re.compile(
    r"workloads[/\\][^/\\]+[/\\]dags[/\\][^/\\]+_pipeline\.py$",
    re.IGNORECASE,
)
_RENDERER_HINTS = ("render_workload.py", "check_codegen_drift.py")
_SHELL_WRITE_HINTS = (
    ">",
    ">>",
    "out-file",
    "set-content",
    "add-content",
    "tee ",
    "new-item",
    "copy-item",
    "move-item",
    "copy ",
    "cp ",
    "mv ",
    "ni ",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_LOG_PATH = REPO_ROOT / "logs" / "hook_blocks.jsonl"

BLOCK_REASON = (
    "Direct write to renderer-owned artifacts is blocked. "
    "Edit config/codegen/*.spec.yaml (and templates), then run "
    "`python tools/render_workload.py --workload {name} --all --write`. "
    "Set ADOP_RENDERER_TOKEN only inside the renderer."
)


def is_protected_path(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    if _GENERATED_SCRIPT_RE.search(normalized):
        return True
    if _SFN_RE.search(normalized):
        return True
    return bool(_DAG_RE.search(normalized))


def extract_file_paths(event: dict) -> list[str]:
    """Pull target paths from Cursor or Claude Code hook payloads."""
    paths: list[str] = []
    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    for key in ("path", "file_path", "filePath"):
        value = event.get(key) or tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)

    edits = tool_input.get("edits") or event.get("edits") or []
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict):
                for key in ("path", "file_path", "filePath"):
                    value = edit.get(key)
                    if isinstance(value, str) and value:
                        paths.append(value)

    command = _command_text(event)
    if command:
        paths.extend(_paths_in_command(command))

    return paths


def renderer_token_present() -> bool:
    return bool(os.environ.get(TOKEN_ENV, "").strip())


def shell_command_is_renderer(command: str) -> bool:
    lowered = command.replace("\\", "/").lower()
    return any(hint in lowered for hint in _RENDERER_HINTS)


def shell_command_writes_protected(command: str) -> bool:
    if shell_command_is_renderer(command):
        return False
    if not any(is_protected_path(p) for p in _paths_in_command(command)):
        # Also catch unquoted relative paths that regex on the whole string.
        normalized = command.replace("\\", "/")
        if not (
            _GENERATED_SCRIPT_RE.search(normalized)
            or _SFN_RE.search(normalized)
            or _DAG_RE.search(normalized)
        ):
            return False
    lowered = command.lower()
    return any(hint in lowered for hint in _SHELL_WRITE_HINTS)


def decide(event: dict) -> tuple[bool, str]:
    """Return (allow, reason)."""
    if renderer_token_present():
        return True, ""

    command = _command_text(event)
    if command and shell_command_writes_protected(command):
        return False, BLOCK_REASON

    for path in extract_file_paths(event):
        if is_protected_path(path):
            if command and shell_command_is_renderer(command):
                continue
            return False, BLOCK_REASON
    return True, ""


def log_block(file_path: str, reason: str) -> None:
    try:
        HOOK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cwd": os.getcwd(),
            "attempted_path": file_path,
            "reason": reason,
        }
        with HOOK_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def parse_hook_stdin(raw: str | bytes) -> dict:
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = raw
    text = text.lstrip("\ufeff").strip()
    if not text:
        return {}
    return json.loads(text)


def cursor_response(allow: bool, reason: str = "") -> dict:
    if allow:
        return {"continue": True, "permission": "allow"}
    return {
        "continue": True,
        "permission": "deny",
        "user_message": reason,
        "agent_message": reason,
    }


def claude_response(allow: bool, reason: str = "") -> dict | None:
    if allow:
        return None
    return {
        "hookSpecificOutput": {
            "permissionDecision": "deny",
            "reason": reason,
        }
    }


def _is_cursor_event(event: dict) -> bool:
    # Claude Code uses PreToolUse (PascalCase). Cursor uses preToolUse / beforeShellExecution.
    hook_event = str(event.get("hook_event_name") or event.get("hookEventName") or "")
    return hook_event != "PreToolUse"


def emit_and_exit(event: dict, allow: bool, reason: str) -> int:
    """Cursor uses permission JSON; Claude Code uses hookSpecificOutput + exit 2."""
    if _is_cursor_event(event):
        print(json.dumps(cursor_response(allow, reason)))
        return 0 if allow else 2

    if not allow:
        print(json.dumps(claude_response(False, reason)))
        print(reason, file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    del argv  # hooks read stdin only
    try:
        event = parse_hook_stdin(sys.stdin.buffer.read())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        print(json.dumps(cursor_response(True)))
        return 0

    if not event:
        print(json.dumps(cursor_response(True)))
        return 0

    allow, reason = decide(event)
    if not allow:
        paths = extract_file_paths(event) or [_command_text(event) or "(unknown)"]
        log_block(paths[0], reason)
    return emit_and_exit(event, allow, reason)


def _command_text(event: dict) -> str:
    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    for key in ("command", "command_line"):
        value = event.get(key) or tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _paths_in_command(command: str) -> list[str]:
    found = []
    normalized = command.replace("\\", "/")
    for match in re.finditer(r"workloads/[^ \t\"']+", normalized, flags=re.IGNORECASE):
        found.append(match.group(0))
    return found


if __name__ == "__main__":
    raise SystemExit(main())

