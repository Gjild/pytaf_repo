from __future__ import annotations

from contextlib import ExitStack
from csv import DictWriter
import os
from pathlib import Path

from .win_durability import flush_dir_anchor_if_windows


class CsvDual:
    """
    Two CSV writers kept open for the life of the object.
    Using ExitStack to manage their lifetime cleanly; open() calls are
    intentionally persistent and annotated to silence SIM115.
    """
    def __init__(self, root: Path):
        export = root / "export"
        export.mkdir(exist_ok=True)
        self._stack = ExitStack()
        self._excel = self._stack.enter_context(  
            open(export / "data.excel.csv", "w", newline="", encoding="utf-8") # noqa: SIM115
        )
        self._raw = self._stack.enter_context(  
            open(export / "data.raw.csv", "w", newline="", encoding="utf-8") # noqa: SIM115
        )
        headers = ["name", "value", "unit", "timestamp"]
        self._excel_w = DictWriter(self._excel, fieldnames=headers)
        self._raw_w = DictWriter(self._raw, fieldnames=headers)
        self._excel_w.writeheader()
        self._raw_w.writeheader()
        self._export_dir = export

    def row(self, name: str, value: float, unit: str, ts: str) -> None:
        r = {"name": name, "value": value, "unit": unit, "timestamp": ts}
        self._excel_w.writerow(r)
        self._raw_w.writerow(r)

    def close(self) -> None:
        # fsync both, then close via ExitStack
        for f in (self._excel, self._raw):
            f.flush()
            os.fsync(f.fileno())
        self._stack.close()
        flush_dir_anchor_if_windows(self._export_dir)
