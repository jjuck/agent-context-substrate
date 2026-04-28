from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class HarnessPaths:
    project_root: Path

    @property
    def home_dir(self) -> Path:
        return Path(os.path.expanduser("~"))

    @property
    def hermes_home(self) -> Path:
        value = os.environ.get("HERMES_HOME")
        return Path(value).expanduser() if value else self.home_dir / ".hermes"

    @property
    def state_db_path(self) -> Path:
        return self.hermes_home / "state.db"

    @property
    def wiki_root(self) -> Path:
        value = os.environ.get("WIKI_PATH")
        return Path(value).expanduser() if value else self.home_dir / "wiki"

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
