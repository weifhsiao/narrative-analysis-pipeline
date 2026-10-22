"""訊息清單匯入:時間/內容正規化後要與 txt 匯入的同一則對得上,頁碼斷層只提醒不擋。"""
import json
from datetime import datetime

import pytest

import scripts.import_messages as cli
from service.message_import_service import (
    Message,
    MessageImportError,
    format_report,
    import_messages,
    normalize_time,
)
from service.novel_log_service import parse_and_import
from tests.helpers import add_character
from util.models import NovelLog

# txt 匯出:p.31～32
TXT = """[2026-06-20 21:09:45] 沈曉棠: 我來了
[2026-06-20 21:09:46] 顧望舒: > page.31｜2026/03/05(四)｜19:20｜霧津港
服裝：深藍毛衣
「門閂就麻煩妳了。」
[2026-06-20 21:12:00] 沈曉棠: 好
[2026-06-20 21:12:01] 顧望舒: > page.32｜2026/03/05(四)｜19:25｜霧津港
"""


def _msg(sender, time, content):
    return Message(sender=sender, time=datetime.fromisoformat(time), content=content)


# 同一段的分享版:UTC、帶毫秒、段落間有空行
SHARED_31 = [
    _msg("沈曉棠", "2026-06-20T13:09:45.401Z", "我來了"),
    _msg("顧望舒", "2026-06-20T13:09:46.359Z", "> page.31｜2026/03/05(四)｜19:20｜霧津港\n服裝：深藍毛衣\n\n「門閂就麻煩妳了。」\n"),
]


def _page(sender_time, page):
    return _msg("顧望舒", sender_time, f"> page.{page}｜2026/03/05(四)｜霧津港\n內容")


def test_normalize_time():
    assert normalize_time(datetime.fromisoformat("2026-06-20T13:09:45.401Z")) == datetime(2026, 6, 20, 21, 9, 45)
    assert normalize_time(datetime(2026, 6, 20, 21, 9, 45, 999)) == datetime(2026, 6, 20, 21, 9, 45)


def test_shared_copy_of_imported_txt_is_all_skipped(db):
    cid = add_character(db, "顧望舒")
    parse_and_import(cid, "沈曉棠", TXT, db)
    report = import_messages(db, cid, SHARED_31, dry_run=False)
    assert (report.inserted, report.skipped) == (0, 2)
    assert db.query(NovelLog).count() == 4


def test_content_is_cleaned_like_txt_import(db):
    cid = add_character(db, "顧望舒")
    import_messages(db, cid, SHARED_31, dry_run=False)
    row = db.query(NovelLog).filter_by(sender="顧望舒").one()
    assert row.content == "> page.31｜2026/03/05(四)｜19:20｜霧津港\n服裝：深藍毛衣\n「門閂就麻煩妳了。」"
    assert row.raw_log_time == datetime(2026, 6, 20, 21, 9, 46)


def test_dry_run_reports_without_writing(db):
    cid = add_character(db, "顧望舒")
    report = import_messages(db, cid, SHARED_31)
    assert report.dry_run and report.inserted == 2 and report.batch_created_at is None
    assert db.query(NovelLog).count() == 0


def test_one_batch_shares_created_at(db):
    cid = add_character(db, "顧望舒")
    report = import_messages(db, cid, SHARED_31, dry_run=False)
    assert {r.created_at for r in db.query(NovelLog)} == {report.batch_created_at}


def test_gap_after_db_tail_is_warned_not_blocked(db):
    cid = add_character(db, "顧望舒")
    parse_and_import(cid, "沈曉棠", TXT, db)  # DB 到 p.32
    report = import_messages(db, cid, [_page("2026-06-21T21:00:00", 36)], dry_run=False)
    assert report.inserted == 1
    assert any("缺 p.33～35" in w for w in report.warnings)


def test_gap_before_next_db_segment_is_warned(db):
    # 回補較早的一段:要跟 DB 後面那段接得上
    cid = add_character(db, "顧望舒")
    parse_and_import(cid, "沈曉棠", TXT, db)  # p.31 在 21:09:46
    report = import_messages(db, cid, [_page("2026-06-20T20:00:00", 28)])
    assert any("缺 p.29～30" in w for w in report.warnings)


def test_continuous_pages_have_no_warning(db):
    cid = add_character(db, "顧望舒")
    parse_and_import(cid, "沈曉棠", TXT, db)
    report = import_messages(db, cid, [_page("2026-06-21T21:00:00", 33), _page("2026-06-21T21:05:00", 34)])
    assert report.warnings == []
    assert (report.first_page, report.last_page) == (33, 34)


