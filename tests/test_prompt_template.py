"""prompt 模板入庫：append-only 版本、存 prompt（save_prompt）、.txt 解析、從 DB 載入與快照。"""
import pytest

from service.prompt_service import (
    PromptLintError,
    PromptNotFoundError,
    load_prompt,
    parse_prompt_file,
    save_prompt,
)
from util.crud.prompt import (
    create_prompt_version,
    get_latest_prompt_template,
    get_latest_prompt_templates,
)
from tests.helpers import add_character, add_context

# ---- 版本 ----


def test_first_version_is_its_own_root(db):
    v1 = create_prompt_version(db, "summary", "sys", "p")

    assert v1.version == 1
    assert v1.root_prompt_id == v1.prompt_id


def test_new_version_appends_under_same_root_and_keeps_old(db):
    v1 = create_prompt_version(db, "summary", "sys", "p1")
    v2 = create_prompt_version(db, "summary", "sys", "p2")

    assert (v2.version, v2.root_prompt_id) == (2, v1.prompt_id)
    assert v2.prompt_id != v1.prompt_id
    assert v1.prompt == "p1"  # 舊版不動
    assert get_latest_prompt_template(db, "summary").prompt_id == v2.prompt_id


def test_latest_templates_one_per_prompt(db):
    create_prompt_version(db, "summary", "", "s1")
    create_prompt_version(db, "timeline", "", "t1")
    create_prompt_version(db, "summary", "", "s2")

    latest = get_latest_prompt_templates(db)

    assert [(t.prompt_name, t.prompt) for t in latest] == [("summary", "s2"), ("timeline", "t1")]


def test_latest_of_unknown_name_is_none(db):
    assert get_latest_prompt_template(db, "nope") is None


# ---- save_prompt ----


def test_save_skips_when_same_as_latest(db):
    first, _ = save_prompt(db, "summary", "sys", "p")
    again, _ = save_prompt(db, "summary", "sys", "p")

    assert first.version == 1
    assert again is None
    assert len(get_latest_prompt_templates(db)) == 1


@pytest.mark.parametrize(
    "change", [{"system": "sys2"}, {"prompt": "p2"}, {"max_length": 500}]
)
def test_save_creates_new_version_when_anything_changes(db, change):
    save_prompt(db, "summary", "sys", "p")
    args = {"system": "sys", "prompt": "p", "max_length": None} | change

    template, _ = save_prompt(db, "summary", **args)

    assert template.version == 2


def test_save_blocks_on_lint_error_and_stores_nothing(db):
    with pytest.raises(PromptLintError) as exc:
        save_prompt(db, "summary", "", "<relationshp></relationshp>")

    assert exc.value.issues[0].prompt == "summary"
    assert get_latest_prompt_template(db, "summary") is None


def test_save_force_stores_despite_lint_error(db):
    template, issues = save_prompt(db, "summary", "", "<relationship></relationship>", force=True)

    assert template.version == 1
    assert [i.level for i in issues] == ["ERROR"]  # fresh DB 沒有 context,type 對不上


def test_save_lints_system_and_prompt_separately(db):
    # 接起來掃的話 <log_content> 會被誤判成包在 <參考範例> 裡而擋下
    template, issues = save_prompt(
        db, "recap", "請依照 <參考範例> 的格式", "<log_content></log_content>\n<參考範例>x</參考範例>"
    )

    assert template is not None
    assert issues == []


def test_save_returns_warnings_without_blocking(db):
    template, issues = save_prompt(db, "summary", "", "{log_content}")

    assert template is not None
    assert [i.level for i in issues] == ["WARN"]


# ---- parse_prompt_file ----


def test_parse_splits_sections():
    text = "# system instruction\n系統\n\n# prompt\n內容\n"

    assert parse_prompt_file(text) == ("系統", "內容")


def test_parse_without_headers_is_all_prompt():
    assert parse_prompt_file("\n只有內容\n") == ("", "只有內容")


def test_parse_headers_must_be_whole_lines():
    text = "# system instruction\n請用 # prompts 格式\n# prompt\n內容 # prompt 也照留"

    assert parse_prompt_file(text) == ("請用 # prompts 格式", "內容 # prompt 也照留")


def test_parse_line_starting_with_prompts_is_not_a_header():
    text = "# system instruction\nS\n# prompts 說明\n# prompt\nP"

    assert parse_prompt_file(text) == ("S\n# prompts 說明", "P")


def test_parse_system_header_text_in_body_is_kept():
    text = "說明 # system instruction 字樣\n# prompt\nP"

    assert parse_prompt_file(text) == ("說明 # system instruction 字樣", "P")


def test_parse_system_header_alone_is_not_sent():
    assert parse_prompt_file("# system instruction\n內容") == ("", "內容")


def test_parse_strips_bom():
    assert parse_prompt_file("\ufeff# system instruction\nS\n# prompt\nP") == ("S", "P")


def test_parse_prompt_header_alone_is_not_sent():
    assert parse_prompt_file("# prompt\n內容") == ("", "內容")


# ---- load_prompt ----


def test_load_uses_latest_version(db):
    create_prompt_version(db, "summary", "", "v1")
    v2 = create_prompt_version(db, "summary", "", "v2")

    rendered = load_prompt("summary", db, 1, {})

    assert rendered.prompt_id == v2.prompt_id
    assert rendered.prompt == "v2"


def test_load_missing_prompt_raises(db):
    with pytest.raises(PromptNotFoundError):
        load_prompt("summary", db, 1, {})


def test_load_snapshot_fills_context_but_keeps_run_param_tag(db):
    cid = add_character(db)
    add_context(db, cid, "relationship", "REL")
    create_prompt_version(
        db, "summary", "<relationship></relationship>", "<log_content></log_content>"
    )

    r = load_prompt("summary", db, cid, {"log_content": "LOG"})

    assert r.system == r.system_snapshot == "<relationship>\nREL\n</relationship>"
    assert r.prompt == "<log_content>\nLOG\n</log_content>"
    assert r.prompt_snapshot == "<log_content></log_content>"
    assert r.used_run_params == {"log_content"}


def test_load_run_params_counted_per_section(db):
    # system 提到 <參考範例> 不影響 prompt 裡的 <log_content>(接起來掃會被誤當成包在裡面)
    create_prompt_version(
        db, "recap", "請依照 <參考範例> 的格式", "<log_content></log_content>\n<參考範例>x</參考範例>"
    )

    r = load_prompt("recap", db, 1, {"log_content": "LOG"})

    assert r.used_run_params == {"log_content"}
    assert "<log_content>\nLOG\n</log_content>" in r.prompt


def test_load_without_log_tag_reports_no_run_params(db):
    create_prompt_version(db, "summary", "", "沒有 log 標籤")

    assert load_prompt("summary", db, 1, {"log_content": "LOG"}).used_run_params == set()
