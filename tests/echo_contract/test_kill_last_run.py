import sys, subprocess, time
from pathlib import Path

def test_kill_last_run_resolves_latest_and_safety(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    (bench/"bench.local.toml").write_text(
        'schema_version="bench.v1"\n[results]\nroot="%s"\n' % tmp_path.as_posix(),
        encoding="utf-8"
    )
    p = subprocess.Popen([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path)
    time.sleep(0.5)
    _ = subprocess.run([sys.executable, "-m", "pytaf.cli.kill", "--last-run", "--bench", "bench/bench.local.toml"], cwd=tmp_path)
    p.wait(timeout=5)
