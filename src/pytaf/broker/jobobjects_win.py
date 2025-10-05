from __future__ import annotations

from contextlib import suppress
import ctypes as c
import ctypes.wintypes as w
from typing import Any

CREATE_NEW_PROCESS_GROUP = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9


class JOBOBJECT_BASIC_LIMIT_INFORMATION(c.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", w.LARGE_INTEGER),
        ("PerJobUserTimeLimit", w.LARGE_INTEGER),
        ("LimitFlags", w.DWORD),
        ("MinimumWorkingSetSize", w.SIZE_T), # type: ignore[attr-defined]
        ("MaximumWorkingSetSize", w.SIZE_T), # type: ignore[attr-defined]
        ("ActiveProcessLimit", w.DWORD),
        ("Affinity", w.ULONG_PTR), # type: ignore[attr-defined]
        ("PriorityClass", w.DWORD),
        ("SchedulingClass", w.DWORD),
    ]


class IO_COUNTERS(c.Structure):
    _fields_ = [
        ("ReadOperationCount", w.ULONGLONG), # type: ignore[attr-defined]
        ("WriteOperationCount", w.ULONGLONG), # type: ignore[attr-defined]
        ("OtherOperationCount", w.ULONGLONG), # type: ignore[attr-defined]
        ("ReadTransferCount", w.ULONGLONG), # type: ignore[attr-defined]
        ("WriteTransferCount", w.ULONGLONG), # type: ignore[attr-defined]
        ("OtherTransferCount", w.ULONGLONG), # type: ignore[attr-defined]
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(c.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", w.SIZE_T), # type: ignore[attr-defined]
        ("JobMemoryLimit", w.SIZE_T), # type: ignore[attr-defined]
        ("PeakProcessMemoryUsed", w.SIZE_T), # type: ignore[attr-defined]
        ("PeakJobMemoryUsed", w.SIZE_T), # type: ignore[attr-defined]
    ]


kernel32 = c.WinDLL("kernel32", use_last_error=True) # type: ignore[attr-defined]


def create_kill_on_close_job() -> Any:
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObjectW failed")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, JobObjectExtendedLimitInformation, c.byref(info), c.sizeof(info)):
        raise OSError("SetInformationJobObject failed")
    return job


def assign_process(job: Any, process_handle: Any) -> None:
    if not kernel32.AssignProcessToJobObject(job, process_handle):
        raise OSError("AssignProcessToJobObject failed")


def terminate_job(job: Any, code: int = 1) -> None:
    kernel32.TerminateJobObject(job, code)


def close_handle(handle: Any) -> None:
    with suppress(Exception):
        kernel32.CloseHandle(handle)