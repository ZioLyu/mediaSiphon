"""抓取规格 → 命令行参数。

参数名属于第三方引擎的稳定接口，因此沿用；
但参数如何组织、默认值怎么取、如何序列化，都是本项目自己的设计。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .settings import SiphonSettings

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def sanitize_title(name: str, fallback: str = "untitled") -> str:
    """清掉文件系统不允许的字符；若清完什么都不剩则用兜底名。"""
    cleaned = _UNSAFE_NAME.sub("_", (name or "").strip())
    cleaned = cleaned.strip(" ._")
    return cleaned[:120] or fallback


def _flag(name: str, value: Any) -> List[str]:
    if value is None or value is False:
        return []
    if value is True:
        return [name]
    text = str(value).strip()
    if not text:
        return []
    # 引擎接受 --key=value 形式。参数以列表形式交给子进程，
    # 不经过 shell，所以含空格的值不需要加引号。
    return [f"{name}={text}"]


@dataclass
class FetchSpec:
    """一次抓取请求的完整描述（可序列化，便于重试）。"""

    url: str
    title: str = ""
    out_dir: str = ""
    variant_width: int = 0
    variant_height: int = 0
    variant_fps: float = 0.0
    is_live: bool = False
    temp_dir: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], settings: SiphonSettings) -> "FetchSpec":
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("缺少源地址")

        default_dir = settings.output_dir or str(Path.home() / "Videos" / "mediaSiphon")
        out_dir = str(payload.get("outDir") or default_dir).strip() or default_dir

        return cls(
            url=url,
            title=sanitize_title(str(payload.get("title") or "")),
            out_dir=out_dir,
            variant_width=int(payload.get("variantWidth") or 0),
            variant_height=int(payload.get("variantHeight") or 0),
            variant_fps=float(payload.get("variantFps") or 0.0),
            is_live=bool(payload.get("isLive")),
            temp_dir=payload.get("tempDir") or None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "outDir": self.out_dir,
            "variantWidth": self.variant_width,
            "variantHeight": self.variant_height,
            "variantFps": self.variant_fps,
            "isLive": self.is_live,
        }


def _variant_selector(spec: FetchSpec) -> str:
    parts = []
    if spec.variant_width:
        parts.append(f"res={spec.variant_width}*")
    if spec.variant_fps:
        parts.append(f"frame={int(spec.variant_fps)}*")
    return ":".join(parts) or "best"


def _header_tokens(settings: SiphonSettings) -> List[str]:
    tokens: List[str] = []
    for raw in (settings.extra_headers or "").splitlines():
        line = raw.strip()
        if line and ":" in line:
            tokens.extend(_flag("--header", line))
    if settings.referer.strip():
        tokens.extend(_flag("--header", f"Referer: {settings.referer.strip()}"))
    return tokens


def _proxy_tokens(settings: SiphonSettings) -> List[str]:
    if settings.proxy_mode == "system":
        return ["--use-system-proxy=true"]
    if settings.proxy_mode == "none":
        return ["--use-system-proxy=false"]
    tokens = ["--use-system-proxy=false"]
    if settings.manual_proxy.strip():
        tokens.extend(_flag("--custom-proxy", settings.manual_proxy.strip()))
    return tokens


def _live_tokens(settings: SiphonSettings) -> List[str]:
    tokens = ["--live-real-time-merge=" + ("true" if settings.live_realtime_merge else "false")]
    if settings.live_keep_fragments:
        tokens.append("--live-keep-segments=true")
    if settings.live_stop_after.strip():
        tokens.extend(_flag("--live-record-limit", settings.live_stop_after.strip()))
    if settings.live_poll_interval > 0:
        tokens.extend(_flag("--live-wait-time", settings.live_poll_interval))
    return tokens


_ENGINE_NAMES = {"ffmpeg": "FFmpeg", "mp4decrypt": "MP4Decrypt", "shaka": "Shaka"}


def _crypto_tokens(settings: SiphonSettings) -> List[str]:
    engine = _ENGINE_NAMES.get(settings.decrypt_engine, "FFmpeg")
    tokens = [f"--decryption-engine={engine}"]
    if settings.decrypt_tool_path.strip():
        tokens.extend(_flag("--decryption-binary-path", settings.decrypt_tool_path.strip()))
    if settings.decrypt_key_file.strip():
        tokens.extend(_flag("--key-text-file", settings.decrypt_key_file.strip()))
    for raw in (settings.decrypt_keys or "").splitlines():
        line = raw.strip()
        if line:
            tokens.extend(_flag("--key", line))
    return tokens


def _remux_tokens(settings: SiphonSettings) -> List[str]:
    tokens: List[str] = []
    if settings.remux_after_done.strip():
        tokens.extend(_flag("--mux-after-done", settings.remux_after_done.strip()))
    for raw in (settings.remux_imports or "").splitlines():
        line = raw.strip()
        if line:
            tokens.extend(_flag("--mux-import", line))
    return tokens


def build_argv(engine: str, spec: FetchSpec, settings: SiphonSettings) -> List[str]:
    """生成传给外部引擎的完整参数列表。"""
    save_name = spec.title or "untitled"
    work_dir = spec.temp_dir or spec.out_dir
    os.makedirs(spec.out_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    argv: List[str] = [
        spec.url,
        f"--save-dir={spec.out_dir}",
        f"--save-name={save_name}",
        f"--tmp-dir={work_dir}",
        f"--thread-count={settings.parallel_fragments}",
        f"--download-retry-count={settings.fragment_retries}",
        f"--http-request-timeout={settings.request_timeout}",
        f"--select-video={_variant_selector(spec)}",
        "--select-audio=all",
        "--select-subtitle=all",
        "--check-segments-count=true",
        "--no-ansi-color",
        "--disable-update-check",
    ]

    if not settings.keep_temp:
        argv.append("--del-after-done=true")

    if settings.speed_limit_kib > 0:
        argv.append(f"--max-speed={settings.speed_limit_kib}K")

    argv.extend(_header_tokens(settings))
    argv.extend(_proxy_tokens(settings))
    argv.extend(_live_tokens(settings))
    argv.extend(_crypto_tokens(settings))
    argv.extend(_remux_tokens(settings))

    deduped: List[str] = []
    for token in argv:
        if token not in deduped:
            deduped.append(token)
    return deduped


def expected_suffixes(spec: FetchSpec, settings: SiphonSettings) -> List[str]:
    """按引擎行为推测产物后缀，用于判定下载是否真的成功。"""
    if spec.is_live:
        return [".ts", ".mp4"] if settings.live_realtime_merge else [".mp4", ".ts"]
    return [".mp4", ".ts", ".mkv", ".flv"]


def find_output(spec: FetchSpec, settings: SiphonSettings) -> Optional[Path]:
    base = Path(spec.out_dir) / (spec.title or "untitled")
    for suffix in expected_suffixes(spec, settings):
        candidate = base.with_suffix(suffix)
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None
