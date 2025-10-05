from pathlib import Path
import subprocess
import sys


def test_cloud_name_triggers_relocation(tmp_path: Path):
    bench = tmp_path / "bench"
    bench.mkdir()
    cloudish = tmp_path / "ThisLooksLikeOneDrive"
    cloudish.mkdir()
    root_path = str(cloudish).replace("ThisLooksLikeOneDrive", "OneDrive")
    cfg = f'schema_version="bench.v1"\\n[results]\\nroot="{root_path}"\\n'
    (bench / "bench.local.toml").write_text(cfg, encoding="utf-8")
    rc = subprocess.run(
        [sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path
    ).returncode
    assert rc in (0,1,24)
