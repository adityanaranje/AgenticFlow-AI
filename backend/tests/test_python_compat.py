"""Guard the interpreter floor of everything we ship or run.

The backend, the operational scripts and this test suite must all work on the
oldest supported interpreter (see ``requires-python`` / ruff ``target-version``
in ``pyproject.toml``). A single 3.11+ only name is enough to stop the API
server — or the test suite — from starting on that runtime, and the breakage is
invisible to a developer whose own interpreter is newer, so it is checked
statically instead of relying on the interpreter running the tests.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

SOURCE_DIRS = (
    BACKEND_ROOT / "app",
    BACKEND_ROOT / "tests",
    REPO_ROOT / "scripts",
)

# Dotted attribute paths (``module.attr``) that only exist from Python 3.11/3.12 on.
BANNED_ATTRIBUTES = {
    # Python 3.11
    "datetime.UTC",
    "asyncio.Runner",
    "asyncio.TaskGroup",
    "asyncio.timeout",
    "contextlib.chdir",
    "enum.ReprEnum",
    "enum.StrEnum",
    "hashlib.file_digest",
    "tomllib.load",
    "tomllib.loads",
    "typing.LiteralString",
    "typing.Never",
    "typing.Self",
    "typing.TypeVarTuple",
    "typing.Unpack",
    "typing.assert_never",
    "typing.dataclass_transform",
    # Python 3.12
    "itertools.batched",
    "pathlib.Path.walk",
    "typing.override",
}

# ``from <module> import <name>`` pairs that require a newer interpreter.
BANNED_IMPORTS = {
    "asyncio": {"Runner", "TaskGroup", "timeout"},
    "contextlib": {"chdir"},
    "datetime": {"UTC"},
    "enum": {"ReprEnum", "StrEnum"},
    "hashlib": {"file_digest"},
    "itertools": {"batched"},
    "tomllib": {"load", "loads"},
    "typing": {
        "LiteralString",
        "Never",
        "Self",
        "TypeVarTuple",
        "Unpack",
        "assert_never",
        "dataclass_transform",
        "override",
    },
}
BANNED_MODULES = {"tomllib"}  # 3.11+ module, no 3.10 equivalent in the stdlib


def _iter_source_files():
    for directory in SOURCE_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            if "__pycache__" not in path.parts:
                yield path


def _dotted_name(node: ast.AST) -> str | None:
    """Return ``a.b.c`` for a Name/Attribute chain, otherwise None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _violations(tree: ast.AST, relpath: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)):
            name = _dotted_name(node)
            if name in BANNED_ATTRIBUTES:
                found.append(f"{relpath}:{node.lineno} uses {name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            banned = BANNED_IMPORTS.get(node.module, set())
            for alias in node.names:
                if alias.name in banned:
                    found.append(f"{relpath}:{node.lineno} imports {node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BANNED_MODULES:
                    found.append(f"{relpath}:{node.lineno} imports {alias.name}")
    return found


def test_no_newer_than_floor_stdlib_apis():
    offenders: list[str] = []
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders.extend(_violations(tree, str(path.relative_to(REPO_ROOT))))

    assert not offenders, (
        "Code uses APIs newer than the supported Python floor "
        "(use the 3.10-compatible spelling instead, e.g. "
        "`datetime.now(timezone.utc)` rather than `datetime.now(UTC)`):\n  "
        + "\n  ".join(offenders)
    )


def test_guard_actually_detects_the_known_breakage():
    """The checker above must catch the exact API that broke a 3.10 runtime."""
    source = "from datetime import UTC\nvalue = UTC\n"
    assert _violations(ast.parse(source), "sample.py")

    source = "import datetime\nvalue = datetime.now(datetime.UTC)\n"
    assert _violations(ast.parse(source), "sample.py")

    source = "from datetime import timezone\nvalue = timezone.utc\n"
    assert not _violations(ast.parse(source), "sample.py")


def test_declared_floor_matches_lint_and_type_check_floor():
    """``requires-python``, ruff and mypy must all agree on the floor."""
    text = PYPROJECT.read_text(encoding="utf-8")
    requires = re.search(r'requires-python\s*=\s*">=([\d.]+)"', text)
    ruff_target = re.search(r'target-version\s*=\s*"py(\d)(\d+)"', text)
    mypy_target = re.search(r'python_version\s*=\s*"([\d.]+)"', text)
    assert requires and ruff_target and mypy_target, text

    expected = requires.group(1)
    ruff_floor = f"{ruff_target.group(1)}.{ruff_target.group(2)}"
    assert ruff_floor == expected, (ruff_floor, expected)
    assert mypy_target.group(1) == expected, (mypy_target.group(1), expected)
    assert expected.startswith("3.1"), expected  # sanity: a real floor, not ">=2"
