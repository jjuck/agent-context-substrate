from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..paths import HarnessPaths

ExportWikiPatchProposal = Callable[..., tuple[Path, Path, Any]]
ApplyWikiPatchFile = Callable[..., Any]
RenderListing = Callable[..., str]


def handle_plan_wiki_patches_command(
    *, args: Any, paths: HarnessPaths, export_wiki_patch_proposal: ExportWikiPatchProposal
) -> int:
    patch_json_path, patch_markdown_path, _proposal = export_wiki_patch_proposal(
        promotion_file=Path(args.promotion_file).expanduser(),
        paths=paths,
        wiki_root=Path(args.wiki_root).expanduser() if args.wiki_root else None,
        write_mode=args.write_mode,
    )
    print(patch_json_path)
    print(patch_markdown_path)
    return 0


def handle_apply_wiki_patch_command(*, args: Any, paths: HarnessPaths, apply_wiki_patch_file: ApplyWikiPatchFile) -> int:
    result = apply_wiki_patch_file(
        patch_file=Path(args.patch_file).expanduser(),
        paths=paths,
        wiki_root=Path(args.wiki_root).expanduser() if args.wiki_root else None,
        dry_run=not args.apply,
    )
    print(
        " ".join(
            [
                f"dry_run={result.dry_run}",
                f"planned={len(result.planned_patch_ids)}",
                f"applied={len(result.applied_patch_ids)}",
                f"skipped={len(result.skipped_patch_ids)}",
            ]
        )
    )
    return 0


def handle_list_promotions_command(*, args: Any, paths: HarnessPaths, render_promotions_listing: RenderListing) -> int:
    print(render_promotions_listing(paths=paths, status=args.status))
    return 0


def handle_list_wiki_patches_command(*, args: Any, paths: HarnessPaths, render_wiki_patches_listing: RenderListing) -> int:
    print(render_wiki_patches_listing(paths=paths, status=args.status))
    return 0
