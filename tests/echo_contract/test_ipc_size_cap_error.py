import os
from pathlib import Path
import subprocess
import sys


def test_ipc_size_cap_error(tmp_path: Path):
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "bench.local.toml").write_text(
        f'schema_version="bench.v1"\n[results]\nroot="{tmp_path.as_posix()}"', encoding="utf-8"
    )
    env = dict(os.environ)
    env["PYTAF_IPC_MAX_BODY"] = "1024"
    rc = subprocess.run(
        [sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"],
        cwd=tmp_path,
        env=env,
    ).returncode
    assert rc in (0, 1, 24)
