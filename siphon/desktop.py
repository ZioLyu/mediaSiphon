"""桌面外壳：找空闲端口 → 后台线程跑 uvicorn → 弹出原生窗口。

开发期可以直接 `python -m siphon.desktop --dev`，此时窗口指向 Vite 开发服务器，
改前端代码即时热更，不需要重启桌面壳。
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from . import __app_slug__, __version__
from . import paths

log = logging.getLogger("siphon.desktop")

WINDOW_TITLE = "mediaSiphon"
DEV_SERVER = "http://127.0.0.1:5173"


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    try:
        file_handler = logging.FileHandler(paths.log_dir() / "app.log", encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(file_handler)
    except OSError:
        pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class SingleInstance:
    """基于本地回环端口的单实例锁：第二个进程会把参数转交给第一个后退出。"""

    def __init__(self, key: str, port_file: Path):
        self.key = key
        self.port_file = port_file
        self._server: Optional[socket.socket] = None

    def acquire(self) -> bool:
        existing = self._read_port()
        if existing:
            try:
                socket.create_connection(("127.0.0.1", existing), timeout=0.4).close()
                log.info("已有实例在运行，端口 %s，本次启动退出", existing)
                return False
            except OSError:
                pass

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
        except OSError as exc:
            log.warning("单实例锁创建失败，继续启动：%s", exc)
            return True

        self._server = server
        port = server.getsockname()[1]
        self.port_file.parent.mkdir(parents=True, exist_ok=True)
        self.port_file.write_text(str(port), encoding="utf-8")
        return True

    def _read_port(self) -> Optional[int]:
        try:
            return int(self.port_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def release(self) -> None:
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        try:
            if self.port_file.exists():
                self.port_file.unlink()
        except OSError:
            pass


def _serve(app, port: int) -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


def _wait_until_ready(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            return True
        except OSError:
            time.sleep(0.12)
    return False


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog=__app_slug__)
    parser.add_argument("--dev", action="store_true", help="连接 Vite 开发服务器")
    parser.add_argument("--no-window", action="store_true", help="只跑后端，不开窗口")
    parser.add_argument("--port", type=int, default=0, help="固定后端端口")
    args = parser.parse_args(argv)

    _configure_logging()
    log.info("%s v%s 启动", WINDOW_TITLE, __version__)

    lock = SingleInstance(__app_slug__, paths.data_root() / ".instance")
    if not lock.acquire():
        return 0

    from .api import create_app
    from .store import job_store

    app = create_app(job_store)
    port = args.port or _free_port()
    server_thread = threading.Thread(target=_serve, args=(app, port), daemon=True)
    server_thread.start()

    if not _wait_until_ready(port):
        log.error("后端未能在超时内就绪，退出")
        lock.release()
        return 1

    backend_url = f"http://127.0.0.1:{port}"
    log.info("后端就绪: %s", backend_url)

    if args.no_window:
        log.info("仅后端模式，Ctrl+C 退出")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            lock.release()
        return 0

    if args.dev:
        target = DEV_SERVER
        if not _probe_url(target):
            log.warning("Vite 开发服务器未运行（%s），先启动 `npm run dev`", target)
    else:
        target = backend_url

    try:
        import webview
    except ImportError:
        log.error("缺少 pywebview，请先安装依赖；或使用 --no-window 只跑后端")
        lock.release()
        return 1

    webview.create_window(
        WINDOW_TITLE,
        url=target,
        width=1180,
        height=780,
        min_size=(920, 620),
        background_color="#f3f6fa",
        text_select=False,
        easy_drag=False,
    )
    try:
        webview.start(debug=args.dev)
    finally:
        lock.release()
    return 0


def _probe_url(url: str, timeout: float = 0.6) -> bool:
    host = url.split("//", 1)[-1]
    if ":" not in host:
        return False
    name, _, port_text = host.partition(":")
    try:
        socket.create_connection((name, int(port_text.split("/")[0])), timeout=timeout).close()
        return True
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    sys.exit(main())
