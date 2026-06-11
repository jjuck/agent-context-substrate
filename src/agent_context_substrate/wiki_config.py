from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

DEFAULT_WIKI_LANGUAGE = "ko"
DEFAULT_SUPPORTED_LANGUAGES = ("ko", "en")
DEFAULT_FALLBACK_FOLDER = "01 지식"
PLACEMENT_POLICY_EMERGENT_ROOT = "emergent-root"
PLACEMENT_POLICY_REGISTRY_FOLDER = "registry-folder"
UNSORTED_REVIEW_SECTION = "Unsorted / Review Needed"
UNCLASSIFIED_REVIEW_SECTION = "Unclassified / Review Needed"


@dataclass(frozen=True)
class WikiCategoryRule:
    category: str
    folder: str
    page_type: str
    template: str
    index_section: str


@dataclass(frozen=True)
class WikiConfig:
    default_language: str
    supported_languages: tuple[str, ...]
    filename_language: str
    template_language: str
    source_language_preserve: bool
    placement_policy: str
    category_registry: dict[str, WikiCategoryRule]
    strict_category_registry: bool = False

    def rule_for_category(self, category: str) -> WikiCategoryRule | None:
        return self.category_registry.get(normalize_category(category))

    def index_section_for_category(self, category: str | None) -> str:
        normalized = normalize_category(category)
        if not normalized:
            return UNCLASSIFIED_REVIEW_SECTION
        rule = self.rule_for_category(normalized)
        return rule.index_section if rule is not None else _title_from_category(normalized)

    def durable_folders(self) -> tuple[str, ...]:
        if self.placement_policy != PLACEMENT_POLICY_REGISTRY_FOLDER:
            return ()
        folders = [rule.folder for rule in self.category_registry.values()]
        folders.append(DEFAULT_FALLBACK_FOLDER)
        return tuple(_dedupe(folders))

    def should_report_unregistered_categories(self) -> bool:
        return self.placement_policy == PLACEMENT_POLICY_REGISTRY_FOLDER or self.strict_category_registry


def default_category_registry() -> dict[str, WikiCategoryRule]:
    rules = [
        WikiCategoryRule("abstraction", DEFAULT_FALLBACK_FOLDER, "knowledge", "knowledge", "Abstractions"),
        WikiCategoryRule("knowledge", DEFAULT_FALLBACK_FOLDER, "knowledge", "knowledge", "Knowledge"),
        WikiCategoryRule("project", "04 프로젝트", "project", "project", "Projects"),
        WikiCategoryRule("source", "06 원천 자료", "source", "source", "Sources"),
        WikiCategoryRule("plan", "05 계획", "plan", "plan", "Plans"),
        WikiCategoryRule("decision", DEFAULT_FALLBACK_FOLDER, "decision", "decision", "Decisions"),
    ]
    return {rule.category: rule for rule in rules}


def default_wiki_config() -> WikiConfig:
    return WikiConfig(
        default_language=DEFAULT_WIKI_LANGUAGE,
        supported_languages=DEFAULT_SUPPORTED_LANGUAGES,
        filename_language=DEFAULT_WIKI_LANGUAGE,
        template_language=DEFAULT_WIKI_LANGUAGE,
        source_language_preserve=True,
        placement_policy=PLACEMENT_POLICY_EMERGENT_ROOT,
        category_registry={},
        strict_category_registry=False,
    )


def load_wiki_config(wiki_root: Path | str) -> WikiConfig:
    config = default_wiki_config()
    config_path = Path(wiki_root) / "_system" / "config.yaml"
    if not config_path.exists():
        return config
    parsed = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    wiki = parsed.get("wiki", {})
    if not isinstance(wiki, dict):
        return config

    supported = _as_string_tuple(wiki.get("supported_languages")) or config.supported_languages
    default_language = _supported_language(str(wiki.get("default_language") or config.default_language), supported)
    filename_language = _supported_language(str(wiki.get("filename_language") or default_language), supported)
    template_language = _supported_language(str(wiki.get("template_language") or default_language), supported)
    source_language_preserve = _as_bool(wiki.get("source_language_preserve"), default=True)
    placement_policy = _placement_policy(str(wiki.get("placement_policy") or config.placement_policy))
    strict_category_registry = _as_bool(
        wiki.get("strict_category_registry", wiki.get("category_registry_strict")),
        default=False,
    )
    registry = _category_registry_from_config(wiki.get("category_registry"), defaults={})
    return WikiConfig(
        default_language=default_language,
        supported_languages=supported,
        filename_language=filename_language,
        template_language=template_language,
        source_language_preserve=source_language_preserve,
        placement_policy=placement_policy,
        category_registry=registry,
        strict_category_registry=strict_category_registry,
    )


def normalize_category(value: str | None) -> str:
    text = (value or "").strip().lower()
    return re.sub(r"\s+", "-", text) if text else ""


def _category_registry_from_config(
    value: object,
    *,
    defaults: dict[str, WikiCategoryRule],
) -> dict[str, WikiCategoryRule]:
    registry = dict(defaults)
    if not isinstance(value, dict):
        return registry
    for raw_category, raw_rule in value.items():
        category = normalize_category(str(raw_category))
        if not category or not isinstance(raw_rule, dict):
            continue
        folder = str(raw_rule.get("folder") or DEFAULT_FALLBACK_FOLDER).strip()
        page_type = str(raw_rule.get("page_type") or raw_rule.get("type") or "knowledge").strip()
        template = str(raw_rule.get("template") or page_type).strip()
        index_section = str(raw_rule.get("index_section") or _title_from_category(category)).strip()
        registry[category] = WikiCategoryRule(
            category=category,
            folder=folder or DEFAULT_FALLBACK_FOLDER,
            page_type=page_type or "knowledge",
            template=template or page_type or "knowledge",
            index_section=index_section or _title_from_category(category),
        )
    return registry


def _parse_simple_yaml(text: str) -> dict[str, object]:
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-1, root)]
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value:
            parent[key] = _parse_scalar(raw_value)
            continue
        child: dict[str, object] = {}
        parent[key] = child
        stack.append((indent, child))
    return root


def _parse_scalar(value: str) -> object:
    value = value.strip().strip("'\"")
    if value.startswith("[") and value.endswith("]"):
        return tuple(item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip())
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    return value


def _as_string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "on"}
    return default


def _supported_language(value: str, supported: tuple[str, ...]) -> str:
    normalized = value.strip().lower()
    return normalized if normalized in supported else DEFAULT_WIKI_LANGUAGE


def _placement_policy(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == PLACEMENT_POLICY_REGISTRY_FOLDER:
        return PLACEMENT_POLICY_REGISTRY_FOLDER
    return PLACEMENT_POLICY_EMERGENT_ROOT


def _title_from_category(category: str) -> str:
    return category.replace("-", " ").replace("_", " ").title()


def _dedupe(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
