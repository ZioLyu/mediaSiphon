"""引擎进程管理：异步启动、逐行读取输出、状态广播。

与界面完全解耦：所有状态变化都以事件回调的形式抛给上层，
由 API 层转成 WebSocket 消息。
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

from . import paths
from .progress import ProgressEvent, parse_chunk
from .settings import SiphonSettings
from .spec import FetchSpec, build_argv, find_output
from .store import (JobRecord, JobStore, STATUS_CANCELLED, STATUS_DONE, STATUS_FAILED,
                    STATUS_RUNNING)

log = logging.getLogger("siphon.runner")

EventSink = Callable[[Dict[str, object]], Awaitable[None]]


@dataclass
class RunningJob:
    job_id: str
    spec: FetchSpec
    process: asyncio.subprocess.Process
    started_at: float = field(default_factory=time.time)
    buffer: str = ""
    last_event: Optional[ProgressEvent] = None

    def terminate(self) -> None:
        if self.process.returncode is None:
            try:
                self.process.terminate()
            except ProcessLookupError:
                pass


class EngineRunner:
    """回调函数：接收上层注册的事件推送。"""

    def __init__(self, jobs: JobStore):
        self._jobs = jobs
        self._running: Dict[str, RunningJob] = {}
        self._sink: Optional[EventSink] = None
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def set_sink(self, sink: Optional[EventSink]) -> None:
        self._sink = sink

    @property
    def active_count(self) -> int:
        return len(self._running)

    def is_running(self, job_id: str) -> bool:
        return job_id in self._running

    async def _emit(self, event: Dict[str, object]) -> None:
        if self._sink is None:
            return
        try:
            await self._sink(event)
        except Exception as exc:
            log.debug("事件丢失: %s", exc)

    def _log_path(self, job_id: str) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return paths.log_dir() / f"{stamp}-{job_id[:8]}.log"

    async def submit(self, spec: FetchSpec, settings: SiphonSettings) -> JobRecord:
        engine = settings.downloader_exe
        if not Path(engine).exists():
            raise FileNotFoundError(f"找不到下载引擎：{engine}")

        argv = build_argv(engine, spec, settings)
        record = self._jobs.insert(
            source_url=spec.url,
            title=spec.title,
            variant=f"{spec.variant_width}x{spec.variant_height}" if spec.variant_width else "",
            kind="live" if spec.is_live else "vod",
            out_dir=spec.out_dir,
            file_hint="",
            argv=argv,
            log_path="",
            note="",
        )
        log_path = self._log_path(record.job_id)
        record = self._jobs.update(record.job_id, log_path=str(log_path)) or record

        await self._emit({"type": "job.created", "job": record.to_public()})
        asyncio.create_task(self._run(record.job_id, spec, settings, engine, argv, log_path))
        return record

    async def _run(self, job_id: str, spec: FetchSpec, settings: SiphonSettings,
                   engine: str, argv: List[str], log_path: Path) -> None:
        self._jobs.update(job_id, status=STATUS_RUNNING)
        await self._emit({"type": "job.status", "id": job_id, "status": STATUS_RUNNING})

        creation = 0
        if sys.platform == "win32":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            process = await asyncio.create_subprocess_exec(
                engine, *argv,
                cwd=str(Path(engine).parent),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creation,
            )
        except OSError as exc:
            self._jobs.update(job_id, status=STATUS_FAILED, note=f"启动失败：{exc}")
            await self._emit({"type": "job.finished", "id": job_id,
                              "status": STATUS_FAILED, "note": str(exc)})
            return

        running = RunningJob(job_id=job_id, spec=spec, process=process)
        async with self._get_lock():
            self._running[job_id] = running

        try:
            await self._pump_output(running, log_path)
            return_code = await process.wait()
        except asyncio.CancelledError:
            running.terminate()
            raise
        finally:
            async with self._get_lock():
                self._running.pop(job_id, None)

        current = self._jobs.get(job_id)
        if current is not None and current.status == STATUS_CANCELLED:
            await self._emit({"type": "job.finished", "id": job_id,
                              "status": STATUS_CANCELLED, "note": "已取消"})
            return

        if return_code == 0:
            output = find_output(spec, settings)
            if output is not None:
                size = output.stat().st_size
                self._jobs.update(job_id, status=STATUS_DONE,
                                  file_hint=str(output), bytes_total=size, note="")
                await self._maybe_thumbnail(job_id, output, settings)
                await self._emit({"type": "job.finished", "id": job_id, "status": STATUS_DONE,
                                  "file": str(output), "bytes": size})
            else:
                reason = "引擎正常退出，但没有找到输出文件"
                self._jobs.update(job_id, status=STATUS_FAILED, note=reason)
                await self._emit({"type": "job.finished", "id": job_id,
                                  "status": STATUS_FAILED, "note": reason})
        else:
            reason = f"引擎退出码 {return_code}"
            self._jobs.update(job_id, status=STATUS_FAILED, note=reason)
            await self._emit({"type": "job.finished", "id": job_id,
                              "status": STATUS_FAILED, "note": reason})

    async def _pump_output(self, running: RunningJob, log_path: Path) -> None:
        stream = running.process.stdout
        if stream is None:
            return

        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"===== {stamp} job {running.job_id} =====\n")
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                handle.write(text)
                handle.flush()

                events, running.buffer = parse_chunk(running.buffer + text)
                for event in events:
                    running.last_event = event
                    if event.total_bytes:
                        self._jobs.update(running.job_id, bytes_total=event.total_bytes)
                    await self._emit({"type": "job.progress", "id": running.job_id,
                                      "progress": event.to_dict()})

    async def _maybe_thumbnail(self, job_id: str, output: Path,
                               settings: SiphonSettings) -> None:
        """用多媒体工具抽一帧做封面，失败静默忽略。"""
        remuxer = settings.remuxer_exe
        if not Path(remuxer).exists():
            return

        thumb = paths.thumb_dir() / f"{job_id}.jpg"
        command = [remuxer, "-v", "error", "-y", "-ss", "0", "-i", str(output),
                   "-frames:v", "1", "-q:v", "4", str(thumb)]
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=creation,
            )
            await asyncio.wait_for(proc.wait(), timeout=30)
        except (OSError, asyncio.TimeoutError):
            return

        if thumb.exists():
            await self._emit({"type": "job.thumb", "id": job_id, "thumb": thumb.name})

    async def cancel(self, job_id: str) -> bool:
        self._jobs.update(job_id, status=STATUS_CANCELLED, note="用户取消")
        running = self._running.get(job_id)
        if running is None:
            return False
        running.terminate()
        return True

    async def shutdown(self) -> None:
        for running in list(self._running.values()):
            running.terminate()
        await asyncio.sleep(0)
