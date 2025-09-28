from __future__ import annotations
import os, base64, msgspec
from pathlib import Path
from .trace_blobs import put_blob
from .win_durability import flush_dir_anchor_if_windows

def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return max(lo, min(v, hi))
    except Exception:
        return default

class TraceWriter:
    def __init__(self, root: Path):
        raw = _env_int("PYTAF_TRACE_INLINE_MAX", 256, 0, 4 * 1024 * 1024)
        self._inline_max = max(64, raw)
        self._enc = msgspec.json.Encoder()
        self._path = root / "trace.raw.v1.jsonl"
        self._f = open(self._path, "wb", buffering=0)
        (root / "trace.version.txt").write_text("trace.raw.v1\n", encoding="utf-8")

    def _write_row(self, row: dict) -> None:
        self._f.write(self._enc.encode(row)); self._f.write(b"\n")

    def tx(self, t_ns: int, uri: str, payload: bytes) -> None:
        self._emit("tx", t_ns, uri, payload)

    def rx(self, t_ns: int, uri: str, payload: bytes) -> None:
        self._emit("rx", t_ns, uri, payload)

    def _emit(self, dir_: str, t_ns: int, uri: str, payload: bytes) -> None:
        row = {"version":"trace.raw.v1","dir":dir_, "t_ns":t_ns, "uri":uri, "len":len(payload)}
        if len(payload) <= self._inline_max:
            row["enc"] = "b64"
            row["b64"] = base64.b64encode(payload).decode("ascii")
        else:
            h, _ = put_blob(self._path.parent, payload)
            row["enc"] = "blob"
            row["blob"] = f"sha256:{h}"
        self._write_row(row)

    def close(self) -> None:
        self._f.flush(); os.fsync(self._f.fileno()); self._f.close()
        flush_dir_anchor_if_windows(self._path.parent)
