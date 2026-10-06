"""Helpers for paths *as Sonarr/Radarr see them*.

These paths belong to the machine running Sonarr/Radarr, not to the machine
running this MCP server: a Linux container (``/downloads/x``), a Windows
install (``D:\\Downloads\\x``) or a UNC share (``\\\\nas\\media\\x``). So
``pathlib``/``os.path`` (which follow the local OS) are deliberately not used.
"""

from __future__ import annotations

import re

_WINDOWS = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def is_windows_path(path: str) -> bool:
    return bool(_WINDOWS.match(path))


def normalize(path: str) -> str:
    """Comparable form: forward slashes, no trailing slash, case-folded on Windows."""
    if not path:
        return ""
    windows = is_windows_path(path)
    p = path.replace("\\", "/")
    p = re.sub(r"(?<!^)/{2,}", "/", p)
    if len(p) > 1 and not re.fullmatch(r"[A-Za-z]:/", p):
        p = p.rstrip("/")
    return p.casefold() if windows else p


def same(a: str, b: str) -> bool:
    return normalize(a) == normalize(b)


def is_within(path: str, folder: str) -> bool:
    """True if ``path`` is ``folder`` or inside it."""
    p, f = normalize(path), normalize(folder)
    if not p or not f:
        return False
    return p == f or p.startswith(f if f.endswith("/") else f + "/")


def parent(path: str) -> str:
    """Parent folder, keeping the original separator style."""
    stripped = path.rstrip("/\\")
    idx = max(stripped.rfind("/"), stripped.rfind("\\"))
    if idx <= 0:
        return stripped[:1] if idx == 0 else stripped
    head = stripped[:idx]
    if re.fullmatch(r"[A-Za-z]:", head):  # keep "C:\" instead of "C:"
        return head + stripped[idx]
    return head


def basename(path: str) -> str:
    stripped = path.rstrip("/\\")
    return re.split(r"[\\/]", stripped)[-1] if stripped else ""
