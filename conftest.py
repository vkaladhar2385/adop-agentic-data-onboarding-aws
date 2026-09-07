"""Pytest bootstrap: ensure the repo root is importable so tests can do
`from workloads.advisory_transactions...` and `from shared.utils...`.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
