"""清单探测：读出可变体（分辨率 / 编码 / 帧率）并判断是否为直播。

只做“看一眼”的工作，不下载任何分片。解析失败一律降级为“未知”，
绝不因为探测失败而阻止下载。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List
from urllib.parse import urlparse

import m3u8
from mpegdash.parser import MPEGDASHParser, MPEGDASH
from mpegdash.nodes import AdaptationSet, Representation

log = logging.getLogger("siphon.probe")

VIDEO_SUFFIXES = (".m3u8", ".m3u")
DASH_SUFFIXES = (".mpd",)
PLAYLIST_SUFFIXES = VIDEO_SUFFIXES + DASH_SUFFIXES


@dataclass
class Variant:
    width: int = 0
    height: int = 0
    codecs: str = ""
    fps: float = 0.0
    bandwidth: int = 0
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def build(cls, width: int = 0, height: int = 0, codecs: str = "",
              fps: float = 0.0, bandwidth: int = 0) -> "Variant":
        parts = []
        if width and height:
            parts.append(f"{width}x{height}")
        if fps:
            parts.append(f"{fps:g}fps")
        if codecs:
            parts.append(codecs)
        return cls(width=int(width or 0), height=int(height or 0),
                   codecs=codecs or "", fps=float(fps or 0.0),
                   bandwidth=int(bandwidth or 0), label=" ".join(parts) or "default")


@dataclass
class ProbeResult:
    kind: str = "vod"                 # vod | live | unknown
    variants: List[Variant] = None    # type: ignore[assignment]
    recognized: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if self.variants is None:
            self.variants = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "recognized": self.recognized,
            "reason": self.reason,
            "variants": [v.to_dict() for v in self.variants],
        }


def looks_like_playlist(url: str) -> bool:
    """按路径后缀判断看起来像不像清单地址（忽略 query）。"""
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return False
    return path.endswith(PLAYLIST_SUFFIXES)


def _parse_ratio(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    if "/" in text:
        num, _, den = text.partition("/")
        try:
            d = float(den)
            return float(num) / d if d else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


class _HlsProbe:
    def __init__(self, url: str, timeout: int):
        self.url = url
        self.timeout = timeout

    def run(self) -> ProbeResult:
        playlist = m3u8.load(self.url, timeout=max(3, self.timeout))
        variants: List[Variant] = []

        for entry in playlist.playlists or []:
            info = entry.stream_info
            resolution = info.resolution or (0, 0)
            variants.append(Variant.build(
                width=resolution[0] if len(resolution) > 1 else 0,
                height=resolution[1] if len(resolution) > 1 else 0,
                codecs=info.codecs or "",
                fps=_parse_ratio(getattr(info, "frame_rate", None)),
                bandwidth=getattr(info, "bandwidth", 0) or 0,
            ))

        is_live = not bool(playlist.is_endlist)
        # 没有子清单时（单码率或直播切片），给一个占位变体便于 UI 展示
        if not variants and (playlist.segments or is_live):
            variants.append(Variant(label="default", bandwidth=0))

        return ProbeResult(kind="live" if is_live else "vod", variants=variants,
                           recognized=True, reason="")


class _DashProbe:
    def __init__(self, url: str, timeout: int):
        self.url = url
        self.timeout = timeout

    def run(self) -> ProbeResult:
        manifest: MPEGDASH = MPEGDASHParser.parse(self.url)
        variants: List[Variant] = []

        periods = manifest.periods or []
        if periods:
            for aset in periods[0].adaptation_sets or []:
                for rep in aset.representations or []:
                    if not self._is_video(aset, rep):
                        continue
                    if not getattr(rep, "width", None):
                        continue
                    variants.append(Variant.build(
                        width=rep.width or 0,
                        height=rep.height or 0,
                        codecs=getattr(rep, "codecs", "") or "",
                        fps=_parse_ratio(getattr(rep, "frame_rate", None)),
                        bandwidth=getattr(rep, "bandwidth", 0) or 0,
                    ))

        kind = "live" if getattr(manifest, "type", "") == "dynamic" else "vod"
        if not variants:
            variants.append(Variant(label="default"))
        return ProbeResult(kind=kind, variants=variants, recognized=True, reason="")

    @staticmethod
    def _is_video(aset: AdaptationSet, rep: Representation) -> bool:
        content_type = (getattr(aset, "content_type", "") or "").lower()
        if content_type == "video":
            return True
        mime = (getattr(aset, "mime_type", "") or getattr(rep, "mime_type", "") or "").lower()
        if mime.startswith("video"):
            return True
        return bool(re.search(r"video", str(getattr(rep, "id", "") or ""), re.I))


def probe(url: str, timeout: int = 30, referer: str = "", headers: str = "") -> ProbeResult:
    """对给定地址做一次轻量探测。"""
    url = (url or "").strip()
    if not url:
        return ProbeResult(kind="unknown", recognized=False, reason="空地址")

    if not looks_like_playlist(url):
        return ProbeResult(kind="unknown", recognized=False, reason="不是 m3u8/mpd 地址")

    lowered = urlparse(url).path.lower()

    try:
        if lowered.endswith(DASH_SUFFIXES):
            return _DashProbe(url, timeout).run()
        return _HlsProbe(url, timeout).run()
    except Exception as exc:  # 探测失败不影响下载
        log.warning("probe failed for %s: %s", url, exc)
        return ProbeResult(kind="unknown", recognized=True, reason=f"探测失败: {exc}")
