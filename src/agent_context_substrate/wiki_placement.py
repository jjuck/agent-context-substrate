from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .promotions import PromotionCandidate
from .safe_paths import safe_wiki_target_path
from .wiki_config import (
    DEFAULT_FALLBACK_FOLDER,
    PLACEMENT_POLICY_REGISTRY_FOLDER,
    UNSORTED_REVIEW_SECTION,
    WikiConfig,
    load_wiki_config,
    normalize_category,
)


@dataclass(frozen=True)
class WikiPlacement:
    target: str
    title: str
    category: str
    page_type: str
    language: str
    registered: bool
    fallback: bool
    index_section: str
    placement_reason: str

    def to_metadata(self) -> dict[str, object]:
        return {
            "target": self.target,
            "title": self.title,
            "category": self.category,
            "page_type": self.page_type,
            "language": self.language,
            "registered": self.registered,
            "fallback": self.fallback,
            "index_section": self.index_section,
            "placement_reason": self.placement_reason,
        }


def resolve_wiki_placement(
    *,
    candidate: PromotionCandidate,
    wiki_root: Path,
    config: WikiConfig | None = None,
) -> WikiPlacement:
    config = config or load_wiki_config(wiki_root)
    raw_target = candidate.target_page.strip()
    if _is_explicit_markdown_target(raw_target):
        target = _normalize_explicit_target(raw_target)
        title = _title_from_target(target)
        category = normalize_category(candidate.category)
        page_type = _page_type_for_candidate(candidate, config, category)
        language = _language_for_candidate(candidate, config)
        registered = bool(category and config.rule_for_category(category) is not None)
        return WikiPlacement(
            target=target,
            title=title,
            category=category,
            page_type=page_type,
            language=language,
            registered=registered,
            fallback=False,
            index_section=config.index_section_for_category(category),
            placement_reason=candidate.placement_reason or "Explicit Markdown target supplied by promotion candidate.",
        )

    category = normalize_category(candidate.category)
    rule = config.rule_for_category(category)
    registered = bool(category and rule is not None)
    title = _display_title(raw_target or "untriaged")
    filename = _safe_markdown_filename(raw_target or title)
    fallback = False
    if config.placement_policy == PLACEMENT_POLICY_REGISTRY_FOLDER:
        fallback = not registered
        folder = rule.folder if rule is not None else DEFAULT_FALLBACK_FOLDER
        target = f"{folder}/{filename}.md"
    else:
        target = f"{filename}.md"
    page_type = _page_type_for_candidate(candidate, config, category)
    language = _language_for_candidate(candidate, config)
    placement_reason = candidate.placement_reason or (
        "Category is registered in wiki config."
        if config.placement_policy == PLACEMENT_POLICY_REGISTRY_FOLDER and registered
        else (
            f"Unregistered category {category!r} fell back to {DEFAULT_FALLBACK_FOLDER}/ without blocking write."
            if config.placement_policy == PLACEMENT_POLICY_REGISTRY_FOLDER and category
            else "Emergent root placement; folder paths are storage, metadata and links carry meaning."
        )
    )
    return WikiPlacement(
        target=target,
        title=title,
        category=category,
        page_type=page_type,
        language=language,
        registered=registered,
        fallback=fallback,
        index_section=config.index_section_for_category(category),
        placement_reason=placement_reason,
    )


def safe_resolved_wiki_placement(
    *,
    candidate: PromotionCandidate,
    wiki_root: Path,
    config: WikiConfig | None = None,
) -> tuple[WikiPlacement, Path] | None:
    placement = resolve_wiki_placement(candidate=candidate, wiki_root=wiki_root, config=config)
    target_path = safe_wiki_target_path(wiki_root=wiki_root, target=placement.target)
    if target_path is not None:
        return placement, target_path
    review_placement = WikiPlacement(
        target="_review/untriaged.md",
        title="untriaged",
        category=placement.category,
        page_type=placement.page_type,
        language=placement.language,
        registered=placement.registered,
        fallback=True,
        index_section=UNSORTED_REVIEW_SECTION,
        placement_reason=f"Unsafe target {placement.target!r} was redirected to review.",
    )
    review_path = safe_wiki_target_path(wiki_root=wiki_root, target=review_placement.target)
    if review_path is None:
        return None
    return review_placement, review_path


def _is_explicit_markdown_target(target: str) -> bool:
    return bool(target) and (target.endswith(".md") or "/" in target or "\\" in target)


def _normalize_explicit_target(target: str) -> str:
    return target.strip().replace("\\", "/")


def _title_from_target(target: str) -> str:
    return Path(target).stem.replace("-", " ").title()


def _display_title(value: str) -> str:
    cleaned = value.strip()
    if cleaned and cleaned == cleaned.lower() and re.fullmatch(r"[a-z0-9_. -]+", cleaned):
        return cleaned.replace("-", " ").replace("_", " ").title()
    return cleaned


def _safe_markdown_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"\\|?*\x00-\x1f]', "", title).strip()
    cleaned = cleaned.replace("/", " ").replace("\\", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:120] or "untitled"


def _page_type_for_candidate(candidate: PromotionCandidate, config: WikiConfig, category: str) -> str:
    proposed = (candidate.page_type or "").strip()
    if proposed:
        return proposed
    rule = config.rule_for_category(category)
    return rule.page_type if rule is not None else "knowledge"


def _language_for_candidate(candidate: PromotionCandidate, config: WikiConfig) -> str:
    proposed = (candidate.language or "").strip().lower()
    if proposed in config.supported_languages:
        return proposed
    return config.default_language
