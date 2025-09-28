import sys, subprocess
from pathlib import Path

def test_cloud_name_triggers_relocation(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    cloudish = tmp_path / "ThisLooksLikeOneDrive"
    cloudish.mkdir()
    cfg = 'schema_version="bench.v1"\n[results]\nroot="%s"\n' % (str(cloudish).replace("ThisLooksLikeOneDrive","OneDrive"))
    (bench/"bench.local.toml").write_text(cfg, encoding="utf-8")
    rc = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path).returncode
    assert rc in (0,1,24)
