from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_context_substrate.paths import HarnessPaths  # noqa: E402


def test_harness_paths_uses_env_override_for_wiki_root(monkeypatch, tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    monkeypatch.setenv("WIKI_PATH", str(wiki_root))

    paths = HarnessPaths(project_root=project_root)

    assert paths.wiki_root == wiki_root
    assert paths.data_dir == project_root / "data"
    assert paths.exports_dir == project_root / "data" / "exports"


def test_harness_paths_defaults_to_hermes_state_db_under_home(tmp_path, monkeypatch) -> None:
    hermes_home = tmp_path / ".hermes"
    user_profile = tmp_path / "user-profile"
    hermes_home.mkdir()
    user_profile.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(user_profile))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("WIKI_PATH", raising=False)

    paths = HarnessPaths(project_root=tmp_path / "project")

    assert paths.hermes_home == hermes_home
    assert paths.state_db_path == hermes_home / "state.db"
    assert paths.wiki_root == tmp_path / "wiki"


def test_harness_paths_explicit_roots_take_precedence_over_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "env-hermes"))
    monkeypatch.setenv("WIKI_PATH", str(tmp_path / "env-wiki"))

    explicit_hermes = tmp_path / "explicit-hermes"
    explicit_wiki = tmp_path / "explicit-wiki"
    paths = HarnessPaths(
        project_root=tmp_path / "project",
        hermes_home=explicit_hermes,
        wiki_root=explicit_wiki,
    )

    assert paths.hermes_home == explicit_hermes
    assert paths.state_db_path == explicit_hermes / "state.db"
    assert paths.wiki_root == explicit_wiki
