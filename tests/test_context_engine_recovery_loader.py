from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
ASSET_PACKAGE = ROOT / "src" / "agent_context_substrate" / "assets" / "context_engine" / "agent_context_substrate"


def _load_recovery_loader_module():
    package_name = "acs_context_engine_asset_for_tests"
    if package_name not in sys.modules:
        package_module = types.ModuleType(package_name)
        package_module.__path__ = [str(ASSET_PACKAGE)]
        sys.modules[package_name] = package_module

    module_name = f"{package_name}.recovery_loader"
    spec = importlib.util.spec_from_file_location(module_name, ASSET_PACKAGE / "recovery_loader.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
    return module


def test_context_engine_recovery_loader_rejects_path_like_session_id(tmp_path: Path) -> None:
    loader = _load_recovery_loader_module()
    project_root = tmp_path / "project"
    outside_recovery = project_root / "data" / "exports" / "outside.json"
    outside_recovery.parent.mkdir(parents=True)
    (project_root / "data" / "exports" / "recovery").mkdir(parents=True)
    outside_recovery.write_text(json.dumps({"secret": "outside recovery"}), encoding="utf-8")

    brief, source_path = loader.load_recovery_brief(project_root, "../outside")

    assert brief is None
    assert source_path is None


def test_context_engine_recovery_loader_rejects_direct_symlinked_recovery_file(tmp_path: Path) -> None:
    loader = _load_recovery_loader_module()
    project_root = tmp_path / "project"
    recovery_dir = project_root / "data" / "exports" / "recovery"
    recovery_dir.mkdir(parents=True)
    outside_recovery = tmp_path / "outside-recovery.json"
    outside_recovery.write_text(json.dumps({"secret": "outside"}), encoding="utf-8")
    (recovery_dir / "session-1.json").symlink_to(outside_recovery)

    brief, source_path = loader.load_recovery_brief(project_root, "session-1")

    assert brief is None
    assert source_path is None


def test_context_engine_recovery_loader_rejects_symlinked_recovery_directory(tmp_path: Path) -> None:
    loader = _load_recovery_loader_module()
    project_root = tmp_path / "project"
    exports_dir = project_root / "data" / "exports"
    exports_dir.mkdir(parents=True)
    outside_recovery_dir = tmp_path / "outside-recovery-dir"
    outside_recovery_dir.mkdir()
    (outside_recovery_dir / "session-1.json").write_text(json.dumps({"secret": "outside"}), encoding="utf-8")
    (exports_dir / "recovery").symlink_to(outside_recovery_dir, target_is_directory=True)

    brief, source_path = loader.load_recovery_brief(project_root, "session-1")

    assert brief is None
    assert source_path is None
