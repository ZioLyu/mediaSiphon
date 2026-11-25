"""设置项定义与读写。

设计上刻意不用第三方配置框架：一份带默认值的字典 + 显式校验 + 原子落盘。
字段名全部自定义，语义比同类项目更扁平。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

from . import paths


@dataclass
class SiphonSettings:
    """用户可调的全部设置。"""

    # 输出位置
    output_dir: str = field(default_factory=lambda: str(Path.home() / "Videos" / "mediaSiphon"))

    # 外部引擎
    downloader_exe: str = field(
        default_factory=lambda: str(paths.engine_dir() / f"N_m3u8DL-RE{paths.executable_suffix()}"))
    remuxer_exe: str = field(
        default_factory=lambda: str(paths.engine_dir() / f"ffmpeg{paths.executable_suffix()}"))

    # 抓取行为
    parallel_fragments: int = 16
    fragment_retries: int = 3
    request_timeout: int = 60
    speed_limit_kib: int = 0
    keep_temp: bool = False
    extra_headers: str = ""
    proxy_mode: str = "system"
    manual_proxy: str = ""
    referer: str = ""

    # 直播
    live_realtime_merge: bool = True
    live_keep_fragments: bool = False
    live_stop_after: str = ""
    live_poll_interval: int = 0

    # 解封装与解密
    remux_after_done: str = ""
    remux_imports: str = ""
    decrypt_engine: str = "ffmpeg"
    decrypt_tool_path: str = ""
    decrypt_keys: str = ""
    decrypt_key_file: str = ""

    # 界面
    accent: str = "#5b5bd6"
    theme: str = "auto"
    locale: str = "zh-CN"
    clear_form_after_submit: bool = True
    check_update_on_launch: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, raw: Dict[str, Any]) -> "SiphonSettings":
        """只接受已知字段，未知键静默丢弃，避免旧配置撑爆新版本。"""
        settings = cls()
        for key, value in raw.items():
            if not hasattr(settings, key) or value is None:
                continue
            current = getattr(settings, key)
            if isinstance(current, bool):
                if not isinstance(value, bool):
                    continue
            elif isinstance(current, int):
                if isinstance(value, bool):
                    continue
                if not isinstance(value, int):
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        continue
            elif isinstance(current, str) and not isinstance(value, str):
                continue
            setattr(settings, key, value)
        settings.normalize()
        return settings

    def normalize(self) -> None:
        self.parallel_fragments = max(1, min(int(self.parallel_fragments), 128))
        self.fragment_retries = max(0, min(int(self.fragment_retries), 50))
        self.request_timeout = max(5, min(int(self.request_timeout), 600))
        self.speed_limit_kib = max(0, int(self.speed_limit_kib))
        self.live_poll_interval = max(0, int(self.live_poll_interval))

        if self.proxy_mode not in ("system", "manual", "none"):
            self.proxy_mode = "system"
        if self.decrypt_engine not in ("ffmpeg", "mp4decrypt", "shaka"):
            self.decrypt_engine = "ffmpeg"
        if self.theme not in ("auto", "light", "dark"):
            self.theme = "auto"
        if self.locale not in ("zh-CN", "zh-TW", "en-US"):
            self.locale = "zh-CN"

        fallback = str(Path.home() / "Videos" / "mediaSiphon")
        self.output_dir = os.path.expanduser((self.output_dir or "").strip() or fallback)


class SettingsStore:
    """线程安全的设置读写。"""

    def __init__(self, file_path: Path | None = None):
        self._path = file_path or paths.settings_path()
        self._lock = threading.RLock()
        self._settings = self._load()

    def _load(self) -> SiphonSettings:
        if not self._path.exists():
            return SiphonSettings()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return SiphonSettings()
        if not isinstance(raw, dict):
            return SiphonSettings()
        return SiphonSettings.from_mapping(raw)

    def read(self) -> SiphonSettings:
        with self._lock:
            return SiphonSettings.from_mapping(self._settings.to_dict())

    def replace(self, patch: Dict[str, Any]) -> SiphonSettings:
        with self._lock:
            merged = self._settings.to_dict()
            merged.update({key: value for key, value in patch.items() if key in merged})
            self._settings = SiphonSettings.from_mapping(merged)
            self._flush()
            return SiphonSettings.from_mapping(self._settings.to_dict())

    def reset(self) -> SiphonSettings:
        with self._lock:
            self._settings = SiphonSettings()
            self._flush()
            return self.read()

    def _flush(self) -> None:
        payload = json.dumps(self._settings.to_dict(), ensure_ascii=False, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, self._path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


settings_store = SettingsStore()
