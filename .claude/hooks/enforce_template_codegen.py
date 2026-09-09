#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block Write/Edit to renderer-owned artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.codegen.write_guard import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
