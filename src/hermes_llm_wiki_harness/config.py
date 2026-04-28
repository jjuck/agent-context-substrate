from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class HarnessConfig:
    project_root: Path
    default_wiki_path: Path
    default_hermes_home: Path

    @classmethod
    def from_environment(cls, project_root: Path) -> "HarnessConfig":
        home = Path(os.path.expanduser("~"))
        wiki_path = Path(os.environ.get("WIKI_PATH", str(home / "wiki"))).expanduser()
        hermes_home = Path(os.environ.get("HERMES_HOME", str(home / ".hermes"))).expanduser()
        return cls(
            project_root=project_root,
            default_wiki_path=wiki_path,
            default_hermes_home=hermes_home,
        )
