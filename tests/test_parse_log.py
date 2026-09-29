"""log 匯入:標題行判定與解析是同一套規則,格式外的標題行整份擋下並指出行號。"""
import pytest

from service.novel_log_service import parse_and_import
from tests.helpers import add_character
from util.models import NovelLog
from util.parse_log_util import LogFormatError, parse_log_header_line

LOG = """匯出表頭,略過
[2026-06-20 21:02:11] Scene (start):
場景描述
[2026-06-20 21:09:45] 沈曉棠: 我來了
[2026-06-20 21:09:46] 顧望舒: > page.31
服裝：深藍毛衣
「門閂就麻煩妳了。」
"""


def test_parse_header_line():
    assert parse_log_header_line("[2026-06-20 21:09:45] 沈曉棠: 我來了: 真的") == (
        parse_log_header_line("  [2026-06-20 21:09:45]沈曉棠:我來了: 真的  ")
    )
    time, sender, rest = parse_log_header_line("[2026-06-20 21:09:45] 沈曉棠: 我來了: 真的")
    assert (str(time), sender, rest) == ("2026-06-20 21:09:45", "沈曉棠", "我來了: 真的")


def test_non_header_line_is_content():
    assert parse_log_header_line("服裝：深藍毛衣") is None
    assert parse_log_header_line("[2026-06-20] 沈曉棠: 日期不完整不算標題") is None


@pytest.mark.parametrize(
    "line, reason",
    [
        ("[2026-06-20 21:09:45] 沈曉棠", "缺「發話者:」"),  # 無冒號
        ("[2026-06-20 21:09:45]:", "缺「發話者:」"),
        ("[2026-06-20 21:09:45] : 沒有發話者", "缺「發話者:」"),  # 舊版會存成 sender=""
        ("[2026-06-20 21:09:45] 沈曉棠：我來了", "全形冒號"),  # 整行沒有半形冒號
        ("[2026-06-20 21:09:45] 顧望舒： > page.31｜2026/03/05(四)｜19:20｜霧津港", "全形冒號"),  # 舊版 sender 變亂碼
        ("[2026-06-20 21:09:45] 場景：開場: 內容", "全形冒號"),  # 取捨:名字本身含「：」也擋
        ("[2026-13-40 21:09:45] 沈曉棠: 時間不存在", "時間無法解析"),
    ],
)
def test_malformed_header_raises_with_line_no_and_reason(line, reason):
    with pytest.raises(LogFormatError, match=f"第 7 行.*{reason}"):
        parse_log_header_line(line, 7)


def test_import_pairs_user_with_next_character_turn(db):
    cid = add_character(db)
    assert parse_and_import(cid, "沈曉棠", LOG, db) == 3
    rows = db.query(NovelLog).order_by(NovelLog.novel_log_id).all()
    assert [(r.sender, r.content) for r in rows] == [
        ("Scene (start)", "場景描述"),
        ("沈曉棠", "我來了"),
        ("顧望舒", "> page.31\n服裝：深藍毛衣\n「門閂就麻煩妳了。」"),
    ]


def test_import_rejects_whole_file_on_malformed_header(db):
    cid = add_character(db)
    bad = LOG + "[2026-06-20 21:10:00] 沈曉棠：全形冒號\n"
    with pytest.raises(LogFormatError, match="第 8 行"):
        parse_and_import(cid, "沈曉棠", bad, db)
    assert db.query(NovelLog).count() == 0


def test_router_returns_400_on_malformed_header(client, db):
    cid = add_character(db)
    res = client.post(
        "/novel_logs/import",
        params={"character_id": cid, "user_name": "沈曉棠"},
        files={"file": ("log.txt", "[2026-06-20 21:09:45] 沈曉棠\n".encode())},
    )
    assert res.status_code == 400
    assert "第 1 行" in res.json()["detail"]


def test_indented_timestamp_line_is_header(db):
    # 判定與解析都看 strip 後的行;舊版判定看原始行,縮排的時間戳行會被併進上一筆內文
    cid = add_character(db)
    log = "[2026-06-20 21:09:46] 顧望舒: 第一句\n  [2026-06-20 21:10:00] 顧望舒: 第二句\n"
    assert parse_and_import(cid, "沈曉棠", log, db) == 2


def test_trailing_user_turn_without_reply_is_not_imported(db):
    # 既有行為:user 發話要等下一個角色回覆才一起入庫,檔尾沒有回覆的 user turn 不存
    cid = add_character(db)
    log = "[2026-06-20 21:09:46] 顧望舒: 回覆\n[2026-06-20 21:10:00] 沈曉棠: 還沒被回的話\n"
    assert parse_and_import(cid, "沈曉棠", log, db) == 1
    assert [r.sender for r in db.query(NovelLog)] == ["顧望舒"]
