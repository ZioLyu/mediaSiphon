"""在没有安装 pytest 的环境里执行 tests/ 下的用例，作为本地自检。

支持最小集：@pytest.fixture、pytest.raises、tmp_path、以及带参数的 fixture（单层依赖）。
"""

import contextlib
import inspect
import sys
import tempfile
import traceback
import types
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_shim() -> types.ModuleType:
    module = types.ModuleType("pytest")

    def fixture(*args, **kwargs):
        def decorator(fn):
            fn._is_fixture = True
            return fn

        return decorator

    @contextlib.contextmanager
    def raises(exc):
        try:
            yield
        except exc:
            return
        raise AssertionError(f"expected {getattr(exc, '__name__', exc)} to be raised")

    module.fixture = fixture
    module.raises = raises
    return module


class Resolver:
    def __init__(self, namespace: dict, workspace: Path):
        self.namespace = namespace
        self.workspace = workspace
        self.cache: dict = {}

    def provide(self, name: str, seen: tuple = ()):
        if name in self.cache:
            return self.cache[name]
        if name in seen:
            raise RuntimeError(f"circular fixture: {name}")

        if name in ("tmp_path", "tmpdir"):
            path = self.workspace / f"case-{uuid.uuid4().hex[:8]}"
            path.mkdir(parents=True, exist_ok=True)
            self.cache[name] = path
            return path

        fn = self.namespace.get(name)
        if fn is None or not callable(fn):
            raise RuntimeError(f"unknown fixture: {name}")

        kwargs = self._dependencies(fn, seen + (name,))
        value = fn(**kwargs)
        if inspect.isgenerator(value):
            value = next(value)
        self.cache[name] = value
        return value

    def _dependencies(self, fn, seen) -> dict:
        kwargs = {}
        params = inspect.signature(fn).parameters
        for arg_name in params:
            if arg_name in ("self", "cls"):
                continue
            kwargs[arg_name] = self.provide(arg_name, seen)
        return kwargs


def run_module(path: Path, workspace: Path) -> tuple:
    namespace = {"__name__": "siphon_test_module", "__file__": str(path)}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)

    passed, failures = 0, []
    for name, fn in list(namespace.items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        resolver = Resolver(namespace, workspace)
        try:
            fn(**resolver._dependencies(fn, ()))
            passed += 1
        except Exception:
            failures.append((name, traceback.format_exc(limit=3)))
    return passed, failures


def main() -> int:
    sys.modules["pytest"] = build_shim()
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    total, problems = 0, []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as workspace:
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            passed, failures = run_module(path, Path(workspace))
            total += passed
            problems.extend((path.name, case, detail) for case, detail in failures)

    for module_name, case, detail in problems:
        print(f"FAIL {module_name}::{case}")
        print(detail)
    print(f"passed={total} failed={len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
