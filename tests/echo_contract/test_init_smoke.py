from pathlib import Path
import subprocess
import sys


def test_init_non_interactive(tmp_path: Path):
    rc = subprocess.run(
        [sys.executable, "-m", "pytaf.cli.init", "--non-interactive", "--bench-dir", "bench"],
        cwd=tmp_path,
    ).returncode
    assert rc == 0
    assert (tmp_path / "bench/bench.local.toml").exists()
    assert (tmp_path / "bench/cal").is_dir()
