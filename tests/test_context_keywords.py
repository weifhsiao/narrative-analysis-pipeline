"""context 的 keywords(遊戲端檢索關鍵字):照輸入原樣存,可新增、修改、清空;舊 DB 用 util.migration 補欄位。"""
import pytest
from sqlalchemy import create_engine, inspect

import util.migration as migration
from tests.helpers import add_character

KEYWORDS = "初訪燈塔、潮汐表、單程票"


def _create(client, cid, **extra):
    body = {"character_id": cid, "context_type": "scenario", "context_content": "內容", **extra}
    return client.post("/character_contexts/", json=body).json()


def test_create_and_read_keywords(client, db):
    cid = add_character(db)
    created = _create(client, cid, keywords=f"  {KEYWORDS} \n")
    assert created["keywords"] == KEYWORDS  # 前後空白去掉,內容原樣
    assert client.get(f"/character_contexts/{created['context_id']}").json()["keywords"] == KEYWORDS


def test_keywords_optional(client, db):
    cid = add_character(db)
    assert _create(client, cid)["keywords"] is None


def test_patch_keywords_only_touches_keywords(client, db):
    cid = add_character(db)
    created = _create(client, cid, title="標題")
    res = client.patch(f"/character_contexts/{created['context_id']}", json={"keywords": "還書之約"}).json()
    assert (res["keywords"], res["title"], res["context_content"]) == ("還書之約", "標題", "內容")

    cleared = client.patch(f"/character_contexts/{created['context_id']}", json={"keywords": ""}).json()
    assert cleared["keywords"] == ""


def _old_engine(tmp_path, not_null_extra=False):
    # 模擬 keywords 上線前的 DB:character_context 少了 keywords 欄
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE character (character_id INTEGER PRIMARY KEY, name VARCHAR)")
        conn.exec_driver_sql(
            "CREATE TABLE character_context (context_id INTEGER PRIMARY KEY, character_id INTEGER, "
            "context_type VARCHAR NOT NULL, context_content VARCHAR NOT NULL, sort_order INTEGER, title VARCHAR, "
            "is_active BOOLEAN NOT NULL, created_at DATETIME, updated_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO character_context (character_id, context_type, context_content, is_active) "
            "VALUES (1, 'scenario', '既有內容', 1)"
        )
    return engine


def test_migration_adds_keywords_and_keeps_rows(tmp_path, monkeypatch):
    engine = _old_engine(tmp_path)
    monkeypatch.setattr(migration, "engine", engine)
    migration.init_db()
    migration.init_db()  # 可重複執行
    columns = {c["name"] for c in inspect(engine).get_columns("character_context")}
    assert "keywords" in columns
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT context_content, keywords FROM character_context").all()
    assert rows == [("既有內容", None)]


def test_migration_refuses_not_null_column(tmp_path, monkeypatch):
    # 缺的是 NOT NULL 欄位時不猜預設值,停下來
    engine = _old_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE novel_log (novel_log_id INTEGER PRIMARY KEY, character_id INTEGER, "
                             "raw_log_time DATETIME NOT NULL, content VARCHAR, created_at DATETIME)")  # 少了 sender
    monkeypatch.setattr(migration, "engine", engine)
    with pytest.raises(SystemExit, match="novel_log.sender"):
        migration.init_db()
