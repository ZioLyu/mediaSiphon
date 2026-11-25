"""HTTP 接口与 WebSocket 通道。

一条规则：界面只通过这里访问后端，后端不感知任何前端框架细节。
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, paths
from .probe import probe, looks_like_playlist
from .runner import EngineRunner
from .settings import SiphonSettings, settings_store
from .spec import FetchSpec, sanitize_title
from .store import ACTIVE_STATUSES, JobStore, job_store

log = logging.getLogger("siphon.api")


class ProbeIn(BaseModel):
    url: str = Field(..., min_length=1)


class StartIn(BaseModel):
    url: str = Field(..., min_length=1)
    title: str = ""
    outDir: str = ""
    variantWidth: int = 0
    variantHeight: int = 0
    variantFps: float = 0
    isLive: bool = False
    keepTemp: bool | None = None


class BatchItem(BaseModel):
    title: str = ""
    url: str = Field(..., min_length=1)


class BatchIn(BaseModel):
    items: List[BatchItem]
    outDir: str = ""


class SettingsPatch(BaseModel):
    patch: Dict[str, Any]


class DirectoryIn(BaseModel):
    path: str = ""


class Browser:
    """WebSocket 连接池 + 事件广播。"""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def drop(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: Dict[str, object]) -> None:
        async with self._lock:
            targets = list(self._clients)
        dead = []
        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


def _open_in_file_manager(target: Path) -> bool:
    if not target.exists():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            if target.is_dir():
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])
        return True
    except OSError:
        return False


def create_app(job_db: Optional[JobStore] = None) -> FastAPI:
    jobs = job_db or job_store
    runner = EngineRunner(jobs)
    hub = Browser()

    app = FastAPI(title="mediaSiphon API", version=__version__,
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.runner = runner
    app.state.hub = hub

    runner.set_sink(hub.broadcast)

    @app.on_event("startup")
    async def _startup() -> None:
        recovered = jobs.mark_orphans_failed()
        if recovered:
            log.warning("把 %d 条上次未结束的任务标记为失败", recovered)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await runner.shutdown()

    # ---------- 基础 ----------
    @app.get("/api/health")
    async def health() -> Dict[str, Any]:
        return {
            "ok": True,
            "version": __version__,
            "engine": settings_store.read().downloader_exe,
            "engineReady": Path(settings_store.read().downloader_exe).exists(),
        }

    # ---------- 设置 ----------
    @app.get("/api/settings")
    async def get_settings() -> Dict[str, Any]:
        return settings_store.read().to_dict()

    @app.patch("/api/settings")
    async def patch_settings(body: SettingsPatch) -> Dict[str, Any]:
        updated = settings_store.replace(body.patch)
        await hub.broadcast({"type": "settings.changed", "settings": updated.to_dict()})
        return updated.to_dict()

    @app.post("/api/settings/reset")
    async def reset_settings() -> Dict[str, Any]:
        defaults = settings_store.reset()
        await hub.broadcast({"type": "settings.changed", "settings": defaults.to_dict()})
        return defaults.to_dict()

    # ---------- 探测 ----------
    @app.post("/api/probe")
    async def do_probe(body: ProbeIn) -> Dict[str, Any]:
        settings = settings_store.read()
        result = await asyncio.to_thread(
            probe, body.url.strip(), max(3, min(settings.request_timeout, 15)),
            settings.referer, settings.extra_headers)
        payload = result.to_dict()
        payload["looksLikePlaylist"] = looks_like_playlist(body.url.strip())
        return payload

    # ---------- 文件系统辅助 ----------
    @app.post("/api/fs/pick-dir")
    async def pick_dir(body: DirectoryIn) -> Dict[str, Any]:
        """用系统原生对话框选目录；没有图形环境时退回普通输入。"""
        start = body.path or settings_store.read().output_dir
        try:
            import tkinter
            from tkinter import filedialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askdirectory(initialdir=start)
            root.destroy()
        except Exception as exc:
            raise HTTPException(status_code=501, detail=f"无法打开系统对话框: {exc}") from exc
        return {"path": chosen or ""}

    @app.post("/api/fs/reveal")
    async def reveal(body: DirectoryIn) -> Dict[str, Any]:
        if not body.path:
            raise HTTPException(status_code=400, detail="缺少路径")
        return {"ok": _open_in_file_manager(Path(body.path))}

    # ---------- 任务 ----------
    @app.get("/api/jobs")
    async def list_jobs(status: str = "all", limit: int = 500) -> Dict[str, Any]:
        limit = max(1, min(limit, 2000))
        records = jobs.list(status=status, limit=limit)
        return {"jobs": [r.to_public() for r in records], "active": runner.active_count}

    @app.post("/api/jobs")
    async def create_job(body: StartIn) -> Dict[str, Any]:
        settings = settings_store.read()
        # 单次请求可以覆盖“保留临时分片”，不影响全局设置
        if body.keepTemp is not None and body.keepTemp != settings.keep_temp:
            settings = SiphonSettings.from_mapping(
                {**settings.to_dict(), "keep_temp": body.keepTemp})
        try:
            spec = FetchSpec.from_payload(body.model_dump(), settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not Path(settings.downloader_exe).exists():
            raise HTTPException(status_code=409, detail="下载引擎未就位，请先在设置里指定路径")

        # 标题留空则尝试自动生成
        if not body.title.strip():
            stem = Path(spec.url.split("?")[0]).stem
            spec.title = sanitize_title(stem, fallback="capture")

        try:
            record = await runner.submit(spec, settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return record.to_public()

    @app.post("/api/jobs/batch")
    async def create_batch(body: BatchIn) -> Dict[str, Any]:
        settings = settings_store.read()
        if not Path(settings.downloader_exe).exists():
            raise HTTPException(status_code=409, detail="下载引擎未就位，请先在设置里指定路径")

        created, skipped = [], []
        for item in body.items:
            url = item.url.strip()
            if not url:
                continue
            payload = {
                "url": url,
                "title": item.title.strip(),
                "outDir": body.outDir or settings.output_dir,
            }
            try:
                spec = FetchSpec.from_payload(payload, settings)
            except ValueError:
                skipped.append(url)
                continue
            if not spec.title:
                spec.title = sanitize_title(Path(url.split("?")[0]).stem, fallback="capture")
            try:
                record = await runner.submit(spec, settings)
                created.append(record.to_public())
            except FileNotFoundError:
                skipped.append(url)

        return {"created": created, "skipped": skipped}

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> Dict[str, Any]:
        ok = await runner.cancel(job_id)
        return {"ok": ok}

    @app.post("/api/jobs/{job_id}/retry")
    async def retry_job(job_id: str) -> Dict[str, Any]:
        record = jobs.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        settings = settings_store.read()
        spec = FetchSpec(
            url=record.source_url,
            title=record.title,
            out_dir=record.out_dir,
            is_live=(record.kind == "live"),
        )
        if record.variant and "x" in record.variant:
            w, _, h = record.variant.partition("x")
            try:
                spec.variant_width = int(w)
                spec.variant_height = int(h)
            except ValueError:
                pass
        try:
            new_record = await runner.submit(spec, settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return new_record.to_public()

    @app.delete("/api/jobs/{job_id}")
    async def delete_job(job_id: str, purge: bool = False) -> Dict[str, Any]:
        record = jobs.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="任务不存在")

        if record.status in ACTIVE_STATUSES:
            await runner.cancel(job_id)

        removed_file = False
        if purge:
            for suffix in (".mp4", ".ts", ".mkv", ".flv"):
                target = Path(record.out_dir) / (record.title + suffix)
                if target.exists():
                    try:
                        target.unlink()
                        removed_file = True
                    except OSError:
                        pass

        jobs.delete(job_id)
        await hub.broadcast({"type": "job.deleted", "id": job_id})
        return {"ok": True, "removedFile": removed_file}

    @app.get("/api/jobs/{job_id}/log")
    async def job_log(job_id: str, tail: int = 400) -> Dict[str, Any]:
        record = jobs.get(job_id)
        if record is None or not record.log_path:
            raise HTTPException(status_code=404, detail="任务不存在")
        path = Path(record.log_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="没有日志")
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return {"lines": text[-max(1, tail):]}

    @app.get("/api/thumbs/{name}")
    async def thumb(name: str) -> FileResponse:
        safe = Path(name).name
        target = paths.thumb_dir() / safe
        if not target.exists():
            raise HTTPException(status_code=404, detail="日志文件不存在")
        return FileResponse(str(target), media_type="image/jpeg")

    # ---------- WebSocket ----------
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await hub.add(ws)
        try:
            await ws.send_json({"type": "hello", "version": __version__})
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await hub.drop(ws)

    # ---------- 静态前端 ----------
    dist = paths.bundle_root() / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(str(dist / "index.html"))

        @app.get("/{path:path}")
        async def spa_fallback(path: str) -> Any:
            candidate = dist / path
            if candidate.is_file():
                return FileResponse(str(candidate))
            if path.startswith("api/") or path.startswith("ws"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(str(dist / "index.html"))

    return app
