from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.paths import HarnessPaths  # noqa: E402
from agent_context_substrate.wiki_registration import register_promoted_page  # noqa: E402


def test_register_promoted_page_updates_index_and_log(tmp_path: Path) -> None:
    wiki_root = tmp_path / "wiki"
    paths = HarnessPaths(project_root=tmp_path / "project", wiki_root=wiki_root)
    output_path = wiki_root / "concepts" / "retrieval.md"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("# Retrieval\n", encoding="utf-8")
    (wiki_root / "index.md").write_text("# Wiki Index\n\n## Concepts\n<!-- empty -->\n", encoding="utf-8")

    register_promoted_page(
        paths=paths,
        section_heading="Concepts",
        slug="retrieval",
        summary="Search grounding",
        output_path=output_path,
        command_name="promote-unit-concept",
        extra_lines=["- Source: `packet-1`"],
    )

    assert (wiki_root / "index.md").read_text(encoding="utf-8") == (
        "# Wiki Index\n\n## Concepts\n- [[retrieval]] — Search grounding\n"
    )
    log_text = (wiki_root / "log.md").read_text(encoding="utf-8")
    assert "promote-unit-concept | retrieval" in log_text
    assert "- Created/updated: `concepts/retrieval.md`" in log_text
    assert "- Source: `packet-1`" in log_text
