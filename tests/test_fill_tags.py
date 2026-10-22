"""_fill_tags：把 prompt 文字裡的填空標籤換成 run 參數或 DB context。

純吃文字、不管 prompt 從哪來，prompt 入庫後仍然有效。
"""
from service.prompt_service import _fill_tags
from tests.helpers import add_character, add_context


def test_run_param_fills_tag(db):
    out = _fill_tags("<log_content></log_content>", db, 1, {"log_content": "LOG"}, set())

    assert out == "<log_content>\nLOG\n</log_content>"


def test_context_type_filled_from_db(db):
    cid = add_character(db)
    add_context(db, cid, "relationship", "REL")

    out = _fill_tags("<relationship></relationship>", db, cid, {}, {"relationship"})

    assert out == "<relationship>\nREL\n</relationship>"


def test_run_param_takes_priority_over_db_type(db):
    cid = add_character(db)
    add_context(db, cid, "log_content", "FROM_DB")

    out = _fill_tags(
        "<log_content></log_content>", db, cid, {"log_content": "FROM_RUN"}, {"log_content"}
    )

    assert "FROM_RUN" in out
    assert "FROM_DB" not in out


def test_existing_tag_content_is_replaced(db):
    out = _fill_tags("<log_content>舊內容</log_content>", db, 1, {"log_content": "新"}, set())

    assert out == "<log_content>\n新\n</log_content>"


def test_unknown_tags_left_untouched(db):
    text = "<格式>\n- 內容\n</格式>\n<foo>bar</foo>"

    assert _fill_tags(text, db, 1, {"log_content": "LOG"}, {"relationship"}) == text


def test_braces_and_backslashes_in_content_preserved(db):
    content = '{"a": 1} {log_content} \\1 \\n \\g<0>'

    out = _fill_tags("<log_content></log_content>", db, 1, {"log_content": content}, set())

    assert out == f"<log_content>\n{content}\n</log_content>"


def test_filled_content_is_not_rescanned(db):
    cid = add_character(db)
    add_context(db, cid, "relationship", "REL")
    injected = "<relationship></relationship>"

    out = _fill_tags(
        "<log_content></log_content>", db, cid, {"log_content": injected}, {"relationship"}
    )

    assert out == f"<log_content>\n{injected}\n</log_content>"


def test_known_type_without_rows_fills_empty(db):
    cid = add_character(db)

    out = _fill_tags("<relationship></relationship>", db, cid, {}, {"relationship"})

    assert out == "<relationship>\n\n</relationship>"


def test_only_active_contexts_joined_in_sort_order(db):
    cid = add_character(db)
    add_context(db, cid, "scenario", "第二段", sort_order=2)
    add_context(db, cid, "scenario", "第一段", sort_order=1)
    add_context(db, cid, "scenario", "停用的", sort_order=0, active=False)

    out = _fill_tags("<scenario></scenario>", db, cid, {}, {"scenario"})

    assert out == "<scenario>\n第一段\n\n第二段\n</scenario>"


def test_other_characters_context_not_used(db):
    me = add_character(db, "我")
    other = add_character(db, "別人")
    add_context(db, other, "relationship", "別人的關係")

    out = _fill_tags("<relationship></relationship>", db, me, {}, {"relationship"})

    assert "別人的關係" not in out


def test_closing_tag_aligned_with_opening_indent(db):
    text = "## 背景\n    <log_content>\n    </log_content>"

    out = _fill_tags(text, db, 1, {"log_content": "第一行\n第二行"}, set())

    assert out == "## 背景\n    <log_content>\n第一行\n第二行\n    </log_content>"


def test_closing_tag_not_indented_when_text_precedes_opening(db):
    out = _fill_tags("說明 <log_content></log_content>", db, 1, {"log_content": "LOG"}, set())

    assert out == "說明 <log_content>\nLOG\n</log_content>"
