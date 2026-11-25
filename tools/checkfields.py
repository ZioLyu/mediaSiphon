"""Verify the frontend Settings interface matches the backend dataclass fields."""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "siphon" / "settings.py"
FRONTEND = ROOT / "frontend" / "src" / "api" / "client.ts"


def backend_fields() -> list:
    tree = ast.parse(BACKEND.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SiphonSettings":
            return [n.target.id for n in node.body if isinstance(n, ast.AnnAssign)]
    return []


def frontend_fields() -> list:
    text = FRONTEND.read_text(encoding="utf-8")
    block = re.search(r"export interface Settings \{([\s\S]*?)\n\}", text)
    if not block:
        return []
    return re.findall(r"^\s{2}([a-z_]+):", block.group(1), re.M)


def main() -> int:
    backend = backend_fields()
    frontend = frontend_fields()

    if not backend or not frontend:
        print("could not parse field lists", len(backend), len(frontend))
        return 1

    missing_in_client = sorted(set(backend) - set(frontend))
    extra_in_client = sorted(set(frontend) - set(backend))

    if missing_in_client:
        print("backend fields missing in client.ts:", missing_in_client)
    if extra_in_client:
        print("client.ts fields not in backend:", extra_in_client)
    if missing_in_client or extra_in_client:
        return 1

    print(f"settings fields aligned ({len(backend)} fields)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
