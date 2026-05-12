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


def is_safe_project_artifact_path(path: Path, project_root: Path, *relative_root_parts: str) -> bool:
    """Return True when an artifact path resolves under an allowed project subdirectory."""

    if not relative_root_parts:
        return False
    project_root_resolved = Path(project_root).resolve()
    allowed_root = (Path(project_root) / Path(*relative_root_parts)).resolve()
    try:
        allowed_root.relative_to(project_root_resolved)
        resolved_path = Path(path).resolve()
        resolved_path.relative_to(project_root_resolved)
        resolved_path.relative_to(allowed_root)
    except ValueError:
        return False
    return True


def is_safe_wiki_page_path(path: Path, wiki_root: Path) -> bool:
    """Return True when a wiki page is readable and stays inside the human wiki boundary."""

    candidate = Path(path)
    if candidate.suffix != ".md":
        return False
    try:
        root = Path(wiki_root).resolve()
        resolved = candidate.resolve()
        parts = resolved.relative_to(root).parts
    except (OSError, ValueError):
        return False
    if not parts:
        return False
    return not any(part.startswith(".") for part in parts) and parts[0] not in {"_system", "90 보관"}


def safe_wiki_target_path(*, wiki_root: Path, target: str) -> Path | None:
    """Resolve a reviewable wiki patch target or return None when unsafe."""

    target_path = Path(target)
    if target_path.is_absolute() or ".." in target_path.parts:
        return None
    root = Path(wiki_root).resolve()
    resolved = (root / target_path).resolve()
    if not is_safe_wiki_page_path(resolved, root):
        return None
    return resolved
