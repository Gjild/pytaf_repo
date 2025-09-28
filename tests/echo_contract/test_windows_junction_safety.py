import os, sys, subprocess
from pathlib import Path
import pytest

@pytest.mark.skipif(os.name != "nt", reason="Windows-only")
def test_latest_junction_does_not_delete_target_or_real_dir(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    (bench/"bench.local.toml").write_text(
        'schema_version="bench.v1"\n[results]\nroot="%s"\n' % tmp_path.as_posix(),
        encoding="utf-8"
    )
    subprocess.check_call([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path)
    run_dirs = sorted([p for p in tmp_path.glob("run_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    assert run_dirs, "no run dir"
    run_a = run_dirs[-1]
    assert run_a.exists()

    (tmp_path / "latest").mkdir(exist_ok=True)
    (tmp_path / "latest/keep.txt").write_text("keep", encoding="utf-8")

    subprocess.check_call([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path)
    assert (tmp_path / "latest/keep.txt").exists()
    assert (tmp_path / "LATEST.txt").exists()
