from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


class Transport(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def transact(self, tx: bytes, *, budgets: Budgets) -> bytes: ...
    @property
    def resource(self) -> str: ...
    @property
    def backend(self) -> str: ...
    @property
    def diag(self) -> TransportDiag: ...


@dataclass
class Budgets:
    write_ms: int
    complete_ms: int
    read_ms: int
    total_ms: int


@dataclass
class TransportDiag:
    bytes_tx: int = 0
    bytes_rx: int = 0
    last_timeout_phase: Literal["write", "complete", "read"] | None = None
    reconnects: int = 0
    zero_len_read_events: int = 0
    zero_len_backoffs: int = 0
    paced_writes: int = 0
    last_diag_query_ok: bool | None = None
