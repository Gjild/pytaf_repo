import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows-only")
def test_broken_junction_recreate(tmp_path: Path):
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "bench.local.toml").write_text(
        f'schema_version="bench.v1"\\n[results]\\nroot="{tmp_path.as_posix()}"\\n', encoding="utf-8"
    )
    subprocess.check_call([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path)
    rd = max([p for p in tmp_path.glob("run_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    shutil.rmtree(rd)
    subprocess.check_call([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path)
    assert (tmp_path / "latest").exists() or (tmp_path / "LATEST.txt").exists()
