from __future__ import annotations

from dataclasses import dataclass
import secrets
import time


@dataclass(frozen=True)
class Epoch:
    id: int
    t0_monotonic_ns: int


def new_epoch() -> Epoch:
    return Epoch(id=secrets.randbits(31), t0_monotonic_ns=time.monotonic_ns())
