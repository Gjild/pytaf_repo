from __future__ import annotations
import os
import time
from dataclasses import dataclass
from .spi import Transport, Budgets, TransportDiag


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return max(lo, min(v, hi))
    except Exception:
        return default


@dataclass
class EchoConfig:
    """
    Configuration for the echo transport used in tests.

    Expected by tests:
      - latency_ms:            base artificial latency per operation (or per fragment)
      - fragment_bytes:        if set, break the response into these-sized fragments (simulated)
      - delayed_trailer_ms:    extra delay after the last fragment before returning
      - rst_after_bytes:       if set and tx size exceeds this threshold, emulate a reset/close

    Internal/compat:
      - size_kib_cap:          legacy latency scaling cap used by broker tests
    """
    # Base latency to simulate work per call
    latency_ms: int = 1
    # Optional fragmentation/trailer knobs (phase-1 tests don't deeply assert these)
    fragment_bytes: int = 0
    delayed_trailer_ms: int = 0
    # Simulated "RST-like" abort if payload exceeds N bytes
    rst_after_bytes: int | None = None
    # Legacy cap (kept for env overrides), not strictly required by tests
    size_kib_cap: int = 100

def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(os.environ.get(name, str(default)))
        return max(lo, min(v, hi))
    except Exception:
        return default

class EchoTransport(Transport):
    """
    Phase-1 echo transport:
      - identity echo (returns exactly what was sent)
      - optional simulated abort via rst_after_bytes -> raises ConnectionError
      - simple latency per call
    """
    def __init__(self, uri: str, cfg: EchoConfig | None = None):
        self._uri = uri
        base = _env_int("PYTAF_ECHO_BASE_LAT_MS", 1, 0, 1000)
        cap  = _env_int("PYTAF_ECHO_SIZE_KIB_CAP", 100, 1, 10000)
        self._cfg = cfg or EchoConfig(latency_ms=base, size_kib_cap=cap)
        self._diag = TransportDiag()
        self._is_open = False

    def open(self) -> None:
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    @property
    def resource(self) -> str:
        return self._uri

    @property
    def backend(self) -> str:
        return "echo"

    @property
    def diag(self) -> TransportDiag:
        return self._diag

    def transact(self, tx: bytes, *, budgets: Budgets) -> bytes:
        if not self._is_open:
            raise RuntimeError("echo: transport not open")

        # Simulate a transport-level abort/reset if payload is above threshold
        if self._cfg.rst_after_bytes is not None and len(tx) > self._cfg.rst_after_bytes:
            self._is_open = False
            # Tests expect ConnectionError specifically
            raise ConnectionError("echo: rst abort")

        # Simulate latency (bounded by size cap for crude scaling)
        size_kib = max(1, len(tx) // 1024)
        delay_ms = max(self._cfg.latency_ms, min(self._cfg.size_kib_cap, size_kib))
        time.sleep(delay_ms / 1000.0)

        # Identity echo
        self._diag.bytes_tx += len(tx)
        self._diag.bytes_rx += len(tx)
        return tx