from pathlib import Path
import subprocess
import sys


def test_broker_exits_on_parent_eof(tmp_path: Path):
    p = subprocess.Popen(
        [sys.executable, "-m", "pytaf.broker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        cwd=tmp_path,
    )
    assert p.stdin and p.stdout
    from pytaf.broker import ipc

    ipc.write_msg(p.stdin.fileno(), {"op": "ping", "epoch_id": 0, "op_id": 1})
    _ = ipc.read_msg(p.stdout.fileno())
    p.stdin.close()  # parent EOF
    p.wait(timeout=3)
    assert p.returncode == 0
