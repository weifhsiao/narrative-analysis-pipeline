"""守住「同一條規則只有一個出處」:散掉時直接讓測試失敗,而不是等下次整包掃描才發現。"""
import ast

import pytest

from util.paths import REPO_DIR

SOURCE_DIRS = ("api", "service", "util", "scripts", "evals")


def _sources():
    for d in SOURCE_DIRS:
        yield from (REPO_DIR / d).rglob("*.py")


def _env_reads(source: str) -> list[str]:
    """防手滑,不防刻意繞過(import os as _os、__import__ 之類抓不到)。"""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in ("getenv", "environ"):
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                hits.append(f"{node.lineno} os.{node.attr}")
        elif isinstance(node, ast.ImportFrom) and node.module == "dotenv":
            hits.append(f"{node.lineno} from dotenv")
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            if any(a.name in ("getenv", "environ") for a in node.names):
                hits.append(f"{node.lineno} from os import getenv/environ")
        elif isinstance(node, ast.Import) and any(a.name == "dotenv" for a in node.names):
            hits.append(f"{node.lineno} import dotenv")
    return hits


def test_env_is_read_only_in_config():
    config = REPO_DIR / "util" / "config.py"
    hits = [
        f"{p.relative_to(REPO_DIR)}:{h}"
        for p in _sources()
        if p != config
        for h in _env_reads(p.read_text(encoding="utf-8"))
    ]
    assert hits == [], "環境變數/.env 只能在 util/config.py 讀,改用 config 的函式:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    "source",
    [
        'import os\nos.getenv("X")',
        'import os\nos.environ["X"]',
        'from os import getenv',
        'from dotenv import load_dotenv',
        'import dotenv',
    ],
)
def test_env_guard_catches(source):
    assert _env_reads(source)


def test_env_guard_ignores_comments_and_strings():
    assert _env_reads('# os.getenv("X")\n"""load_dotenv()"""\nimport os\nos.path.join("a")') == []
