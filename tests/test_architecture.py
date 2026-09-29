"""守住「同一條規則只有一個出處」:散掉時直接讓測試失敗,而不是等下次整包掃描才發現。"""
import ast
from pathlib import Path

from util.paths import REPO_DIR

SOURCE_DIRS = ("api", "service", "util", "scripts", "evals")


def _sources():
    for d in SOURCE_DIRS:
        yield from (REPO_DIR / d).rglob("*.py")


def _env_reads(path: Path) -> list[str]:
    hits = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and node.attr in ("getenv", "environ"):
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                hits.append(f"{path.relative_to(REPO_DIR)}:{node.lineno} os.{node.attr}")
        if isinstance(node, ast.ImportFrom) and node.module == "dotenv":
            hits.append(f"{path.relative_to(REPO_DIR)}:{node.lineno} from dotenv")
    return hits


def test_env_is_read_only_in_config():
    config = REPO_DIR / "util" / "config.py"
    hits = [h for p in _sources() if p != config for h in _env_reads(p)]
    assert hits == [], "環境變數/.env 只能在 util/config.py 讀,改用 config 的函式:\n" + "\n".join(hits)
