from __future__ import annotations

from pathlib import Path
import re

from .safe_paths import is_safe_wiki_page_path

SYSTEM_PAGE_NAMES = {"index.md", "log.md", "SCHEMA.md"}
SYSTEM_CATEGORIES = {"system"}
SYSTEM_TYPES = {"index", "log", "system"}
_FRONTMATTER_KEY_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", re.MULTILINE)


def collect_durable_wiki_pages(wiki_root: Path | str) -> list[Path]:
    root = Path(wiki_root)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.md") if is_durable_wiki_page(path, root))


def is_durable_wiki_page(path: Path, wiki_root: Path | str) -> bool:
    root = Path(wiki_root)
    if path.suffix.lower() != ".md":
        return False
    if path.name in SYSTEM_PAGE_NAMES:
        return False
    if not is_safe_wiki_page_path(path, root):
        return False
    fields = frontmatter_fields(path)
    category = _normalize(fields.get("category", ""))
    page_type = _normalize(fields.get("type", ""))
    return category not in SYSTEM_CATEGORIES and page_type not in SYSTEM_TYPES


def frontmatter_fields(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---\n"):
        return {}
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}
    return {match.group(1): match.group(2).strip().strip("'\"") for match in _FRONTMATTER_KEY_PATTERN.finditer(parts[0][4:])}


def _normalize(value: str) -> str:
    return value.strip().lower().replace("_", "-")
