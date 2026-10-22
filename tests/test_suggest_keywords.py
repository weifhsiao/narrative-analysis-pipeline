"""關鍵字建議:送出內容與同線其他段已用的關鍵字,回傳整理過的候選詞;只建議不寫入。"""
from datetime import datetime
from pathlib import Path

import pytest

import service.keyword_service as keyword_service
from service.keyword_service import split_keywords, suggest_keywords
from service.prompt_service import parse_prompt_file, save_prompt
from tests.helpers import add_character
from util.models import CharacterContext, NovelLog

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "keywords.txt"


@pytest.fixture
def ai(fake_ai, monkeypatch):
    monkeypatch.setattr(keyword_service.ai_client, "get_client", lambda: fake_ai)
    return fake_ai


def _ctx(db, cid, content, keywords=None, active=True) -> int:
    row = CharacterContext(
        character_id=cid, context_type="scenario", context_content=content, keywords=keywords, is_active=active
    )
    db.add(row)
    db.flush()
    return row.context_id


@pytest.fixture
def setup(db):
    save_prompt(db, "keywords", *parse_prompt_file(PROMPT_FILE.read_text(encoding="utf-8")))
    cid = add_character(db)
    target = _ctx(db, cid, "燈塔圖書室修補《霧津潮汐誌》")
    _ctx(db, cid, "另一段在燈塔圖書室", keywords="單程票、守塔人日記")
    _ctx(db, cid, "停用的段提到潮汐表", keywords="不該出現", active=False)
    for sender in ("沈曉棠", "顧望舒", "Scene (start)", "Environment (system)"):
        db.add(NovelLog(character_id=cid, raw_log_time=datetime(2026, 6, 20, 21, 0), sender=sender, content="x"))
    db.flush()
    return target


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("潮汐表、Lighthouse、潮汐表", ["潮汐表", "Lighthouse"]),
        ("白沙嘴,借書登記，守塔人日記", ["白沙嘴", "借書登記", "守塔人日記"]),
        ("晚宴|手術｜出院\n拖鞋", ["晚宴", "手術", "出院", "拖鞋"]),
        (" 「燈塔」 、、 ", ["燈塔"]),
        (None, []),
    ],
)
def test_split_keywords_accepts_all_separators(raw, expected):
    assert split_keywords(raw) == expected


def test_prompt_gets_content_and_other_entries_keywords(db, ai, setup):
    ai.response = "燈塔圖書室、霧津潮汐誌、單程票"
    suggest_keywords(db, setup)
    prompt = ai.calls[0]["prompt"]
    assert "燈塔圖書室修補《霧津潮汐誌》" in prompt
    assert "單程票、守塔人日記" in prompt
    assert "不該出現" not in prompt  # 停用的段不算
    assert "另一段" not in prompt  # 只給關鍵字,不給其他段的內容
    assert "沈曉棠、顧望舒" in prompt  # 角色名 = 發話者扣掉系統訊息
    assert "Scene" not in prompt


def test_candidates_are_cleaned_and_flagged(db, ai, setup):
    ai.response = "燈塔圖書室、霧津潮汐誌,單程票|這是一整句話不是關鍵字所以應該被丟掉、霧津潮汐誌、顧望舒、潮汐表"
    result = suggest_keywords(db, setup)
    # (詞, 其他段關鍵字用過, 其他段內容也有, 含角色名);停用的段不算
    assert [(c.text, c.used_elsewhere, c.mentioned_elsewhere, c.has_name) for c in result.candidates] == [
        ("燈塔圖書室", False, True, False),
        ("霧津潮汐誌", False, False, False),
        ("單程票", True, False, False),
        ("顧望舒", False, False, True),
        ("潮汐表", False, False, False),
    ]
    assert result.usage.model == "fake-model-001"
    assert len(ai.calls) == 1


def test_retries_once_when_too_few_candidates(db, ai, setup):
    ai.response = "只有一個"
    result = suggest_keywords(db, setup)
    assert len(ai.calls) == 2
    assert result.warnings == ["AI 只給了 1 個可用的候選詞"]


def test_router_returns_candidates_without_saving(client, db, ai, setup):
    ai.response = "燈塔圖書室、霧津潮汐誌、單程票"
    res = client.post(f"/character_contexts/{setup}/suggest-keywords")
    assert res.status_code == 200
    body = res.json()
    assert [c["text"] for c in body["candidates"]] == ["燈塔圖書室", "霧津潮汐誌", "單程票"]
    assert (body["max_chars"], body["separator"]) == (30, "、")
    assert db.get(CharacterContext, setup).keywords is None


def test_router_404_for_unknown_context(client, db, ai, setup):
    assert client.post("/character_contexts/999/suggest-keywords").status_code == 404


def test_router_409_when_prompt_not_imported(client, db, ai):
    ctx = _ctx(db, add_character(db), "內容")
    res = client.post(f"/character_contexts/{ctx}/suggest-keywords")
    assert res.status_code == 409
    assert "import_prompts" in res.json()["detail"]


def test_router_502_on_ai_failure(client, db, ai, setup):
    ai.response = RuntimeError("quota exceeded")
    res = client.post(f"/character_contexts/{setup}/suggest-keywords")
    assert res.status_code == 502
    assert "quota exceeded" in res.json()["detail"]
