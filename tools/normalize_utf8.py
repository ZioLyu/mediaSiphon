"""Normalize all text sources to UTF-8 (run after editing on Windows)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTS = {".py", ".ts", ".vue", ".css", ".json", ".toml", ".md", ".html", ".txt", ".js", ".cjs"}
SKIP = {"node_modules", ".git", "dist", "runtime", "__pycache__", "build"}


def main() -> int:
    fixed = []
    broken = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in EXTS:
            continue
        if SKIP & set(path.parts):
            continue
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
            continue
        except UnicodeDecodeError:
            pass
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            broken.append(str(path))
            continue
        path.write_bytes(text.encode("utf-8"))
        fixed.append(str(path))

    for item in fixed:
        print("fixed:", item)
    for item in broken:
        print("BROKEN (cannot decode):", item)
    print(f"done. fixed={len(fixed)} broken={len(broken)}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
