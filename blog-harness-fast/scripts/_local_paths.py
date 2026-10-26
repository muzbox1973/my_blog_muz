"""Constrain package-supplied relative paths to the selected workspace."""
import os
import re
from pathlib import Path, PureWindowsPath


def contained_path(root, relative):
    value = os.fspath(relative)
    win = PureWindowsPath(value)
    normalized = value.replace("\\", "/")
    if (not value or win.drive or win.root or Path(value).is_absolute()
            or ".." in normalized.split("/") or ":" in value):
        raise ValueError(f"Unsafe relative path: {value!r}")
    base = Path(root).resolve()
    target = (base / normalized).resolve()
    if target == base or not target.is_relative_to(base):
        raise ValueError(f"Path escapes the selected folder: {value!r}")
    return str(target)


def image_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError(f"Unsafe image id: {value!r}")
    if value.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise ValueError(f"Reserved Windows filename: {value!r}")
    return value
