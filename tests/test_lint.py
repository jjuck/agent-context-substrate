from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.lint import (  # noqa: E402
    export_lint_report,
    lint_wiki,
)
from agent_context_substrate.paths import HarnessPaths  # noqa: E402


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_lint_wiki_detects_missing_provenance_orphans_broken_links_and_index_gaps(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    _write(
        wiki_root / "SCHEMA.md",
        """# Wiki Schema

## Tag Taxonomy
- question
- note
- architecture
- implementation
""",
    )
    _write(
        wiki_root / "index.md",
        """# Wiki Index

## Concepts
- [[page-a]] — Indexed page
- [[page-b]] — Indexed page with missing provenance
""",
    )
    _write(wiki_root / "log.md", "# Wiki Log\n")

    _write(
        wiki_root / "concepts" / "page-a.md",
        """---
title: Page A
created: 2026-04-22
updated: 2026-04-22
type: concept
tags: [note]
sources: [\"raw/articles/a.md\"]
---

# Page A

Links to [[page-b]] and [[missing-page]].
""",
    )
    _write(
        wiki_root / "concepts" / "page-b.md",
        """---
title: Page B
created: 2026-04-22
updated: 2026-04-22
type: concept
tags: [question]
---

# Page B

Links back to [[page-a]].
""",
    )
    _write(
        wiki_root / "queries" / "lonely-query.md",
        """---
title: Lonely Query
created: 2026-04-22
updated: 2026-04-22
type: query
tags: [question]
sources: [\"hermes-session:session-1#messages=1,2\"]
---

# Lonely Query

No inbound durable links yet.
""",
    )

    report = lint_wiki(paths)
    payload = report.to_dict()

    assert payload["checked_pages"] == [
        "concepts/page-a.md",
        "concepts/page-b.md",
        "queries/lonely-query.md",
    ]
    assert payload["missing_provenance_pages"] == ["concepts/page-b.md"]
    assert payload["orphan_pages"] == ["queries/lonely-query.md"]
    assert payload["pages_missing_from_index"] == ["queries/lonely-query.md"]
    assert payload["broken_wikilinks"] == [
        {"source_page": "concepts/page-a.md", "target": "missing-page"}
    ]


def test_lint_wiki_detects_internal_artifact_graph_issues(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Queries\n<!-- empty -->\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")

    packet_dir = project_root / "data" / "exports" / "context_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_payload = {
        "packet_id": "packet-1",
        "task_title": "Broken packet",
        "macro_context": "Test broken graph lint",
        "unit_summaries": [
            {
                "unit_id": "unit-1",
                "session_id": "session-1",
                "title": "Broken unit",
                "goal": "Exercise the internal graph lint",
                "decisions": [],
                "progress": [],
                "open_questions": [],
                "micro_ids": ["micro-a", "micro-missing"],
                "related_pages": [],
                "provenance": None,
            }
        ],
        "micro_summaries": [
            {
                "micro_id": "micro-a",
                "session_id": "session-1",
                "message_ids": [1],
                "summary": "Micro with missing parent unit",
                "why_it_matters": "Important context",
                "artifacts": [],
                "files": [],
                "entities": [],
                "concepts": [],
                "parent_unit_id": None,
                "provenance": None,
            },
            {
                "micro_id": "micro-b",
                "session_id": "session-1",
                "message_ids": [2],
                "summary": "Orphan micro summary",
                "why_it_matters": "Important context",
                "artifacts": [],
                "files": [],
                "entities": [],
                "concepts": [],
                "parent_unit_id": "unit-2",
                "provenance": None,
            },
        ],
        "raw_pointers": [],
        "critical_files": [],
        "open_questions": [],
    }
    _write(packet_dir / "packet-1.json", json.dumps(packet_payload, ensure_ascii=False, indent=2))

    report = lint_wiki(paths)
    payload = report.to_dict()

    assert payload["micro_summaries_missing_parent_unit"] == ["packet-1::micro-a"]
    assert payload["micro_summaries_with_unknown_parent_unit"] == ["packet-1::micro-b -> unit-2"]
    assert payload["unit_summaries_with_missing_micro_references"] == ["packet-1::unit-1 -> micro-missing"]
    assert payload["packet_micro_summaries_unreferenced"] == ["packet-1::micro-b"]
    assert payload["packets_missing_raw_pointers"] == ["packet-1"]



def test_lint_wiki_detects_human_facing_quality_violations(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Concepts\n- [[7]]\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "concepts" / "7.md",
        """---
title: 7번 단계 진행해줘
created: 2026-04-24
updated: 2026-04-24
type: concept
tags: [implementation]
sources: [\"hermes-session:20260424_122938_c308ad#messages=1\"]
---

# 7번 단계 진행해줘

## Summary
Durable concept page derived from session 20260424_122938_c308ad.
""",
    )
    _write(
        wiki_root / "queries" / "20260424_122938_c308ad.md",
        """---
title: 자동 finalize 테스트
created: 2026-04-24
updated: 2026-04-24
type: query
lang: ko
tags: [question]
sources: [\"context-packet:20260424_122938_c308ad\"]
---

# 자동 finalize 테스트

## Summary
Durable query page derived from session 20260424_122938_c308ad.
""",
    )
    _write(
        wiki_root / "plans" / "20260424_122938_c308ad-plan.md",
        """---
title: Session Plan
created: 2026-04-24
updated: 2026-04-24
type: plan
lang: ko
tags: [plan]
sources: [\"context-packet:20260424_122938_c308ad\"]
---

# Session Plan

## Proposed Steps
- [ ] temporary session-derived plan
""",
    )

    payload = lint_wiki(paths).to_dict()

    assert payload["numeric_slug_pages"] == ["concepts/7.md"]
    assert payload["session_id_slug_pages"] == [
        "plans/20260424_122938_c308ad-plan.md",
        "queries/20260424_122938_c308ad.md",
    ]
    assert payload["generated_summary_only_pages"] == [
        "concepts/7.md",
        "queries/20260424_122938_c308ad.md",
    ]
    assert payload["transient_command_title_pages"] == ["concepts/7.md"]
    assert payload["smoke_or_test_pages"] == ["queries/20260424_122938_c308ad.md"]
    assert payload["session_derived_plan_pages"] == ["plans/20260424_122938_c308ad-plan.md"]
    assert payload["missing_lang_pages"] == ["concepts/7.md"]



def test_lint_wiki_enforces_namuwiki_style_content_structure(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n")
    _write(
        wiki_root / "index.md",
        """# Wiki Index

## Knowledge
- [[Thin RAG]] — Too short and missing policy sections
- [[Helpful RAG]] — Structured page
- [[Neighbor A]] — Link target
- [[Neighbor B]] — Link target
""",
    )
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "01 지식" / "Thin RAG.md",
        """---
title: Thin RAG
lang: ko
type: knowledge
category: knowledge
status: active
tags: [rag]
sources: [\"raw/articles/rag.md\"]
---

# Thin RAG

> [!summary]
> RAG 요약.

## 개요

RAG는 검색해서 답하는 방식이다.
""",
    )
    _write(
        wiki_root / "01 지식" / "Helpful RAG.md",
        """---
title: Helpful RAG
lang: ko
type: knowledge
category: knowledge
status: active
tags: [rag]
sources: [\"raw/articles/rag.md\"]
---

# Helpful RAG

> [!summary]
> 검색 증강 생성(RAG, Retrieval-Augmented Generation)은 답변 전에 관련 자료를 찾아 함께 읽는 방식이다.

## 개요

검색 증강 생성(RAG, Retrieval-Augmented Generation)은 모델이 기억에만 의존하지 않고 외부 자료를 먼저 찾아보게 하는 방법이다. 처음 보는 독자는 이를 “시험 전에 참고자료를 펼쳐 보고 답을 쓰는 방식”으로 이해할 수 있다.

## 배경

LLM은 거대 언어 모델(LLM, Large Language Model)을 뜻한다. 이런 모델은 모든 사실을 항상 정확히 기억하지 못한다. 그래서 최신 문서, 프로젝트 기록, 위키 페이지처럼 바깥에 있는 자료를 함께 읽도록 만드는 흐름이 필요해졌다.

## 상세

RAG는 보통 질문을 받으면 관련 문서를 검색하고, 검색된 내용을 짧게 추린 뒤, 그 근거를 바탕으로 답변을 만든다. 이 과정은 답변의 근거를 남기기 쉽다는 장점이 있다.

## 예시

예를 들어 Hermes가 예전 프로젝트 결정을 떠올려야 할 때 [[Neighbor A]] 같은 지식 문서와 [[Neighbor B]] 같은 프로젝트 문서를 먼저 찾아본 뒤 답할 수 있다.

## 한계와 주의점

검색 결과가 부정확하면 답변도 흔들릴 수 있다. 또한 검색된 문서를 그대로 믿지 말고 출처와 작성 시점을 함께 확인해야 한다.

## 관련 문서

- [[Neighbor A]]
- [[Neighbor B]]

## 출처와 근거

- `raw/articles/rag.md`
""",
    )
    for name in ["Neighbor A", "Neighbor B"]:
        _write(
            wiki_root / "01 지식" / f"{name}.md",
            f"""---
title: {name}
lang: ko
type: knowledge
category: knowledge
status: active
tags: []
sources: [\"manual\"]
---

# {name}

> [!summary]
> 연결 대상 문서.

## 개요

연결 대상 문서다.

## 배경

본문 구성 검사에서 보조 문서로만 사용한다.

## 상세

충분한 본문을 제공하기 위해 여러 문장으로 설명한다. 이 문서는 테스트 안에서 링크 대상으로 쓰인다.

## 예시

도움 문서에서 이 문서를 참조한다.

## 한계와 주의점

테스트 보조 문서이므로 실제 지식은 담지 않는다.

## 관련 문서

- [[Helpful RAG]]
- [[Thin RAG]]

## 출처와 근거

- manual
""",
        )

    payload = lint_wiki(paths).to_dict()

    assert payload["missing_required_sections_pages"] == ["01 지식/Thin RAG.md"]
    assert payload["thin_content_pages"] == ["01 지식/Thin RAG.md"]
    assert payload["unexplained_english_terms_pages"] == ["01 지식/Thin RAG.md"]
    assert payload["insufficient_related_links_pages"] == ["01 지식/Thin RAG.md"]
    assert "01 지식/Helpful RAG.md" not in payload["missing_required_sections_pages"]
    assert "01 지식/Helpful RAG.md" not in payload["unexplained_english_terms_pages"]



def test_export_lint_report_writes_json_and_markdown(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    wiki_root = tmp_path / "wiki"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WIKI_PATH", str(wiki_root))
    paths = HarnessPaths(project_root=project_root)

    _write(wiki_root / "SCHEMA.md", "# Wiki Schema\n\n## Tag Taxonomy\n- question\n")
    _write(wiki_root / "index.md", "# Wiki Index\n\n## Queries\n<!-- empty -->\n")
    _write(wiki_root / "log.md", "# Wiki Log\n")
    _write(
        wiki_root / "queries" / "page.md",
        """---
title: Page
created: 2026-04-22
updated: 2026-04-22
type: query
tags: [question]
sources: [\"hermes-session:session-1#messages=1\"]
---

# Page

## Provenance
- `hermes-session:session-1#messages=1`
""",
    )

    packet_dir = project_root / "data" / "exports" / "context_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    _write(
        packet_dir / "packet-1.json",
        json.dumps(
            {
                "packet_id": "packet-1",
                "task_title": "Packet without raw pointers",
                "macro_context": "Test report export",
                "unit_summaries": [],
                "micro_summaries": [],
                "raw_pointers": [],
                "critical_files": [],
                "open_questions": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    report = lint_wiki(paths)
    json_path, markdown_path = export_lint_report(report=report, paths=paths, report_id="smoke-lint")

    assert json_path == project_root / "data" / "exports" / "lint" / "smoke-lint.json"
    assert markdown_path == project_root / "data" / "exports" / "lint" / "smoke-lint.md"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["pages_missing_from_index"] == ["queries/page.md"]
    assert payload["orphan_pages"] == ["queries/page.md"]
    assert payload["packets_missing_raw_pointers"] == ["packet-1"]

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Wiki Lint Report" in markdown
    assert "Checked pages: **1**" in markdown
    assert "## Missing Provenance" in markdown
    assert "## Orphan Pages" in markdown
    assert "## Internal Artifact Graph" in markdown
    assert "packet-1" in markdown
    assert "queries/page.md" in markdown
