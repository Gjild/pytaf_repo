from __future__ import annotations
import ctypes as c
import ctypes.wintypes as w

CREATE_NEW_PROCESS_GROUP  = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9

class JOBOBJECT_BASIC_LIMIT_INFORMATION(c.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", w.LARGE_INTEGER),
        ("PerJobUserTimeLimit", w.LARGE_INTEGER),
        ("LimitFlags", w.DWORD),
        ("MinimumWorkingSetSize", w.SIZE_T),
        ("MaximumWorkingSetSize", w.SIZE_T),
        ("ActiveProcessLimit", w.DWORD),
        ("Affinity", w.ULONG_PTR),
        ("PriorityClass", w.DWORD),
        ("SchedulingClass", w.DWORD),
    ]

class IO_COUNTERS(c.Structure):
    _fields_ = [("ReadOperationCount", w.ULONGLONG),
                ("WriteOperationCount", w.ULONGLONG),
                ("OtherOperationCount", w.ULONGLONG),
                ("ReadTransferCount", w.ULONGLONG),
                ("WriteTransferCount", w.ULONGLONG),
                ("OtherTransferCount", w.ULONGLONG)]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(c.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", w.SIZE_T),
        ("JobMemoryLimit", w.SIZE_T),
        ("PeakProcessMemoryUsed", w.SIZE_T),
        ("PeakJobMemoryUsed", w.SIZE_T),
    ]

kernel32 = c.WinDLL("kernel32", use_last_error=True)

def create_kill_on_close_job():
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObjectW failed")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                            c.byref(info), c.sizeof(info)):
        raise OSError("SetInformationJobObject failed")
    return job

def assign_process(job, process_handle):
    if not kernel32.AssignProcessToJobObject(job, process_handle):
        raise OSError("AssignProcessToJobObject failed")

def terminate_job(job, code: int = 1):
    kernel32.TerminateJobObject(job, code)

def close_handle(handle) -> None:
    try:
        kernel32.CloseHandle(handle)
    except Exception:
        pass
