from __future__ import annotations

import time
from dataclasses import dataclass

from pytaf.transport.spi import Budgets, Transport, TransportDiag


@dataclass
class EchoConfig:
    latency_ms: int = 3
    fragment_bytes: int = 0
    delayed_trailer_ms: int = 0
    zero_len_every: int = 0
    rst_after_bytes: int = 0


class EchoTransport(Transport):
    def __init__(self, uri: str, cfg: EchoConfig | None = None):
        self._uri = uri
        self._cfg = cfg or EchoConfig()
        self._open = False
        self._diag = TransportDiag()

    @property
    def resource(self) -> str:
        return self._uri

    @property
    def backend(self) -> str:
        return "echo"

    @property
    def diag(self) -> TransportDiag:
        return self._diag

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def transact(self, tx: bytes, *, budgets: Budgets) -> bytes:
        # Phase 0: functional echo only.
        # TODO(phase1): enforce budgets & introduce cancellation preemption points.
        if not self._open:
            raise RuntimeError("transport not open")
        self._diag.bytes_tx += len(tx)
        time.sleep(max(self._cfg.latency_ms, 0) / 1000.0)
        if self._cfg.rst_after_bytes and len(tx) >= self._cfg.rst_after_bytes:
            self._open = False
            self._diag.reconnects += 1
            raise ConnectionError("echo: simulated RST-like abort")
        payload = tx
        if self._cfg.fragment_bytes and len(payload) > self._cfg.fragment_bytes:
            parts = []
            for i in range(0, len(payload), self._cfg.fragment_bytes):
                parts.append(payload[i : i + self._cfg.fragment_bytes])
                time.sleep(0.0005)
            payload = b"".join(parts)
        if self._cfg.delayed_trailer_ms:
            time.sleep(self._cfg.delayed_trailer_ms / 1000.0)
        self._diag.bytes_rx += len(payload)
        return payload
