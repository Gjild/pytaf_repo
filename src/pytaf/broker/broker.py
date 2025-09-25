from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import os
import select
import signal
import time
from typing import Any, Literal

from pytaf.broker import epochs, ipc
from pytaf.broker.lanes import DualLaneQueue
from pytaf.transport.echo import EchoConfig, EchoTransport
from pytaf.transport.spi import Budgets
from pytaf.util.lockfile import BrokerLock

Lane = Literal["control", "bulk"]

@dataclass
class Session:
    uri: str
    lanes: DualLaneQueue
    xport: EchoTransport
    control_burst: int = 0

def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return max(lo, min(v, hi))
    except Exception:
        return default

class Broker:
    def __init__(self, r_fd: int, w_fd: int, epoch: epochs.Epoch):
        self._r, self._w = r_fd, w_fd
        self._epoch = epoch
        self._sessions: dict[str, Session] = {}
        self._running = True
        self._bulk_chunk = _env_int("PYTAF_BULK_CHUNK", 16384, 512, 1 << 20)
        self._peek_handle: int | None = None
        self._bulk_state: dict[str, dict[str, Any]] = {}
        self._set_nonblocking(self._r)
        self._fair_burst_limit = _env_int("PYTAF_CONTROL_BURST_LIMIT", 8, 1, 256)
        lock_path = os.environ.get("PYTAF_BROKER_LOCK", "")
        self._lock = BrokerLock(lock_path) if lock_path else None
        self._lock_was_held = False
        if self._lock:
            self._lock.acquire_exclusive()
            self._lock_was_held = True

    def _set_nonblocking(self, fd: int) -> None:
        if os.name != "nt":
            import fcntl
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        else:
            try:
                import msvcrt
                self._peek_handle = msvcrt.get_osfhandle(fd)  # type: ignore[attr-defined]
            except Exception:
                self._peek_handle = None

    def _ipc_readable(self, timeout: float = 0.0) -> bool:
        if os.name != "nt":
            try:
                r, _, _ = select.select([self._r], [], [], timeout)
                return bool(r)
            except Exception:
                return False
        if self._peek_handle is None:
            return False
        try:
            import ctypes as c
            import ctypes.wintypes as w
            avail = w.DWORD()
            ok = c.windll.kernel32.PeekNamedPipe(  # type: ignore[attr-defined]
                self._peek_handle, None, 0, None, c.byref(avail), None
            )
            if not ok:
                # Treat broken pipe as "readable" to let reader handle EOF.
                err_code = int(c.GetLastError())  # type: ignore[attr-defined]
                return err_code == 109  # ERROR_BROKEN_PIPE
            return avail.value > 0
        except Exception:
            return False

    def _ensure(self, uri: str) -> Session:
        s = self._sessions.get(uri)
        if s:
            return s
        sess = Session(uri=uri, lanes=DualLaneQueue(), xport=EchoTransport(uri, EchoConfig()))
        sess.xport.open()
        self._sessions[uri] = sess
        return sess

    def _ack(
        self,
        ok: bool,
        op_id: int,
        payload: bytes | None = None,
        diag: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        d: dict[str, Any] = {"lock_was_held": bool(self._lock_was_held)}
        if diag:
            d.update(diag)
        ipc.write_msg(self._w, {
            "ok": ok,
            "op_id": op_id,
            "epoch_id": self._epoch.id,
            "ipc_version": ipc.VERSION,
            "payload": payload,
            "diag": d,
            "error": error,
        })

    def _dispatch_ipc(self, msg: dict[str, Any]) -> None:
        op = msg.get("op")
        op_id = int(msg.get("op_id", 0))
        if op == "open":
            uri = str(msg["resource"])
            self._ensure(uri)
            self._ack(True, op_id)
            return
        if op == "close":
            uri = str(msg["resource"])
            sess = self._sessions.pop(uri, None)
            if sess:
                with suppress(Exception):
                    sess.xport.close()
            self._bulk_state.pop(uri, None)
            self._ack(True, op_id)
            return
        if op == "xact":
            uri = str(msg["resource"])
            lane: Lane = msg.get("lane") or "control"
            tx: bytes = msg.get("payload") or b""
            sess = self._ensure(uri)
            if lane == "control":
                sess.lanes.put("control", {"op_id": op_id, "tx": tx, "lane": "control"})
            else:
                self._bulk_state[uri] = {"op_id": op_id, "tx": tx, "ofs": 0}
            return
        if op == "ping":
            self._ack(True, op_id, payload=b"pong", diag={"broker_ready": True})
            return
        if op == "shutdown":
            self._ack(True, op_id)
            self._running = False
            return
        self._ack(False, op_id, error=f"unknown op {op}")

    def _service_control_if_any(self, sess: Session) -> bool:
        op = sess.lanes.get_nowait_or_none()
        if not op:
            return False
        tx: bytes = op.get("tx", b"")
        budgets = Budgets(write_ms=0, complete_ms=0, read_ms=0, total_ms=0)
        rx = sess.xport.transact(tx, budgets=budgets)
        self._ack(True, int(op["op_id"]), payload=rx, diag={"bytes_rx": sess.xport.diag.bytes_rx})
        sess.control_burst += 1
        return True

    def _advance_bulk_tick(self, uri: str, sess: Session, st: dict[str, Any]) -> None:
        tx: bytes = st["tx"]
        ofs: int = int(st["ofs"])
        size = len(tx)
        if ofs >= size:
            return
        chunk = max(1, min(self._bulk_chunk, size - ofs))
        budgets = Budgets(write_ms=0, complete_ms=0, read_ms=0, total_ms=0)
        rx = sess.xport.transact(tx[ofs:ofs + chunk], budgets=budgets)
        st["ofs"] = ofs + chunk
        self._service_control_if_any(sess)
        if int(st["ofs"]) >= size:
            self._ack(True, int(st["op_id"]), payload=rx, diag={"bytes_rx": sess.xport.diag.bytes_rx})
            self._bulk_state.pop(uri, None)

    def run(self) -> int:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        while self._running:
            drained = 0
            while drained < 64 and self._ipc_readable(0.0):
                try:
                    msg = ipc.read_msg(self._r)
                except EOFError:
                    self._running = False
                    break
                self._dispatch_ipc(msg)
                drained += 1

            for uri, sess in list(self._sessions.items()):
                progressed = self._service_control_if_any(sess)
                if progressed and sess.control_burst >= self._fair_burst_limit and uri in self._bulk_state:
                    self._advance_bulk_tick(uri, sess, self._bulk_state[uri])
                    sess.control_burst = 0
                else:
                    st = self._bulk_state.get(uri)
                    if st:
                        self._advance_bulk_tick(uri, sess, st)
                        if not progressed:
                            # leave burst counter unchanged if no control progressed
                            pass
                        else:
                            sess.control_burst = 0
            time.sleep(0.001)

        for s in list(self._sessions.values()):
            with suppress(Exception):
                s.xport.close()
        if self._lock:
            self._lock.release()
        return 0

def main_broker(r_fd: int, w_fd: int) -> int:
    ep = epochs.new_epoch()
    br = Broker(r_fd, w_fd, ep)
    return br.run()
