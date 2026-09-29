"""設定與路徑:值在呼叫當下讀 env、預設只有一個出處、路徑不隨 cwd 變。"""
import subprocess
import sys

import util.db_util as db_util
from util import config
from util.paths import REPO_DIR


def test_config_reads_env_at_call_time(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "model-a")
    assert config.gemini_model() == "model-a"
    monkeypatch.setenv("GEMINI_MODEL", "model-b")
    assert config.gemini_model() == "model-b"


def test_unset_model_falls_back_to_single_default(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert config.gemini_model() == config.DEFAULT_GEMINI_MODEL


def test_sql_echo_flag(monkeypatch):
    for value, expected in (("true", True), (" YES ", True), ("1", True), ("false", False), ("", False)):
        monkeypatch.setenv("SQL_ECHO", value)
        assert config.sql_echo() is expected


def test_quiet_sql_turns_off_engine_echo(monkeypatch):
    monkeypatch.setattr(db_util.engine, "echo", True)
    db_util.quiet_sql()
    assert db_util.engine.echo is False


def test_paths_do_not_depend_on_cwd(tmp_path):
    # 另起 process、cwd 設在別處:DB 仍指向 repo 的 data/,cwd 不產生任何檔案(create_engine 不會連線)
    out = subprocess.run(
        [sys.executable, "-c", "import util.db_util as d; print(d.DB_PATH)"],
        cwd=tmp_path,
        env={"PYTHONPATH": str(REPO_DIR)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == str(REPO_DIR / "data" / "novel.db")
    assert list(tmp_path.iterdir()) == []
