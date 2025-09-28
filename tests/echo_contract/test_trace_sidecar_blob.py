import sys, subprocess
from pathlib import Path

def test_sidecar_blob_created(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    (bench/"bench.local.toml").write_text(
        'schema_version="bench.v1"\n[results]\nroot="%s"\n' % tmp_path.as_posix(),
        encoding="utf-8"
    )
    rc = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path).returncode
    assert rc in (0,1,24)
    rd = max([p for p in tmp_path.glob("run_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    blobs = list((rd / "trace_blobs").glob("*.bin"))
    assert blobs, "expected at least one sidecar blob file"
