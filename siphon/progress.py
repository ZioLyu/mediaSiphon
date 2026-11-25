"""从引擎的终端输出里提取进度。

自己实现 ANSI 清理与按行切分，并用命名分组而非位置捕获，
这样引擎输出多一列时，只要字段还在，解析依然成立。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

# 点播: 12/345 45.6% 1.2MB/30.5MB 3.4MBps 00:01:23
_VOD_RE = re.compile(
    r"(?P<done>\d+)\s*/\s*(?P<total>\d+)\s+"
    r"(?P<percent>\d+(?:\.\d+)?)\s*%\s+"
    r"(?P<have>\d+(?:\.\d+)?)\s*(?P<have_unit>[KMG]?B)\s*/\s*"
    r"(?P<all>\d+(?:\.\d+)?)\s*(?P<all_unit>[KMG]?B)\s+"
    r"(?P<speed>-|\d+(?:\.\d+)?)\s*(?P<speed_unit>[KMG]?Bps)\s*"
    r"(?P<eta>[\d:\-]+)",
    re.IGNORECASE,
)

# 直播: 01m23s/10m00s 45/200 Recording 45% 2.1MBps
_LIVE_RE = re.compile(
    r"(?P<elapsed>\d{1,2}m\d{1,2}s)\s*/\s*(?P<span>\d{1,2}m\d{1,2}s)\s+"
    r"(?P<done>\d+)\s*/\s*(?P<total>\d+)\s+"
    r"(?P<phase>Recording|Waiting)\s+"
    r"(?P<percent>\d+)\s*%"
    r"(?:\s+(?P<speed>-|\d+(?:\.\d+)?)\s*(?P<speed_unit>[KMG]?Bps))?",
    re.IGNORECASE,
)

_UNIT_SCALE = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def _to_bytes(amount: str, unit: str) -> int:
    try:
        return int(float(amount) * _UNIT_SCALE.get(unit.upper(), 1))
    except (TypeError, ValueError):
        return 0


def _normalize_speed(amount: Optional[str], unit: Optional[str]) -> str:
    """把引擎输出的速率统一成可读字符串。"""
    if not amount or amount == "-":
        return "0 B/s"
    scale = _UNIT_SCALE.get((unit or "B").upper().rstrip("PS"), 1)
    try:
        value = float(amount) * scale
    except ValueError:
        return "0 B/s"

    for suffix, divider in (("GB/s", 1024 ** 3), ("MB/s", 1024 ** 2), ("KB/s", 1024)):
        if value >= divider:
            return f"{value / divider:.1f} {suffix}"
    return f"{value:.0f} B/s"


@dataclass
class ProgressEvent:
    phase: str          # fetching | recording | waiting
    done: int
    total: int
    percent: int
    have_bytes: int
    total_bytes: int
    speed: str
    eta: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "phase": self.phase,
            "done": self.done,
            "total": self.total,
            "percent": self.percent,
            "haveBytes": self.have_bytes,
            "totalBytes": self.total_bytes,
            "speed": self.speed,
            "eta": self.eta,
        }


def parse_line(line: str) -> Optional[ProgressEvent]:
    """解析单行输出；不是进度行则返回 None。"""
    text = strip_ansi(line).strip()
    if not text:
        return None
    if "WARN" in text.upper() and "%" not in text:
        return None

    live = _LIVE_RE.search(text)
    if live:
        phase = "recording" if live["phase"].lower() == "recording" else "waiting"
        return ProgressEvent(
            phase=phase,
            done=int(live["done"]),
            total=int(live["total"]),
            percent=int(live["percent"]),
            have_bytes=0,
            total_bytes=0,
            speed=_normalize_speed(live["speed"], live["speed_unit"]),
            eta=live["span"],
        )

    vod = _VOD_RE.search(text)
    if vod:
        return ProgressEvent(
            phase="fetching",
            done=int(vod["done"]),
            total=int(vod["total"]),
            percent=int(float(vod["percent"])),
            have_bytes=_to_bytes(vod["have"], vod["have_unit"]),
            total_bytes=_to_bytes(vod["all"], vod["all_unit"]),
            speed=_normalize_speed(vod["speed"], vod["speed_unit"]),
            eta=vod["eta"],
        )

    return None


def parse_chunk(buffer: str) -> Tuple[List[ProgressEvent], str]:
    """把一段原始输出切成完整行，返回 (事件列表, 残余缓冲)。

    引擎用 \\r 或 \\n 刷新进度，两种换行都要处理。
    """
    normalized = strip_ansi(buffer.replace("\r\n", "\n").replace("\r", "\n"))
    lines = normalized.split("\n")
    tail = ""
    if normalized and not normalized.endswith("\n"):
        tail = lines.pop()

    events: List[ProgressEvent] = []
    for line in lines:
        event = parse_line(line)
        if event is not None:
            events.append(event)
    return events, tail
