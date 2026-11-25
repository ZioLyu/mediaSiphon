"""Cross-check icon names used in templates against the Icon component union type."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    icon_file = ROOT / "frontend" / "src" / "components" / "Icon.vue"
    text = icon_file.read_text(encoding="utf-8")

    match = re.search(r"type Name\s*=([\s\S]*?)\n\n", text)
    if not match:
        print("cannot locate Name union in Icon.vue")
        return 1

    declared = set(re.findall(r"'([a-z-]+)'", match.group(1)))
    # 图标名可能带连字符（如 panel-left），TypeScript 里必须加引号，两种写法都要识别
    defined = set(re.findall(r"^\s{2}'?([a-z-]+)'?:\s*'", text, re.M))
    missing_defs = declared - defined
    extra_defs = defined - declared

    used = set()
    for path in (ROOT / "frontend" / "src").rglob("*.vue"):
        body = path.read_text(encoding="utf-8")
        for tag in re.findall(r"<Icon\b[^>]*>", body):
            found = re.search(r'\bname="([a-z-]+)"', tag)
            if found:
                used.add(found.group(1))
        for expr in re.findall(r":name=\"([^\"]+)\"", body):
            used |= set(re.findall(r"'([a-z-]+)'", expr))

    report = []
    if missing_defs:
        report.append(f"declared but no path: {sorted(missing_defs)}")
    if extra_defs:
        report.append(f"path without declaration: {sorted(extra_defs)}")
    unknown = used - declared
    if unknown:
        report.append(f"used but not declared: {sorted(unknown)}")

    for line in report:
        print(" -", line)
    if report:
        return 1
    print(f"icon names OK ({len(declared)} icons, {len(used)} used)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
