"""Tests for shared.codegen.write_guard (Cursor + Claude Code hook logic)."""

from __future__ import annotations

import io
import json
import os
from unittest import mock

import pytest

from shared.codegen.write_guard import (
    BLOCK_REASON,
    TOKEN_ENV,
    decide,
    is_protected_path,
    main,
    shell_command_writes_protected,
)


@pytest.mark.parametrize(
    "path,protected",
    [
        ("workloads/foo/scripts/extract/ingest_to_bronze.py", True),
        (r"workloads\foo\scripts\quality\run_quality_checks.py", True),
        ("workloads/foo/scripts/transform/local_runner.py", False),
        ("workloads/foo/scripts/transform/spark_transforms.py", False),
        (
            "workloads/foo/orchestration/foo_state_machine.json",
            True,
        ),
        ("workloads/foo/dags/foo_pipeline.py", True),
        ("workloads/foo/config/codegen/ingest_to_bronze.spec.yaml", False),
        ("workloads/foo/sql/silver/create.sql", False),
        ("workloads/foo/tests/unit/test_x.py", False),
    ],
)
def test_is_protected_path(path: str, protected: bool) -> None:
    assert is_protected_path(path) is protected


def test_decide_blocks_script_without_token() -> None:
    event = {
        "tool_name": "Write",
        "tool_input": {"path": "workloads/x/scripts/extract/ingest_to_bronze.py"},
    }
    allow, reason = decide(event)
    assert allow is False
    assert "renderer" in reason.lower() or "blocked" in reason.lower()


def test_decide_allows_script_with_renderer_token() -> None:
    event = {
        "tool_name": "Write",
        "tool_input": {"path": "workloads/x/scripts/extract/ingest_to_bronze.py"},
    }
    with mock.patch.dict(os.environ, {TOKEN_ENV: "render"}):
        allow, _ = decide(event)
    assert allow is True


def test_decide_allows_non_protected_path() -> None:
    event = {
        "tool_name": "Write",
        "tool_input": {"path": "workloads/x/config/source.yaml"},
    }
    allow, _ = decide(event)
    assert allow is True


def test_shell_redirect_to_protected_blocked() -> None:
    cmd = "echo x > workloads/foo/scripts/extract/ingest_to_bronze.py"
    assert shell_command_writes_protected(cmd) is True
    event = {"tool_name": "Shell", "tool_input": {"command": cmd}}
    allow, _ = decide(event)
    assert allow is False


def test_shell_render_workload_allowed() -> None:
    cmd = "python tools/render_workload.py --workload foo --all --write"
    event = {"tool_name": "Shell", "tool_input": {"command": cmd}}
    allow, _ = decide(event)
    assert allow is True


def _stdin_with_bytes(data: bytes) -> object:
    """Minimal stdin stand-in for hook tests under pytest capture."""

    class _Stdin:
        buffer = io.BytesIO(data)

    return _Stdin()


def test_main_fail_open_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin_with_bytes(b"not-json"))
    rc = main()
    assert rc == 0


def test_main_fail_open_on_empty_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _stdin_with_bytes(b""))
    rc = main()
    assert rc == 0


def test_main_blocks_protected_write(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {"path": "workloads/x/scripts/extract/ingest_to_bronze.py"},
    }
    monkeypatch.setattr("sys.stdin", _stdin_with_bytes(json.dumps(payload).encode()))
    rc = main()
    assert rc == 2
    out = capsys.readouterr().out
    assert "deny" in out


def test_block_reason_mentions_render_command() -> None:
    assert "render_workload.py" in BLOCK_REASON
