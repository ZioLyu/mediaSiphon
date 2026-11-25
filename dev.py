"""开发辅助：监听后端 Python 文件，自动重启桌面进程。

前端热更新由 Vite 自己负责，这个脚本只管后端。
用法：
    python dev.py            # 自动重启
    python dev.py --dev      # 同时让桌面窗口指向 Vite 开发服务器

需要开发依赖：pip install -e ".[dev]"（含 watchdog）。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("缺少 watchdog，请执行：pip install -e \".[dev]\"")
        return 1

    passthrough = [arg for arg in sys.argv[1:] if arg in ("--dev", "--no-window")]
    command = [sys.executable, "-m", "siphon.desktop", *passthrough]
    process: subprocess.Popen | None = None
    pending = {"flag": False}

    def spawn() -> None:
        nonlocal process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        process = subprocess.Popen(command, cwd=str(ROOT))

    class Watcher(FileSystemEventHandler):
        def on_modified(self, event) -> None:
            if event.is_directory:
                return
            path = Path(str(event.src_path))
            if path.suffix != ".py" or "__pycache__" in path.parts:
                return
            if not pending["flag"]:
                pending["flag"] = True
                time.sleep(0.25)
                pending["flag"] = False
                print("检测到改动，重启后端:", path.name)
                spawn()

    spawn()

    observer = Observer()
    observer.schedule(Watcher(), str(ROOT / "siphon"), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
            if process is not None and process.poll() is not None:
                print("进程已退出，按 Ctrl+C 结束监听")
                while process.poll() is not None:
                    time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        if process is not None and process.poll() is None:
            process.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