def test_jump_inside_batch_is_warned(db):
    cid = add_character(db, "顧望舒")
    report = import_messages(db, cid, [_page("2026-06-21T21:00:00", 33), _page("2026-06-21T21:05:00", 35)])
    assert report.warnings == ["本批中間缺 p.34"]


def test_old_page_marker_and_headerless_reply(db):
    # 舊格式 `> P.174`;沒狀態欄的回覆不影響判斷
    cid = add_character(db, "顧望舒")
    msgs = [
        _msg("顧望舒", "2026-06-21T21:00:00", "> P.174｜霧津港\n內容"),
        _msg("顧望舒", "2026-06-21T21:01:00", "*沒有狀態欄的回覆*"),
        _msg("顧望舒", "2026-06-21T21:02:00", "> page.175｜霧津港"),
    ]
    report = import_messages(db, cid, msgs)
    assert (report.first_page, report.last_page, report.warnings) == (174, 175, [])


def test_no_page_at_all_says_so(db):
    cid = add_character(db, "顧望舒")
    report = import_messages(db, cid, [_msg("沈曉棠", "2026-06-21T21:00:00", "只有對話")])
    assert report.warnings == ["本批找不到頁碼(狀態欄),無法檢查斷層"]
    assert "無頁碼" in format_report(report)


def test_source_character_name_mismatch_is_warned(db):
    cid = add_character(db, "顧望舒_rerun")
    assert not import_messages(db, cid, SHARED_31, source_character_name="顧望舒").warnings
    other = add_character(db, "陸陽")
    report = import_messages(db, other, SHARED_31, source_character_name="顧望舒")
    assert any("character_id" in w for w in report.warnings)


@pytest.mark.parametrize("cid, msgs, reason", [(999, SHARED_31, "不存在"), (None, [], "空的")])
def test_bad_input_raises(db, cid, msgs, reason):
    cid = cid or add_character(db)
    with pytest.raises(MessageImportError, match=reason):
        import_messages(db, cid, msgs)


def test_blank_sender_raises(db):
    cid = add_character(db)
    with pytest.raises(MessageImportError, match="第 1 則缺發話者"):
        import_messages(db, cid, [_msg(" ", "2026-06-21T21:00:00", "x")])


PAYLOAD = {
    "character_name": "顧望舒",
    "messages": [{"sender": "沈曉棠", "time": "2026-06-20T13:09:45.401Z", "content": "我來了"}],
}


def test_router_dry_run_then_write(client, db):
    cid = add_character(db, "顧望舒")
    res = client.post("/novel_logs/import-messages", params={"character_id": cid}, json=PAYLOAD)
    assert res.status_code == 200
    assert res.json()["dry_run"] is True and res.json()["inserted"] == 1
    assert db.query(NovelLog).count() == 0

    res = client.post("/novel_logs/import-messages", params={"character_id": cid, "dry_run": False}, json=PAYLOAD)
    assert res.json()["inserted"] == 1 and res.json()["batch_created_at"]
    assert db.query(NovelLog).count() == 1


def test_router_400_on_unknown_character(client, db):
    res = client.post("/novel_logs/import-messages", params={"character_id": 999}, json=PAYLOAD)
    assert res.status_code == 400


def test_cli_dry_run_and_write(db, tmp_path, capsys):
    cid = add_character(db, "顧望舒")
    db.commit()  # CLI 自己開 session,要看得到這個角色
    path = tmp_path / "m.json"
    path.write_text(json.dumps(PAYLOAD, ensure_ascii=False), encoding="utf-8")

    assert cli.main([str(path), "--character-id", str(cid)]) == 0
    assert "dry-run" in capsys.readouterr().out
    assert cli.main([str(path), "--character-id", str(cid), "--write"]) == 0
    assert "已寫入" in capsys.readouterr().out
    assert db.query(NovelLog).count() == 1


BAD_JSON = [
    "not json",
    "[]",
    '{"messages": [{"sender": "a"}]}',
    '{"messages": [{"sender": "a", "time": "x", "content": ""}]}',
]


@pytest.mark.parametrize("raw", BAD_JSON)
def test_cli_rejects_bad_json(raw):
    with pytest.raises(cli.MessageImportError, match="JSON 格式不符"):
        cli.load_payload(raw)
