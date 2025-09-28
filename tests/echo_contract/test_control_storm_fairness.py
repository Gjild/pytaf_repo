import sys, subprocess, json
from pathlib import Path

def test_control_storm_allows_bulk_progress(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    (bench/"bench.local.toml").write_text(
        'schema_version="bench.v1"\n[results]\nroot="%s"\n' % tmp_path.as_posix(),
        encoding="utf-8"
    )
    env = {"PYTAF_CONTROL_BURST_LIMIT": "2"}
    rc = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"],
                        cwd=tmp_path, env=env).returncode
    assert rc in (0,1,24)
    rd = max([p for p in tmp_path.glob("run_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    m = json.loads((rd/"manifest.v1.json").read_text("utf-8"))
    assert "bulk_chunk_bytes" in m
