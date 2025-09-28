import sys, subprocess
from pathlib import Path

def test_stale_temp_blocks_without_ack(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    (bench/"bench.local.toml").write_text(
        'schema_version="bench.v1"\n[results]\nroot="%s"\n' % tmp_path.as_posix(),
        encoding="utf-8"
    )
    (tmp_path / "results.v1.jsonl.tmp").write_text("junk", encoding="utf-8")
    rc = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path).returncode
    assert rc == 28
    rc2 = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml", "--acknowledge-stale"], cwd=tmp_path).returncode
    assert rc2 in (0,1,24)
