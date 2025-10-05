from __future__ import annotations

import os
import struct
import time
from typing import Any, Literal, TypedDict

import msgspec

MAGIC = b"PTAF"
VERSION = 1
_HDR = struct.Struct(">4sBIQ")  # magic(4), ver(u8), len(u32), mono_ns(u64)


def _max_body() -> int:
    try:
        v = int(os.environ.get("PYTAF_IPC_MAX_BODY", "8388608"))
        return max(1024, min(v, 128 * 1024 * 1024))
    except Exception:
        return 8 * 1024 * 1024


class OpMsg(TypedDict, total=False):
    op: Literal["open", "close", "xact", "ping", "shutdown", "flush"]
    epoch_id: int
    op_id: int
    resource: str | None
    lane: Literal["control", "bulk"] | None
    payload: bytes | None


class AckMsg(TypedDict, total=False):
    ok: bool
    op_id: int
    epoch_id: int
    ipc_version: int
    diag: dict[str, Any] | None
    payload: bytes | None
    error: str | None


_enc = msgspec.msgpack.Encoder()
_dec = msgspec.msgpack.Decoder()


def now_mono_ns() -> int:
    return time.monotonic_ns()


def write_msg(fd: int, payload: dict[str, Any]) -> None:
    body = _enc.encode(payload)
    if len(body) > _max_body():
        raise ValueError("ipc: payload too large")
    os.write(fd, _HDR.pack(MAGIC, VERSION, len(body), now_mono_ns()))
    os.write(fd, body)


def read_msg(fd: int) -> dict[str, Any]:
    hdr = _read_exact(fd, _HDR.size)
    magic, ver, n, mono = _HDR.unpack(hdr)
    if magic != MAGIC or ver != VERSION:
        raise RuntimeError("ipc: bad magic/version")
    if n > _max_body():
        raise RuntimeError("ipc: body too large")
    body = _read_exact(fd, n)
    msg: dict[str, Any] = _dec.decode(body)
    msg["_mono_ns"] = mono
    return msg


def _read_exact(fd: int, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise EOFError("ipc: short read")
        buf += chunk
    return bytes(buf)