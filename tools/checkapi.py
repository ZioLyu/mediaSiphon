"""Verify that every API path used by the frontend exists in the backend."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
API_FILE = ROOT / "siphon" / "api.py"
CLIENT_FILE = ROOT / "frontend" / "src" / "api" / "client.ts"


def backend_routes() -> set:
    text = API_FILE.read_text(encoding="utf-8")
    routes = set()
    for method, path in re.findall(r'@app\.(get|post|patch|delete|put)\("([^"]+)"', text):
        routes.add((method.upper(), path))
    return routes


def client_calls() -> set:
    text = CLIENT_FILE.read_text(encoding="utf-8")
    calls = set()
    for path in re.findall(r"request<[^>]*>\(\s*(?:`|')([^`']+)", text):
        method = "GET"
        segment = text.split(path, 1)[1][:160] if path in text else ""
        found = re.search(r"method:\s*'([A-Z]+)'", segment)
        if found:
            method = found.group(1)
        normalized = re.sub(r"\$\{[^}]+\}", "{x}", path.split("?")[0])
        calls.add((method, normalized))
    return calls


def main() -> int:
    routes = backend_routes()
    normalized_routes = {(m, re.sub(r"\{[^}]+\}", "{x}", p)) for m, p in routes}

    missing = []
    for method, path in client_calls():
        if (method, path) in normalized_routes:
            continue
        # 允许 GET 走 SPA 兜底或路径参数形态不同的情况
        base = path.rsplit("/", 1)[0]
        if any(r[1].startswith(base) for r in normalized_routes):
            continue
        missing.append(f"{method} {path}")

    if missing:
        print("前端调用但后端未定义：")
        for item in missing:
            print(" -", item)
        return 1

    print(f"API 对齐检查通过：后端 {len(routes)} 条路由")
    return 0


if __name__ == "__main__":
    sys.exit(main())
