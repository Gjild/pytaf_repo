from __future__ import annotations

from dataclasses import dataclass
import os
import time

from .spi import Budgets, Transport, TransportDiag


@dataclass
class EchoConfig:
    # Base latency in milliseconds per transaction (minimum cost).
    latency_ms: int = 1
    # If >0, simulate fragmented device behavior by “sending” in fixed-size chunks.
    # We still return a single bytes object, but we sleep per-fragment to emulate pacing.
    fragment_bytes: int = 0
    # Extra trailer latency in milliseconds applied after the last fragment.
    delayed_trailer_ms: int = 0
    # If >0 and the TX length >= rst_after_bytes, simulate a transport reset mid-flight.
    # We raise ConnectionError and mark the transport closed.
    rst_after_bytes: int = 0
    # Legacy cap preserved for tests that tune internal pacing by payload size.
    size_kib_cap: int = 100


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return max(lo, min(v, hi))
    except Exception:
        return default


class EchoTransport(Transport):
    """
    Echo backend for Phase 1 with deterministic pacing, optional fragmentation,
    optional delayed trailer, and optional reset-after-bytes simulation.
    """

    def __init__(self, uri: str, cfg: EchoConfig | None = None):
        self._uri = uri
        # Backward-compat: allow envs to tune latency and size cap.
        base = _env_int("PYTAF_ECHO_BASE_LAT_MS", 1, 0, 10_000)
        cap = _env_int("PYTAF_ECHO_SIZE_KIB_CAP", 100, 1, 100_000)
        if cfg is None:
            cfg = EchoConfig(latency_ms=base, fragment_bytes=0,
                             delayed_trailer_ms=0, rst_after_bytes=0, size_kib_cap=cap)
        else:
            # If cfg provided, still respect env overrides for tests that rely on them.
            cfg.latency_ms = _env_int("PYTAF_ECHO_BASE_LAT_MS", cfg.latency_ms, 0, 10_000)
            cfg.size_kib_cap = _env_int("PYTAF_ECHO_SIZE_KIB_CAP", cfg.size_kib_cap, 1, 100_000)

        self._cfg = cfg
        self._diag = TransportDiag()
        self._is_open = False
        self._broken = False  # set true if we simulate an RST

    def open(self) -> None:
        self._is_open = True
        self._broken = False

    def close(self) -> None:
        self._is_open = False
        # Allow re-open after an RST in tests that exercise recovery
        self._broken = False

    @property
    def resource(self) -> str:
        return self._uri

    @property
    def backend(self) -> str:
        return "echo"

    @property
    def diag(self) -> TransportDiag:
        return self._diag

    def _sleep_ms(self, ms: int) -> None:
        if ms <= 0:
            return
        time.sleep(ms / 1000.0)

    def transact(self, tx: bytes, *, budgets: Budgets) -> bytes:
        if not self._is_open or self._broken:
            raise ConnectionError("echo: transport not open or reset")

        # Simulate an “*IDN?” fast path
        if tx == b"*IDN?":
            self._diag.bytes_tx += len(tx)
            self._sleep_ms(self._cfg.latency_ms)
            out = b"PYTAF,ECHO,1.0\n"
            self._diag.bytes_rx += len(out)
            return out

        # Optional reset-after-bytes behavior
        if self._cfg.rst_after_bytes > 0 and len(tx) >= self._cfg.rst_after_bytes:
            # emulate a mid-flight RST by closing and failing this call
            self._broken = True
            self._is_open = False
            raise ConnectionError("echo: simulated RST after bytes threshold")

        # Base latency + pacing latency (bounded by size_kib_cap for legacy tests)
        size_kib = max(1, len(tx) // 1024)
        pacing_ms = min(size_kib, self._cfg.size_kib_cap)

        # Fragmentation/pacing model
        frag = max(0, self._cfg.fragment_bytes)
        if frag <= 0:
            # Single-shot response with base + pacing + optional trailer delay
            self._sleep_ms(self._cfg.latency_ms + pacing_ms + self._cfg.delayed_trailer_ms)
            rx = bytes(tx)
        else:
            # Sleep per fragment to emulate device drip; still return identity.
            n_frags = (len(tx) + frag - 1) // frag
            # Base latency once, then per-fragment pacing.
            self._sleep_ms(self._cfg.latency_ms)
            for _ in range(n_frags):
                self._sleep_ms(max(0, pacing_ms))
            self._sleep_ms(self._cfg.delayed_trailer_ms)
            rx = bytes(tx)

        self._diag.bytes_tx += len(tx)
        self._diag.bytes_rx += len(rx)
        return rx
