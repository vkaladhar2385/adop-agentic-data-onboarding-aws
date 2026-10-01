"""Tests for the Phase 7 import-boundary lint."""
from __future__ import annotations

from tools.check_import_boundaries import main, scan_file


def test_repo_respects_boundary():
    assert main([]) == 0


def test_detects_pack_import(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from platform_packs.aws import thing\n", encoding="utf-8")
    assert scan_file(bad)


def test_detects_pack_path_reference(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('TEMPLATES = "platform-packs/azure/templates"\n', encoding="utf-8")
    assert scan_file(bad)


def test_clean_file_passes(tmp_path):
    ok = tmp_path / "ok.py"
    ok.write_text("from shared.codegen.renderer import render\n", encoding="utf-8")
    assert scan_file(ok) == []
