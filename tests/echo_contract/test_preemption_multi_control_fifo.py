import sys, subprocess
from pathlib import Path
import msgspec

def test_multi_control_fifo_over_bulk(tmp_path: Path):
    bench = tmp_path / "bench"; bench.mkdir()
    (bench/"bench.local.toml").write_text(
        'schema_version="bench.v1"\n[results]\nroot="%s"\n' % tmp_path.as_posix(),
        encoding="utf-8")
    rc = subprocess.run([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path).returncode
    assert rc in (0,1,24)
    rd = max([p for p in tmp_path.glob("run_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    lines = (rd / "results.v1.jsonl").read_text("utf-8").splitlines()
    dec = msgspec.json.Decoder()
    vals = {}
    for ln in lines:
        row = dec.decode(ln.encode("utf-8"))
        if row.get("name") in ("ack_order_1","ack_order_2","ack_order_3","control_preempted_bulk"):
            vals[row["name"]] = int(row["value"])
    assert vals["ack_order_1"] == 4 and vals["ack_order_2"] == 7 and vals["ack_order_3"] == 3
    assert vals["control_preempted_bulk"] == 1
