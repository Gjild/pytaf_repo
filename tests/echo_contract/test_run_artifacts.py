import json
from pathlib import Path
import subprocess
import sys


def _run_pytaf_run(cwd: Path) -> int:
    return subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"],
                          cwd=cwd).returncode

def test_run_creates_artifacts(tmp_path: Path):
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "bench.local.toml").write_text(
        f'schema_version="bench.v1"\\n[results]\\nroot="{tmp_path.as_posix()}"\\n',
        encoding="utf-8",
    )
    rc = _run_pytaf_run(tmp_path)
    assert rc in (0, 1, 24)

    run_dirs = [p for p in tmp_path.glob("run_*") if p.is_dir()]
    assert run_dirs, "no run dir created"
    rd = max(run_dirs, key=lambda p: p.stat().st_mtime)

    for must in [
        "results.header.json","manifest.v1.json","layout.v1.json",
        "export/data.excel.csv","export/data.raw.csv",
        "results.v1.jsonl","trace.raw.v1.jsonl","trace.version.txt"
    ]:
        assert (rd / must).exists(), f"missing {must}"

    assert (tmp_path / "latest").exists() or (tmp_path / "LATEST.txt").exists()

    m = json.loads((rd/"manifest.v1.json").read_text("utf-8"))
    assert m["broker_pid"] > 0
    assert "created_utc" in m
    assert "results_root_resolved" in m
    assert "latest_strategy" in m
    assert "ipc_version" in m and "epoch_id" in m
    assert "stale_acknowledged" in m
    assert "parent_pid" in m and isinstance(m["parent_pid"], int)
    assert "shell_hint" in m
    assert "trace_inline_max_bytes" in m
    assert "clean_exit" in m
    assert isinstance(m.get("ack_order", []), list)
    assert isinstance(m.get("ack_order_no_open", []), list)
    assert "broker_lock_path" in m
    assert m.get("broker_lock_was_held", True) in (True, False)
    assert m.get("termination_path") in ("wait","ctrl_break","job_kill","kill","sigint","sigterm","sigkill","unknown")

    hdr = json.loads((rd/"results.header.json").read_text("utf-8"))
    assert hdr.get("ipc_handshake_ok", False) is True
