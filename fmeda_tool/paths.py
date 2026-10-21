"""Bundled read-only resources and persistent, writable application directories."""
import os
from pathlib import Path
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def data_directory() -> Path:
    override = os.environ.get("FMEDA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return local / "FMEDA Tool"
    return resource_path("data")


def projects_directory() -> Path:
    return data_directory() / "projects"


def logs_directory() -> Path:
    if is_frozen() or os.environ.get("FMEDA_DATA_DIR"):
        return data_directory() / "logs"
    return resource_path("logs")
