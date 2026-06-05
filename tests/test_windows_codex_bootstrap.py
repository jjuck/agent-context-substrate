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
    assert "--user-hook-fallback" not in script
    assert "--dangerously-bypass-hook-trust" not in script


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
        "Hooks need review",
        "Trust all and continue",
        "Running Stop hook: Finalizing Codex thread into Agent Context Substrate",
        "codex_hook_events.jsonl",
        "search-knowledge",
        "state_5.sqlite",
        "Documents\\LLM Wiki",
        "data\\...",
    ]:
        assert required in docs
    assert "--dangerously-bypass-hook-trust" not in docs
