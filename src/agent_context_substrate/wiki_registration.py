from __future__ import annotations

from datetime import date
from pathlib import Path

from .paths import HarnessPaths


def upsert_index_entry(index_path: Path, section_heading: str, entry_line: str) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not index_path.exists():
        index_path.write_text("# Wiki Index\n", encoding="utf-8")
    lines = index_path.read_text(encoding="utf-8").splitlines()
    if entry_line in lines:
        return

    section_line = f"## {section_heading}"
    try:
        section_index = lines.index(section_line)
    except ValueError:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend([section_line, entry_line])
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    section_end = section_index + 1
    while section_end < len(lines) and not lines[section_end].startswith("## "):
        section_end += 1

    empty_marker = "<!-- empty -->"
    if empty_marker in lines[section_index + 1:section_end]:
        empty_index = lines.index(empty_marker, section_index + 1, section_end)
        lines[empty_index] = entry_line
        while empty_index + 1 < len(lines) and lines[empty_index + 1] == "":
            del lines[empty_index + 1]
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    lines.insert(section_end, entry_line)
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_log_entry(log_path: Path, heading: str, bullet_lines: list[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Wiki Log\n"
    if existing and not existing.endswith("\n"):
        existing += "\n"
    entry = "\n".join([heading, *bullet_lines]) + "\n"
    log_path.write_text(existing + ("\n" if existing.strip() else "") + entry, encoding="utf-8")


def register_promoted_page(
    *,
    paths: HarnessPaths,
    section_heading: str,
    slug: str,
    summary: str,
    output_path: Path,
    command_name: str,
    extra_lines: list[str] | None = None,
) -> None:
    upsert_index_entry(
        paths.wiki_root / "index.md",
        section_heading,
        f"- [[{slug}]] — {summary}",
    )
    bullet_lines = [f"- Created/updated: `{output_path.relative_to(paths.wiki_root).as_posix()}`"]
    bullet_lines.extend(list(extra_lines or []))
    append_log_entry(
        paths.wiki_root / "log.md",
        f"## [{date.today().isoformat()}] {command_name} | {slug}",
        bullet_lines,
    )
