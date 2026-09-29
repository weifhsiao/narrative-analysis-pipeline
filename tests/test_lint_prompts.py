"""lint_prompts 細部案例：來源是 DB 裡各支 prompt 的最新版。"""
import pytest

from service.prompt_service import lint_prompts
from tests.helpers import add_character, add_context, add_prompt


def _issues(db, character_id=None, names=None):
    return [(i.level, i.prompt, i.message) for i in lint_prompts(db, character_id, names)]


def _levels(db, **kw):
    return [(lv, p) for lv, p, _ in _issues(db, **kw)]


def test_clean_prompt_has_no_issues(db):
    cid = add_character(db)
    add_context(db, cid, "relationship", "REL")
    add_prompt(db, "summary", "<relationship></relationship><log_content></log_content>")

    assert _issues(db, cid) == []


def test_unpaired_tag_is_error(db):
    add_context(db, add_character(db), "relationship", "REL")
    add_prompt(db, "summary", "<relationship>")

    [(level, prompt, message)] = [i for i in _issues(db) if i[0] == "ERROR"]
    assert (level, prompt) == ("ERROR", "summary")
    assert "不成對" in message


def test_unknown_type_is_error(db):
    add_context(db, add_character(db), "relationship", "REL")
    add_prompt(db, "summary", "<relationshp></relationshp>")

    assert ("ERROR", "summary") in _levels(db)


def test_leftover_placeholder_is_warn(db):
    add_prompt(db, "summary", "{log_content}")

    [(level, _, message)] = _issues(db)
    assert level == "WARN"
    assert "{log_content}" in message


def test_unrelated_braces_are_not_reported(db):
    add_prompt(db, "summary", '範例 {"key": 1} 與 {unknown}')

    assert _issues(db) == []


def test_character_missing_type_is_warn(db):
    cid = add_character(db)
    other = add_character(db, "別人")
    add_context(db, other, "relationship", "只有別人有")  # 別角色有的 type 仍算已知
    add_prompt(db, "summary", "<relationship></relationship>")

    assert _levels(db) == []
    assert _levels(db, character_id=cid) == [("WARN", "summary")]


def test_only_inactive_context_counts_as_missing(db):
    cid = add_character(db)
    add_context(db, cid, "relationship", "停用中", active=False)
    add_context(db, add_character(db, "別人"), "relationship", "REL")
    add_prompt(db, "summary", "<relationship></relationship>")

    assert _levels(db, character_id=cid) == [("WARN", "summary")]


def test_unused_type_is_info(db):
    add_context(db, add_character(db), "other", "沒人用")
    add_prompt(db, "summary", "<log_content></log_content>")

    [(level, prompt, message)] = _issues(db)
    assert (level, prompt) == ("INFO", None)
    assert "other" in message


def test_slot_nested_in_structure_tag_is_error(db):
    add_prompt(db, "recap", "<故事段落>\n<log_content>\n</log_content>\n</故事段落>")

    [(level, prompt, message)] = _issues(db)
    assert (level, prompt) == ("ERROR", "recap")
    assert "<log_content> 包在 <故事段落> 裡面" in message


def test_slot_nested_in_slot_is_error(db):
    add_context(db, add_character(db), "relationship", "REL")
    add_prompt(db, "summary", "<relationship><log_content></log_content></relationship>")

    [(level, _, message)] = [i for i in _issues(db) if i[0] == "ERROR"]
    assert "<log_content> 包在 <relationship> 裡面" in message


def test_context_slot_nested_in_structure_tag_is_error(db):
    add_context(db, add_character(db), "relationship", "REL")
    add_prompt(db, "summary", "<甲>\n<relationship>\n</relationship>\n</甲>")

    errors = [m for lv, _, m in _issues(db) if lv == "ERROR"]
    assert len(errors) == 1 and "<relationship> 包在 <甲> 裡面" in errors[0]


def test_slot_split_across_system_and_prompt_is_error(db):
    # 引擎 system / prompt 各自填：開在 system、閉在 prompt 兩邊都填不到
    add_prompt(db, "summary", "# system instruction\n<log_content>\n# prompt\n</log_content>")

    [(level, _, message)] = _issues(db)  # 兩段訊息相同,只報一次
    assert level == "ERROR"
    assert "不成對" in message


@pytest.mark.parametrize(
    "text",
    [
        "</log_content>\n<log_content>",  # 數量對得上,但閉在開之前
        "<甲></log_content></甲>\n<log_content>",  # 閉標籤藏在結構標籤裡
    ],
    ids=["close-before-open", "close-hidden-in-structure"],
)
def test_counts_match_but_engine_cannot_pair_is_error(db, text):
    add_prompt(db, "summary", text)

    assert _levels(db) == [("ERROR", "summary")]


def test_slot_name_mentioned_inside_structure_tag_is_fine(db):
    # 引擎把 <格式>…</格式> 整段跳過,裡面提到 <log_content> 只是內文
    add_prompt(db, "recap", "<格式>把 <log_content> 摘要</格式>\n<log_content></log_content>")

    assert _issues(db) == []


def test_slot_name_only_mentioned_inside_structure_tag_is_fine(db):
    # 只在結構標籤內文提到、外面沒有真的填空標籤:是內文,不是壞掉的填空標籤
    add_prompt(db, "recap", "<格式>把 <log_content> 摘要成條列</格式>")

    assert _issues(db) == []


def test_slot_nested_deep_is_error(db):
    add_prompt(db, "recap", "<甲>\n<乙>\n<log_content></log_content>\n</乙>\n</甲>")

    [(level, _, message)] = _issues(db)
    assert level == "ERROR" and "<log_content> 包在 <甲> 裡面" in message


def test_structure_tag_mentioned_in_system_does_not_affect_prompt(db):
    add_prompt(
        db,
        "recap",
        "# system instruction\n請依照 <參考範例> 的格式輸出\n# prompt\n"
        "<log_content></log_content>\n<參考範例>\n範例\n</參考範例>",
    )

    assert _issues(db) == []


def test_same_issue_in_both_sections_reported_once(db):
    add_prompt(db, "summary", "# system instruction\n{log_content}\n# prompt\n{log_content}")

    assert _levels(db) == [("WARN", "summary")]


def test_chinese_structure_tags_are_ignored(db):
    add_prompt(db, "recap", "<格式>\n- 內容\n</格式><參考範例>")

    assert _issues(db) == []


def test_only_latest_version_is_checked(db):
    add_prompt(db, "summary", "<relationshp></relationshp>")  # v1 有錯
    add_prompt(db, "summary", "<log_content></log_content>")  # v2 修好

    assert _issues(db) == []


def test_names_limits_scope_and_reports_missing_prompt(db):
    add_prompt(db, "summary", "<log_content></log_content>")
    add_prompt(db, "recap", "<relationshp></relationshp>")  # 範圍外，不報

    assert _levels(db, names=("summary", "timeline")) == [("ERROR", "timeline")]
