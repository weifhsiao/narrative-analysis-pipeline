"""run_pipeline 與 /runs router：preflight lint、preview、正式執行、AI 失敗的記錄方式。"""
import pytest
from sqlalchemy import select

from service.pipeline_service import PIPELINE_PROMPTS, run_pipeline
from service.prompt_service import PromptLintError
from util.ai_client import AIBlockedError
from util.models import PromptExecution
from tests.helpers import add_character, add_context, add_log, add_run, write_prompt

START, END = "2026-01-01 00:00:00", "2026-01-31 23:59:59"

GOOD_PROMPT = """# system instruction
你是整理助手。

# prompt
<relationship>
</relationship>
<log_content>
</log_content>
"""


@pytest.fixture
def setup(db, prompts_dir):
    """一個有 log、有 relationship、三支 pipeline prompt 都乾淨的角色。"""
    cid = add_character(db)
    add_context(db, cid, "relationship", "REL_CONTENT")
    add_log(db, cid, "第一句劇情", "2026-01-02 10:00:00")
    add_log(db, cid, "範圍外的劇情", "2026-02-02 10:00:00")
    for name in PIPELINE_PROMPTS:
        write_prompt(prompts_dir, name, GOOD_PROMPT)
    return cid


def _executions(db):
    return db.execute(select(PromptExecution)).scalars().all()


# ---- preflight lint ----


def test_lint_error_aborts_before_ai_and_debug_files(db, setup, prompts_dir, fake_ai, tmp_path):
    write_prompt(prompts_dir, "timeline", "<relationshp></relationshp>")

    with pytest.raises(PromptLintError) as exc:
        run_pipeline(db, 1, setup, START, END)

    assert [i.prompt for i in exc.value.issues] == ["timeline"]
    assert fake_ai.calls == []
    assert not (tmp_path / "data").exists()
    assert _executions(db) == []


def test_lint_error_in_non_pipeline_prompt_does_not_abort(db, setup, prompts_dir, fake_ai):
    write_prompt(prompts_dir, "recap", "<relationshp></relationshp>")

    run_pipeline(db, 1, setup, START, END)

    assert len(fake_ai.calls) == len(PIPELINE_PROMPTS)


def test_lint_warn_does_not_abort(db, prompts_dir, fake_ai):
    cid = add_character(db)
    other = add_character(db, "別人")
    add_context(db, other, "relationship", "只有別人有")  # type 存在，但 cid 沒有 → WARN
    for name in PIPELINE_PROMPTS:
        write_prompt(prompts_dir, name, GOOD_PROMPT)

    run_pipeline(db, 1, cid, START, END)

    assert len(fake_ai.calls) == len(PIPELINE_PROMPTS)


# ---- preview ----


def test_preview_writes_rendered_prompts_without_calling_ai(db, setup, fake_ai):
    result = run_pipeline(db, 1, setup, START, END, preview=True)

    assert len(result["files"]) == len(PIPELINE_PROMPTS)
    for path in result["files"]:
        text = open(path, encoding="utf-8").read()
        assert "REL_CONTENT" in text
        assert "第一句劇情" in text
        assert "範圍外的劇情" not in text
    assert fake_ai.calls == []
    assert _executions(db) == []


# ---- 正式執行 ----


def test_execute_sends_filled_prompt_and_records_success(db, setup, fake_ai):
    insert_cnt = run_pipeline(db, 7, setup, START, END)

    assert insert_cnt == len(PIPELINE_PROMPTS)
    call = fake_ai.calls[0]
    assert call["system"] == "你是整理助手。"
    assert "<relationship>\nREL_CONTENT\n</relationship>" in call["prompt"]
    assert "<log_content>\n第一句劇情\n</log_content>" in call["prompt"]
    assert call["attachments"] is None
    rows = _executions(db)
    assert {r.run_id for r in rows} == {7}
    assert {r.result_code for r in rows} == {"SUCCESS"}
    assert {r.result_content for r in rows} == {"fake response"}


def test_attachment_mode_sends_log_as_file(db, setup, fake_ai, monkeypatch):
    monkeypatch.setenv("LOG_INPUT_MODE", "attachment")

    run_pipeline(db, 1, setup, START, END)

    call = fake_ai.calls[0]
    assert "第一句劇情" not in call["prompt"]
    assert "story_log.txt" in call["prompt"]
    [attachment] = call["attachments"]
    assert attachment.data.decode("utf-8") == "第一句劇情"


@pytest.mark.parametrize(
    "error, code",
    [(AIBlockedError("SAFETY"), "BLOCKED"), (RuntimeError("500 boom"), "ERROR")],
)
def test_ai_failure_recorded_per_prompt(db, setup, fake_ai, error, code):
    fake_ai.response = error

    run_pipeline(db, 1, setup, START, END)

    rows = _executions(db)
    assert len(rows) == len(PIPELINE_PROMPTS)
    assert {r.result_code for r in rows} == {code}
    assert all(str(error) in r.result_content for r in rows)


# ---- router ----


@pytest.mark.parametrize("action", ["execute", "preview"])
def test_router_returns_422_with_issues_on_lint_error(client, db, setup, prompts_dir, action):
    run_id = add_run(db, setup, START, END)
    write_prompt(prompts_dir, "summary", "<relationship>")

    res = client.post(f"/runs/{run_id}/{action}")

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "prompt lint failed"
    assert detail["issues"][0]["prompt"] == "summary"
    assert "relationship" in detail["issues"][0]["message"]


def test_router_preview_ok(client, db, setup, fake_ai):
    run_id = add_run(db, setup, START, END)

    res = client.post(f"/runs/{run_id}/preview")

    assert res.status_code == 200
    assert len(res.json()["files"]) == len(PIPELINE_PROMPTS)
    assert fake_ai.calls == []


def test_router_execute_ok(client, db, setup):
    run_id = add_run(db, setup, START, END)

    res = client.post(f"/runs/{run_id}/execute")

    assert res.status_code == 200
    assert res.json() == {"insert_cnt": len(PIPELINE_PROMPTS)}


@pytest.mark.parametrize("action", ["execute", "preview"])
def test_router_404_when_run_missing(client, action):
    assert client.post(f"/runs/999/{action}").status_code == 404
