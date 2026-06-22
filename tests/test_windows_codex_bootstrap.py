from __future__ import annotations

from pathlib import Path


def test_windows_codex_bootstrap_script_documents_single_command_flow() -> None:
    script_path = Path("scripts/setup-codex-windows.ps1")

    script = script_path.read_text(encoding="utf-8")

    assert "setup-codex" in script
    assert "--yes" in script
    assert "-CheckOnly" in script
    assert "-InstallMissingTools" in script
    assert "-InstallObsidian" in script
    assert "Git.Git" in script
    assert "Python.Python.3.13" in script
    assert "Obsidian.Obsidian" in script
    assert "OpenAI\\Codex\\bin" in script
    assert "npm shim" in script
    assert "codex plugin add" in script
    assert "agent-context-substrate@personal" in script
    assert "codex_plugin_registered" in script
    assert "allowed_workspace_roots" in script
    assert "%USERPROFILE%\\Documents\\Codex" in script
    assert "Codex app -> Settings -> Hooks" in script
    assert "CLI /hooks is the alternate" in script
    assert "--user-hook-fallback" not in script
    assert "--dangerously-bypass-hook-trust" not in script


def test_windows_codex_bootstrap_does_not_force_default_absolute_wiki_root() -> None:
    script = Path("scripts/setup-codex-windows.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $env:USERPROFILE "Documents\\LLM Wiki"' not in script
    assert 'if ($WikiRootExplicit) {' in script
    assert '$SetupArgs += @("--wiki-root", $WikiRoot)' in script


def test_windows_codex_docs_explain_one_shot_and_diagnostic_commands() -> None:
    docs = "\n".join(
        [
            Path("README.ko.md").read_text(encoding="utf-8"),
            Path("README.md").read_text(encoding="utf-8"),
            Path("docs/WINDOWS_CODEX_APP_SETUP.ko.md").read_text(encoding="utf-8"),
            Path("docs/WINDOWS_CODEX_APP_SETUP.md").read_text(encoding="utf-8"),
        ]
    )

    for required in [
        "scripts/setup-codex-windows.ps1",
        "setup-codex",
        "setup-codex-wizard",
        "doctor-codex",
        "diagnose-codex",
        "config-codex",
        "Python.Python.3.13",
        "Git.Git",
        "Obsidian.Obsidian",
        "npm shim",
        "%LOCALAPPDATA%\\OpenAI\\Codex\\bin",
        "--user-hook-fallback",
        "codex plugin add agent-context-substrate@personal",
        "codex_plugin_registered",
        "agent-context-substrate@personal",
        "Personal",
        "Created by you",
        "allowed_workspace_roots",
        "%USERPROFILE%\\Documents\\Codex",
        "ordinary Codex workspaces",
        "Codex app -> Settings -> Hooks",
        "CLI /hooks",
        "alternate",
        "Hooks need review",
        "Trust all and continue",
        "Running Stop hook: Finalizing Codex thread into Agent Context Substrate",
        "codex_hook_events.jsonl",
        "search-knowledge",
        "state_5.sqlite",
        "Documents\\LLM Wiki",
        "default template",
        "data\\...",
    ]:
        assert required in docs
    assert "--dangerously-bypass-hook-trust" not in docs


def test_windows_codex_hook_trust_guidance_is_app_first() -> None:
    surfaces = {
        "README.md": Path("README.md").read_text(encoding="utf-8"),
        "README.ko.md": Path("README.ko.md").read_text(encoding="utf-8"),
        "docs/WINDOWS_CODEX_APP_SETUP.md": Path("docs/WINDOWS_CODEX_APP_SETUP.md").read_text(encoding="utf-8"),
        "docs/WINDOWS_CODEX_APP_SETUP.ko.md": Path("docs/WINDOWS_CODEX_APP_SETUP.ko.md").read_text(encoding="utf-8"),
        "docs/USER_GUIDE.en.md": Path("docs/USER_GUIDE.en.md").read_text(encoding="utf-8"),
        "docs/USER_GUIDE.md": Path("docs/USER_GUIDE.md").read_text(encoding="utf-8"),
        "docs/RELEASE_CHECKLIST.md": Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8"),
        "plugin skill": Path(
            "src/agent_context_substrate/assets/codex_plugin/agent-context-substrate/skills/agent-context-substrate/SKILL.md"
        ).read_text(encoding="utf-8"),
        "scripts/setup-codex-windows.ps1": Path("scripts/setup-codex-windows.ps1").read_text(encoding="utf-8"),
    }
    forbidden_cli_first = [
        "Open Codex CLI and review /hooks",
        "Review /hooks in Codex CLI",
        "Run the Codex app CLI, then '/hooks'",
        "Run 'codex', then '/hooks'",
    ]

    for name, text in surfaces.items():
        assert "Codex app -> Settings -> Hooks" in text, name
        assert "Full Access" in text or "전체권한" in text or name.endswith(".ps1"), name
        assert "--dangerously-bypass-hook-trust" not in text, name
        for forbidden in forbidden_cli_first:
            assert forbidden not in text, name

    combined = "\n".join(surfaces.values())
    assert "CLI /hooks is the alternate" in combined or "CLI `/hooks` is an alternate" in combined
    assert "CLI /hooks 또는 Hooks need review modal은 대체" in combined
