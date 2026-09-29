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
    "line",
    [
        "[2026-06-20 21:09:45] 沈曉棠",  # 無冒號
        "[2026-06-20 21:09:45] 沈曉棠：我來了",  # 全形冒號
        "[2026-06-20 21:09:45] 顧望舒： > page.31｜2026/03/05(四)｜19:20｜霧津港",  # 全形冒號 + 狀態欄時間
        "[2026-06-20 21:09:45] : 沒有發話者",
        "[2026-13-40 21:09:45] 沈曉棠: 時間不存在",
    ],
)
def test_malformed_header_raises_with_line_no(line):
    with pytest.raises(LogFormatError, match="第 7 行"):
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
