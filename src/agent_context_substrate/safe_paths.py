from __future__ import annotations

from pathlib import Path
import re

_SAFE_STEM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def safe_artifact_stem(value: str, *, label: str = "artifact id") -> str:
    """Return a conservative filename stem or raise ValueError.

    Artifact identifiers often originate from session ids, packet ids, or CLI
    report ids. Treat them as untrusted before joining with output directories:
    reject absolute paths, path separators, parent traversal, empty values, and
    shell/metacharacter-heavy strings.
    """

    stem = str(value).strip()
    path = Path(stem)
    if (
        not stem
        or path.is_absolute()
        or ".." in path.parts
        or "/" in stem
        or "\\" in stem
        or not _SAFE_STEM_PATTERN.fullmatch(stem)
    ):
        raise ValueError(f"Unsafe {label}: {value!r}")
    return stem


def safe_child_path(directory: Path, stem: str, suffix: str, *, label: str = "artifact id") -> Path:
    safe_stem = safe_artifact_stem(stem, label=label)
    base = Path(directory)
    path = base / f"{safe_stem}{suffix}"
    resolved_base = base.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Unsafe {label}: {stem!r}") from exc
    return path
