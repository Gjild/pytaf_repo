from __future__ import annotations

import os
from pathlib import Path


def is_cloudy_path(path: Path) -> bool:
    s = str(path).lower()
    return any(x in s for x in ("onedrive", "dropbox", "google drive", "googledrive", "icloud"))

def ensure_local_results_root(path: Path) -> tuple[Path, bool, Path, bool]:
    """
    Returns: (resolved_root, relocated_because_cloud, relocation_target, cloud_path_detected)
    """
    p = path
    relocated = False
    relto = Path()
    cloud = is_cloudy_path(p)
    if os.name == "nt":
        if cloud:
            relto = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "PyTAF" / "cache"
            relto.mkdir(parents=True, exist_ok=True)
            p = relto
            relocated = True
    else:
        if cloud:
            relto = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "pytaf"
            relto.mkdir(parents=True, exist_ok=True)
            p = relto
            relocated = True
    p.mkdir(parents=True, exist_ok=True)
    return p, relocated, relto, cloud
