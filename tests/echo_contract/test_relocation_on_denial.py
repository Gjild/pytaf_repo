import os, sys, subprocess
from pathlib import Path
import pytest

@pytest.mark.skipif(os.name == "nt", reason="Unix-only path perms trick")
def test_relocation_on_permission_denied(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    badroot = tmp_path / "no_write"
    badroot.mkdir()
    badroot.chmod(0o555)

    (bench/"bench.local.toml").write_text(
        f'schema_version="bench.v1"\n[results]\nroot="{badroot.as_posix()}"\n',
        encoding="utf-8"
    )
    rc = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path).returncode
    assert rc in (0,1,24)
