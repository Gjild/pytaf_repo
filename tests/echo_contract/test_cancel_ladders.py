import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def test_parent_signal_path(tmp_path: Path):
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "bench.local.toml").write_text(
        f'schema_version="bench.v1"\\n[results]\\nroot="{tmp_path.as_posix()}"\\n', encoding="utf-8"
    )
    p = subprocess.Popen([sys.executable, "-m", "pytaf.cli.run", "--bench", "bench/bench.local.toml"], cwd=tmp_path)
    time.sleep(0.3)
    if os.name != "nt":
        try:
            p.send_signal(signal.SIGINT)
            p.wait(timeout=3)
        except Exception:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                p.kill()
                p.wait(timeout=3)
    else:
        try:
            p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            p.wait(timeout=4)
        except Exception:
            p.kill()
            p.wait(timeout=3)
