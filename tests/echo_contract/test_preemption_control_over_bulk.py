from pathlib import Path
import subprocess
import sys

import msgspec


def test_control_preempts_bulk_single_control(tmp_path: Path):
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "bench.local.toml").write_text(
        f'schema_version="bench.v1"\\n[results]\\nroot="{tmp_path.as_posix()}"\\n',
        encoding="utf-8",
    )
    rc = subprocess.run(
        [sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path
    ).returncode
    assert rc in (0, 1, 24)
    rd = max([p for p in tmp_path.glob("run_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    lines = (rd / "results.v1.jsonl").read_text("utf-8").splitlines()
    dec = msgspec.json.Decoder()
    vals = {}
    for ln in lines:
        row = dec.decode(ln.encode("utf-8"))
        if row.get("name") in ("ack_order_1","ack_order_2","ack_order_3","control_preempted_bulk"):
            vals[row["name"]] = int(row["value"])
    assert vals.get("ack_order_1") == 4
    assert vals.get("ack_order_2") in (7,)
    assert vals.get("ack_order_3") == 3
    assert vals.get("control_preempted_bulk") == 1
