"""打包脚本：用 Nuitka 生成三平台桌面产物。

用法：
    python build.py            # 按当前平台打包
    python build.py --clean    # 先清理上次产物

前端产物（frontend/dist）与外部引擎目录（engine）会被一并收进分发包。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "siphon" / "desktop.py"
DIST = ROOT / "dist"
FRONTEND_DIST = ROOT / "frontend" / "dist"
ENGINE_DIR = ROOT / "engine"
APP_NAME = "mediaSiphon"


def ensure_frontend() -> None:
    if not (FRONTEND_DIST / "index.html").exists():
        raise SystemExit(
            "找不到前端产物，请先在 frontend/ 目录执行 npm install && npm run build"
        )


def ensure_engine() -> None:
    binaries = [p for p in ENGINE_DIR.glob("*") if p.is_file()] if ENGINE_DIR.exists() else []
    if not binaries:
        print("提示：engine/ 目录为空，打包后需要用户自行放置外部引擎")


def common_args() -> list[str]:
    args = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--show-progress",
        f"--output-dir={DIST}",
        f"--include-data-dir={FRONTEND_DIST}=frontend/dist",
    ]
    if ENGINE_DIR.exists():
        args.append(f"--include-data-dir={ENGINE_DIR}=engine")
    return args


def windows_args() -> list[str]:
    return common_args() + [
        "--windows-disable-console",
        "--mingw64",
        f"--windows-product-name={APP_NAME}",
        f"--windows-file-description={APP_NAME}",
        "--output-filename=mediaSiphon.exe",
        str(ENTRY),
    ]


def macos_args() -> list[str]:
    return common_args() + [
        "--macos-create-app-bundle",
        "--macos-disable-console",
        f"--macos-app-name={APP_NAME}",
        "--output-filename=mediaSiphon",
        str(ENTRY),
    ]


def linux_args() -> list[str]:
    return common_args() + [
        "--output-filename=mediaSiphon",
        str(ENTRY),
    ]


def build(clean: bool) -> int:
    ensure_frontend()
    ensure_engine()

    if clean and DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)

    if sys.platform == "win32":
        args = windows_args()
    elif sys.platform == "darwin":
        args = macos_args()
    else:
        args = linux_args()

    print("执行:", " ".join(args))
    return subprocess.call(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 mediaSiphon")
    parser.add_argument("--clean", action="store_true", help="打包前清理 dist")
    args = parser.parse_args()
    return build(args.clean)


if __name__ == "__main__":
    sys.exit(main())
