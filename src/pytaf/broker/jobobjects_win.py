from __future__ import annotations

from contextlib import suppress
import ctypes as c
import ctypes.wintypes as w
from typing import Any

# Constants
CREATE_NEW_PROCESS_GROUP: int = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: int = 0x00002000
JobObjectExtendedLimitInformation: int = 9

# Fallback ctypes aliases to satisfy mypy stubs cross-platform
SIZE_T = c.c_size_t
ULONG_PTR = c.c_size_t
ULONGLONG = c.c_ulonglong

class JOBOBJECT_BASIC_LIMIT_INFORMATION(c.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", w.LARGE_INTEGER),
        ("PerJobUserTimeLimit", w.LARGE_INTEGER),
        ("LimitFlags", w.DWORD),
        ("MinimumWorkingSetSize", SIZE_T),
        ("MaximumWorkingSetSize", SIZE_T),
        ("ActiveProcessLimit", w.DWORD),
        ("Affinity", ULONG_PTR),
        ("PriorityClass", w.DWORD),
        ("SchedulingClass", w.DWORD),
    ]

class IO_COUNTERS(c.Structure):
    _fields_ = [
        ("ReadOperationCount", ULONGLONG),
        ("WriteOperationCount", ULONGLONG),
        ("OtherOperationCount", ULONGLONG),
        ("ReadTransferCount", ULONGLONG),
        ("WriteTransferCount", ULONGLONG),
        ("OtherTransferCount", ULONGLONG),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(c.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", SIZE_T),
        ("JobMemoryLimit", SIZE_T),
        ("PeakProcessMemoryUsed", SIZE_T),
        ("PeakJobMemoryUsed", SIZE_T),
    ]

# Use Any to avoid missing attribute errors in type stubs
kernel32: Any = c.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

def create_kill_on_close_job() -> Any:
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObjectW failed")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        job,
        JobObjectExtendedLimitInformation,
        c.byref(info),
        c.sizeof(info),
    )
    if not ok:
        raise OSError("SetInformationJobObject failed")
    return job

def assign_process(job: Any, process_handle: int) -> None:
    ok = kernel32.AssignProcessToJobObject(job, process_handle)
    if not ok:
        raise OSError("AssignProcessToJobObject failed")

def terminate_job(job: Any, code: int = 1) -> None:
    kernel32.TerminateJobObject(job, code)

def close_handle(handle: Any) -> None:
    with suppress(Exception):
        kernel32.CloseHandle(handle)
