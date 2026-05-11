from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class HarnessPaths:
    project_root: Path | str
    hermes_home: Path | str | None = None
    wiki_root: Path | str | None = None
    home_dir: Path | str | None = None

    def __post_init__(self) -> None:
        home_dir = Path(self.home_dir).expanduser() if self.home_dir is not None else Path(os.path.expanduser("~"))
        hermes_home = (
            Path(self.hermes_home).expanduser()
            if self.hermes_home is not None
            else Path(os.environ["HERMES_HOME"]).expanduser()
            if os.environ.get("HERMES_HOME")
            else home_dir / ".hermes"
        )
        wiki_root = (
            Path(self.wiki_root).expanduser()
            if self.wiki_root is not None
            else Path(os.environ["WIKI_PATH"]).expanduser()
            if os.environ.get("WIKI_PATH")
            else home_dir / "wiki"
        )
        object.__setattr__(self, "project_root", Path(self.project_root).expanduser())
        object.__setattr__(self, "home_dir", home_dir)
        object.__setattr__(self, "hermes_home", hermes_home)
        object.__setattr__(self, "wiki_root", wiki_root)

    @property
    def state_db_path(self) -> Path:
        return self.hermes_home / "state.db"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    def ensure_project_dirs(self) -> None:
        for path in (self.data_dir, self.cache_dir, self.exports_dir, self.index_dir):
            path.mkdir(parents=True, exist_ok=True)
