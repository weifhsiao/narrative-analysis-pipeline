"""run_pipeline 與 /runs router：preflight lint、preview、正式執行（快照/用量）、AI 失敗的記錄方式。"""

import pytest
from sqlalchemy import select

from service.pipeline_service import PIPELINE_PROMPTS, run_pipeline
from service.prompt_service import PromptLintError, lint_prompts
from util.ai_client import AIBlockedError
from util.models import CharacterContext, PromptExecution
from tests.conftest import FAKE_USAGE
from tests.helpers import add_character, add_context, add_log, add_prompt, add_run

START, END = "2026-01-01 00:00:00", "2026-01-31 23:59:59"

# 範圍內的 log 依時間 join 後應得的內容（含剛好落在 END 的那筆）
IN_RANGE_LOG = "第一句劇情\n\n月底最後一秒"


def good_prompt(name: str) -> str:
    """各支 system 不同，才驗得到「每支 prompt 載入的是自己」。"""
    return f"""# system instruction
你是 {name} 助手。

# prompt
<relationship>
</relationship>
<log_content>
</log_content>
"""


@pytest.fixture
def setup(db):
    """一個有 log、有 relationship、三支 pipeline prompt 都乾淨的角色。"""
    cid = add_character(db)
    add_context(db, cid, "relationship", "REL_CONTENT")
    add_log(db, cid, "範圍前的劇情", "2025-12-31 23:59:59")
    add_log(db, cid, "第一句劇情", "2026-01-02 10:00:00")
    add_log(db, cid, "月底最後一秒", END)  # 邊界：字串邊界直接比會漏掉，要靠 _coerce_dt
    add_log(db, cid, "範圍後的劇情", "2026-02-01 00:00:00")
    for name in PIPELINE_PROMPTS:
        add_prompt(db, name, good_prompt(name))
    return cid


def _executions(db):
    return db.execute(select(PromptExecution)).scalars().all()


# ---- preflight lint ----


def test_lint_error_aborts_before_ai_and_files(db, setup, fake_ai, tmp_path):
    add_prompt(db, "timeline", "<relationshp></relationshp>")  # 新一版打錯字

    with pytest.raises(PromptLintError) as exc:
        run_pipeline(db, 1, setup, START, END)

    assert [i.prompt for i in exc.value.issues] == ["timeline"]
    assert fake_ai.calls != []
    assert not (tmp_path / "data").exists()
    assert _executions(db) == []


def test_missing_pipeline_prompt_aborts(db, fake_ai):
    cid = add_character(db)
    add_context(db, cid, "relationship", "REL")
    add_prompt(
        db, "summary", good_prompt("summary")
    )  # timeline / relationship 沒 import

    with pytest.raises(PromptLintError) as exc:
        run_pipeline(db, 1, cid, START, END)

    assert sorted(i.prompt for i in exc.value.issues) == ["relationship", "timeline"]
    assert fake_ai.calls == []


def test_lint_error_in_non_pipeline_prompt_does_not_abort(db, setup, fake_ai):
    add_prompt(db, "recap", "<relationshp></relationshp>")

    run_pipeline(db, 1, setup, START, END)

    assert len(fake_ai.calls) == len(PIPELINE_PROMPTS)


def test_lint_warn_does_not_abort(db, fake_ai):
    cid = add_character(db)
    other = add_character(db, "別人")
    add_context(
        db, other, "relationship", "只有別人有"
    )  # type 存在，但 cid 沒有 → WARN
    for name in PIPELINE_PROMPTS:
        add_prompt(db, name, good_prompt(name))
    assert any(i.level == "WARN" for i in lint_prompts(db, cid))  # 前提：真的有 WARN

    run_pipeline(db, 1, cid, START, END)

    assert len(fake_ai.calls) == len(PIPELINE_PROMPTS)


# ---- preview ----


def test_preview_returns_sent_content_without_ai_files_or_db(
    db, setup, fake_ai, tmp_path
):
    result = run_pipeline(db, 1, setup, START, END, preview=True)

    prompts = result["prompts"]
    assert [p["prompt_name"] for p in prompts] == list(PIPELINE_PROMPTS)
    for p in prompts:
        assert p["system"] == f"你是 {p['prompt_name']} 助手。"
        assert "<relationship>\nREL_CONTENT\n</relationship>" in p["prompt"]
        assert f"<log_content>\n{IN_RANGE_LOG}\n</log_content>" in p["prompt"]
        assert p["prompt_id"] is not None
        assert p["error"] is None
    assert fake_ai.calls == []
    assert _executions(db) == []
    assert not (tmp_path / "data").exists()


# ---- 正式執行 ----


