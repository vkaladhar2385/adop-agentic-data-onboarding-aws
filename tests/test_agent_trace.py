from pathlib import Path

from shared.utils.agent_trace import append_trace


def test_append_trace_writes_jsonl(tmp_path, monkeypatch):
    import shared.utils.agent_trace as trace

    monkeypatch.setattr(trace, "REPO_ROOT", tmp_path)
    (tmp_path / "workloads" / "demo_wl").mkdir(parents=True)
    path = append_trace("demo_wl", "discovery", "ok", agent="main")
    assert path.is_file()
    line = path.read_text(encoding="utf-8").strip()
    assert '"phase": "discovery"' in line
    assert '"workload": "demo_wl"' in line
