import sys, subprocess
from pathlib import Path

def test_trace_inline_threshold_env(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    (bench/"bench.local.toml").write_text(
        'schema_version="bench.v1"\n[results]\nroot="%s"\n' % tmp_path.as_posix(),
        encoding="utf-8"
    )
    env = {"PYTAF_TRACE_INLINE_MAX": "4096"}
    rc = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path, env=env).returncode
    assert rc in (0,1,24)
    rd = max([p for p in tmp_path.glob("run_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    lines = (rd / "trace.raw.v1.jsonl").read_text("utf-8").splitlines()
    assert any('"enc":"b64"' in ln for ln in lines), "expected inline b64 entries"
