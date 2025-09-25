from __future__ import annotations

from dataclasses import dataclass, field
from queue import Empty, PriorityQueue
from typing import Any, Literal

Lane = Literal["control", "bulk"]


@dataclass(order=True)
class _Item:
    priority: int
    seq: int
    op: dict[str, Any] = field(compare=False)


class DualLaneQueue:
    def __init__(self) -> None:
        self._q: PriorityQueue[_Item] = PriorityQueue()
        self._seq: int = 0

    def put(self, lane: Lane, op: dict[str, Any]) -> None:
        prio = 0 if lane == "control" else 10
        self._seq += 1
        self._q.put(_Item(priority=prio, seq=self._seq, op=op))

    def get_nowait_or_none(self) -> dict[str, Any] | None:
        try:
            item: _Item = self._q.get_nowait()
            return item.op
        except Empty:
            return None

    def empty(self) -> bool:
        return self._q.empty()
