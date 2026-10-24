"""novel_log 去重:同線、同秒、同發話者視為同一則,不管從哪個來源匯入都只存一次。"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

import util.migration as migration
from service.novel_log_service import insert_new_novel_logs, parse_and_import
from tests.helpers import add_character
from util.crud.novel_log import get_novel_logs
from util.models import NovelLog

LOG = """[2026-06-20 21:09:45] 沈曉棠: 我來了
[2026-06-20 21:09:46] 顧望舒: > page.31
「門閂就麻煩妳了。」
"""

# 與 LOG 重疊一則(page.31),再多一則新的
LOG_OVERLAP = """[2026-06-20 21:09:45] 沈曉棠: 我來了
[2026-06-20 21:09:46] 顧望舒: > page.31
「門閂就麻煩妳了。」
[2026-06-20 21:12:00] 沈曉棠: 好
[2026-06-20 21:12:01] 顧望舒: > page.32
"""


def _log(cid, time, sender, content="x"):
    return NovelLog(
        character_id=cid, raw_log_time=datetime.fromisoformat(time), sender=sender, content=content
    )


def test_reimport_same_file_inserts_nothing(db):
    cid = add_character(db)
    parse_and_import(cid, "沈曉棠", LOG, db)
    result = parse_and_import(cid, "沈曉棠", LOG, db)
    assert (result.inserted, result.skipped) == (0, 2)
    assert db.query(NovelLog).count() == 2


def test_overlapping_export_only_adds_new_turns(db):
    cid = add_character(db)
    parse_and_import(cid, "沈曉棠", LOG, db)
    result = parse_and_import(cid, "沈曉棠", LOG_OVERLAP, db)
    assert (result.inserted, result.skipped) == (2, 2)
    assert db.query(NovelLog).count() == 4


def test_same_second_different_sender_is_not_duplicate(db):
    # user 與角色回覆常落在同一秒,鍵裡少了 sender 就會誤刪
    cid = add_character(db)
    result = insert_new_novel_logs(
        db, cid, [_log(cid, "2026-06-20 21:09:45", "沈曉棠"), _log(cid, "2026-06-20 21:09:45", "顧望舒")]
    )
    assert (result.inserted, result.skipped) == (2, 0)


def test_same_second_turns_keep_import_order(db):
    # 唯一索引含 sender:只照 raw_log_time 排序時 SQLite 會走索引、同秒改依 sender 字序
    # (B 排在 Z 前面 → 角色回覆跑到 user 發話前面)
    cid = add_character(db)
    log = "[2026-06-20 21:09:45] Z: 先說\n[2026-06-20 21:09:45] B: 後回\n"
    parse_and_import(cid, "Z", log, db)
    assert [r.sender for r in get_novel_logs(db, cid)] == ["Z", "B"]


def test_other_character_thread_is_not_duplicate(db):
    cid1, cid2 = add_character(db, "A"), add_character(db, "B")
    insert_new_novel_logs(db, cid1, [_log(cid1, "2026-06-20 21:09:45", "沈曉棠")])
    result = insert_new_novel_logs(db, cid2, [_log(cid2, "2026-06-20 21:09:45", "沈曉棠")])
    assert result.inserted == 1


def test_duplicate_within_one_batch_is_skipped(db):
    cid = add_character(db)
    result = insert_new_novel_logs(
        db, cid, [_log(cid, "2026-06-20 21:09:45", "沈曉棠"), _log(cid, "2026-06-20 21:09:45", "沈曉棠")]
    )
    assert (result.inserted, result.skipped) == (1, 1)


def test_empty_batch(db):
    cid = add_character(db)
    assert insert_new_novel_logs(db, cid, []).inserted == 0


def test_unique_index_is_the_last_line_of_defense(db):
    # 繞過 service 直接寫入,DB 也擋得住
    cid = add_character(db)
    db.add_all([_log(cid, "2026-06-20 21:09:45", "沈曉棠"), _log(cid, "2026-06-20 21:09:45", "沈曉棠")])
    with pytest.raises(IntegrityError):
        db.flush()


def test_router_reports_skipped(client, db):
    cid = add_character(db)
    params = {"character_id": cid, "user_name": "沈曉棠"}
    files = {"file": ("log.txt", LOG.encode())}
    client.post("/novel_logs/import", params=params, files=files)
    res = client.post("/novel_logs/import", params=params, files={"file": ("log.txt", LOG.encode())})
    # 全被略過也回這篇的頭尾,UI 才能直接帶去查詢/建 run
    assert res.json() == {
        "import_cnt": 0,
        "skipped_cnt": 2,
        "range_start": "2026-06-20T21:09:45",
        "range_end": "2026-06-20T21:09:46",
    }


def test_import_range_covers_whole_file_not_only_new_turns(db):
    cid = add_character(db)
    parse_and_import(cid, "沈曉棠", LOG, db)
    result = parse_and_import(cid, "沈曉棠", LOG_OVERLAP, db)
    assert (result.range_start, result.range_end) == (
        datetime(2026, 6, 20, 21, 9, 45),
        datetime(2026, 6, 20, 21, 12, 1),
    )


def test_router_empty_file_has_no_range(client, db):
    cid = add_character(db)
    params = {"character_id": cid, "user_name": "沈曉棠"}
    res = client.post("/novel_logs/import", params=params, files={"file": ("log.txt", b"")})
    assert res.json() == {"import_cnt": 0, "skipped_cnt": 0, "range_start": None, "range_end": None}


def _old_schema_engine(tmp_path, duplicate: bool):
    # 模擬索引上線前的既有 DB:novel_log 表已存在、沒有唯一索引
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE character (character_id INTEGER PRIMARY KEY, name VARCHAR)")
        conn.exec_driver_sql(
            "CREATE TABLE novel_log (novel_log_id INTEGER PRIMARY KEY, character_id INTEGER, "
            "raw_log_time DATETIME NOT NULL, sender VARCHAR NOT NULL, content VARCHAR, created_at DATETIME)"
        )
        rows = 2 if duplicate else 1
        for _ in range(rows):
            conn.exec_driver_sql(
                "INSERT INTO novel_log (character_id, raw_log_time, sender) VALUES (1, '2026-06-20 21:09:45.000000', 'A')"
            )
    return engine


def test_migration_adds_index_to_existing_table(tmp_path, monkeypatch):
    engine = _old_schema_engine(tmp_path, duplicate=False)
    monkeypatch.setattr(migration, "engine", engine)
    migration.init_db()
    migration.init_db()  # 可重複執行
    names = {i["name"] for i in inspect(engine).get_indexes("novel_log")}
    assert "uq_novel_log_char_time_sender" in names


def test_migration_stops_with_message_when_duplicates_exist(tmp_path, monkeypatch):
    engine = _old_schema_engine(tmp_path, duplicate=True)
    monkeypatch.setattr(migration, "engine", engine)
    with pytest.raises(SystemExit, match="重複資料"):
        migration.init_db()