def test_execute_sends_filled_prompt_and_records_success(db, setup, fake_ai):
    insert_cnt = run_pipeline(db, 7, setup, START, END)

    assert insert_cnt == len(PIPELINE_PROMPTS)
    assert [c["system"] for c in fake_ai.calls] == [
        f"你是 {n} 助手。" for n in PIPELINE_PROMPTS
    ]
    call = fake_ai.calls[0]
    assert "<relationship>\nREL_CONTENT\n</relationship>" in call["prompt"]
    assert f"<log_content>\n{IN_RANGE_LOG}\n</log_content>" in call["prompt"]
    assert call["attachments"] is None
    rows = _executions(db)
    assert {r.run_id for r in rows} == {7}
    assert {r.result_code for r in rows} == {"SUCCESS"}
    assert {r.result_content for r in rows} == {"fake response"}


def test_execute_records_prompt_version(db, setup):
    v2 = add_prompt(db, "summary", good_prompt("summary") + "改過的第二版")

    run_pipeline(db, 1, setup, START, END)

    summary = next(r for r in _executions(db) if r.prompt_id == v2.prompt_id)
    assert v2.version == 2
    assert "改過的第二版" in summary.prompt_snapshot


def test_execute_snapshot_has_context_but_not_log(db, setup):
    run_pipeline(db, 1, setup, START, END)

    for r in _executions(db):
        assert "<relationship>\nREL_CONTENT\n</relationship>" in r.prompt_snapshot
        assert (
            "<log_content>\n</log_content>" in r.prompt_snapshot
        )  # 模板原樣，log 由 run range 重建
        assert "第一句劇情" not in r.prompt_snapshot
        assert r.system_snapshot.startswith("你是 ")


def test_snapshot_keeps_context_as_of_run(db, setup):
    run_pipeline(db, 1, setup, START, END)
    ctx = db.execute(select(CharacterContext)).scalar_one()
    ctx.context_content = "事後改過"
    db.flush()

    assert all("REL_CONTENT" in r.prompt_snapshot for r in _executions(db))


def test_execute_records_usage(db, setup):
    run_pipeline(db, 1, setup, START, END)

    for r in _executions(db):
        assert (r.model, r.input_tokens, r.output_tokens, r.thinking_tokens) == (
            FAKE_USAGE.model,
            FAKE_USAGE.input_tokens,
            FAKE_USAGE.output_tokens,
            FAKE_USAGE.thinking_tokens,
        )


def test_execute_does_not_write_debug_log(db, setup, tmp_path):
    run_pipeline(db, 1, setup, START, END)

    assert not (tmp_path / "data" / "debug_log").exists()


def test_attachment_mode_sends_log_as_file(db, setup, fake_ai, monkeypatch):
    monkeypatch.setenv("LOG_INPUT_MODE", "attachment")

    run_pipeline(db, 1, setup, START, END)

    call = fake_ai.calls[0]
    assert "第一句劇情" not in call["prompt"]
    assert "story_log.txt" in call["prompt"]
    [attachment] = call["attachments"]
    assert attachment.data.decode("utf-8") == IN_RANGE_LOG


def test_attachment_only_for_prompts_with_log_tag(db, setup, fake_ai, monkeypatch):
    monkeypatch.setenv("LOG_INPUT_MODE", "attachment")
    add_prompt(
        db,
        "timeline",
        "# system instruction\nsys\n\n# prompt\n<relationship>\n</relationship>",
    )

    run_pipeline(db, 1, setup, START, END)

    by_system = {c["system"]: c["attachments"] for c in fake_ai.calls}
    assert by_system["sys"] is None
    assert len(by_system["你是 summary 助手。"]) == 1


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
    assert all(r.prompt_snapshot for r in rows)  # 已組好才送出，失敗也留快照


def test_blocked_records_usage_when_provider_reports_it(db, setup, fake_ai):
    fake_ai.response = AIBlockedError("SAFETY", FAKE_USAGE)

    run_pipeline(db, 1, setup, START, END)

    assert {r.input_tokens for r in _executions(db)} == {FAKE_USAGE.input_tokens}


# ---- router ----


@pytest.mark.parametrize("action", ["execute", "preview"])
def test_router_returns_422_with_issues_on_lint_error(client, db, setup, action):
    run_id = add_run(db, setup, START, END)
    add_prompt(db, "summary", "<relationship>")

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
    prompts = res.json()["prompts"]
    assert len(prompts) == len(PIPELINE_PROMPTS)
    # range 走 run 表的 String 欄位讀回，邊界那筆仍要撈到
    assert f"<log_content>\n{IN_RANGE_LOG}\n</log_content>" in prompts[0]["prompt"]
    assert fake_ai.calls == []


def test_router_execute_ok(client, db, setup):
    run_id = add_run(db, setup, START, END)

    res = client.post(f"/runs/{run_id}/execute")

    assert res.status_code == 200
    assert res.json() == {"insert_cnt": len(PIPELINE_PROMPTS)}

    [first, *_] = client.get(f"/runs/{run_id}/execution").json()
    assert first["prompt_id"] is not None
    assert first["model"] == FAKE_USAGE.model
    assert "REL_CONTENT" in first["prompt_snapshot"]


@pytest.mark.parametrize("action", ["execute", "preview"])
def test_router_404_when_run_missing(client, action):
    assert client.post(f"/runs/999/{action}").status_code == 404
