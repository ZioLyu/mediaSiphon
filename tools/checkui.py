"""Check frontend import paths and Vue SFC structure."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"
issues = []


def check_vue(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    opens = len(re.findall(r"<template[\s>]", text))
    closes = text.count("</template>")
    if opens != closes:
        issues.append(f"{path}: template tag mismatch ({opens} open / {closes} close)")
    if text.count("<script setup") > 1:
        issues.append(f"{path}: multiple script setup blocks")
    if "<script setup" in text and "</script>" not in text:
        issues.append(f"{path}: unclosed script block")
    if "<style scoped>" in text and "</style>" not in text:
        issues.append(f"{path}: unclosed style block")
    for spec in re.findall(r"from\s+['\"]([^'\"]+)['\"]", text):
        if not spec.startswith("."):
            continue
        base = (path.parent / spec).resolve()
        candidates = [base.with_suffix(".vue"), base.with_suffix(".ts"), base / "index.ts", base]
        if not any(c.exists() for c in candidates):
            issues.append(f"{path}: missing module {spec}")


def check_ts(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    for spec in re.findall(r"from\s+['\"]([^'\"]+)['\"]", text):
        if not spec.startswith("."):
            continue
        base = (path.parent / spec).resolve()
        candidates = [base.with_suffix(".ts"), base / "index.ts", base]
        if not any(c.exists() for c in candidates):
            issues.append(f"{path}: missing module {spec}")


def main() -> int:
    for path in sorted(SRC.rglob("*.vue")):
        check_vue(path)
    for path in sorted(SRC.rglob("*.ts")):
        check_ts(path)

    if issues:
        for item in issues:
            print(" -", item)
        return 1
    print("frontend structure OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
