"""静态检查：确认模块间引用的符号都真实存在（不需要第三方依赖）。"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def module_symbols(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def main() -> int:
    files = {p.stem: p for p in (ROOT / "siphon").glob("*.py") if p.name != "__init__.py"}
    symbols = {stem: module_symbols(path) for stem, path in files.items()}

    problems = []
    for stem, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                target = node.module
                if target not in symbols:
                    problems.append(f"{path.name}: 未知模块 .{target}")
                    continue
                for alias in node.names:
                    if alias.name not in symbols[target]:
                        problems.append(f"{path.name}: .{target} 缺少 {alias.name}")

    if problems:
        print("发现问题：")
        for item in problems:
            print(" -", item)
        return 1

    print("模块引用检查通过，共", len(files), "个模块")
    return 0


if __name__ == "__main__":
    sys.exit(main())
