"""运行时目录与路径解析。

所有可变数据都放在单一应用目录里，方便用户整体搬移或清理。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "mediaSiphon"
DB_FILE_NAME = "history.db"
SETTINGS_FILE_NAME = "settings.json"
THUMB_DIR_NAME = "thumbs"
LOG_DIR_NAME = "logs"
ENGINE_DIR_NAME = "engine"


def is_frozen() -> bool:
    """是否运行在打包产物里（Nuitka 写 __compiled__，PyInstaller 写 sys.frozen）。"""
    return bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()


def bundle_root() -> Path:
    """只读资源所在目录：源码模式是仓库根，打包后是可执行文件所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """可写数据目录。开发时放在仓库下的 runtime/，便于随时删除重建。"""
    override = os.environ.get("SIPHON_DATA_DIR")
    if override:
        root = Path(override).expanduser().resolve()
    elif is_frozen():
        root = Path(os.environ.get("APPDATA") or Path.home()) / APP_DIR_NAME
    else:
        root = bundle_root() / "runtime"

    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return data_root() / DB_FILE_NAME


def settings_path() -> Path:
    return data_root() / SETTINGS_FILE_NAME


def thumb_dir() -> Path:
    path = data_root() / THUMB_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = data_root() / LOG_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def engine_dir() -> Path:
    return bundle_root() / ENGINE_DIR_NAME


def executable_suffix() -> str:
    return ".exe" if sys.platform == "win32" else ""
