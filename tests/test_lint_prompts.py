"""lint_prompts 細部案例：來源是 DB 裡各支 prompt 的最新版。"""
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

    assert [(lv, m) for lv, _, m in _issues(db) if lv == "ERROR"] == [
        ("ERROR", "<log_content> 包在 <relationship> 裡面,引擎不會填(填空標籤要放在其他標籤外)")
    ]


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
