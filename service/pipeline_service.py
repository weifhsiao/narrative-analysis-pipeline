import os
import time
from datetime import datetime
from util.file_util import write_response
from util.ai_client import get_client, configured_model, Attachment, AIBlockedError, TokenUsage
from util.models import PromptExecution
from util.crud.prompt import insert_prompt_executions
from sqlalchemy.orm import Session
from service.novel_log_service import assemble_dialogue
from service.prompt_service import load_prompt, lint_prompts, PromptLintError

# 本 pipeline 會跑的 prompt(recap 停用中)
PIPELINE_PROMPTS = ("summary", "timeline", "relationship")


def _run_prompt(
    prompt_name: str,
    timestamp: str,
    db: Session,
    character_id: int,
    run_params: dict[str, str],
    preview: bool = False,
    attachments: list[Attachment] | None = None,
) -> dict:
    ai_model = configured_model()
    start_time = datetime.now()
    print(
        f"prompt=[{prompt_name}]  | model=[{ai_model}] | preview=[{preview}] | start."
    )
    rendered = None
    usage = None
    try:
        rendered = load_prompt(prompt_name, db, character_id, run_params)
        # log 夾檔只給模板裡有 <log_content> 的 prompt:標籤就是開關,同 context 原則
        if "log_content" not in rendered.used_run_params:
            attachments = None
        if preview:
            code, content = "PREVIEW", None
        else:
            result = get_client().generate(
                rendered.prompt, rendered.system, attachments=attachments
            )
            write_response(result.text, timestamp, f"{prompt_name}")
            code, content, usage = "SUCCESS", result.text, result.usage
    except AIBlockedError as e:
        # 200 but no usable text (content/safety block). Store the real reason,
        # not a downstream error. generate() raises before write_response, so no
        # empty response file is written. Blocked input is usually still billed.
        code, content, usage = "BLOCKED", str(e), e.usage
    except Exception as e:
        # Everything else: API errors (4xx/5xx), network issues, bugs.
        # str(APIError) already includes the HTTP code, e.g. "400 INVALID_ARGUMENT...".
        code, content = "ERROR", str(e)

    end_time = datetime.now()

    print(
        f"prompt=[{prompt_name}]  | end | duration=[{(end_time - start_time).total_seconds()}]s | result_code=[{code}]"
    )

    return {
        "prompt_name": prompt_name,
        "start_time": start_time,
        "end_time": end_time,
        "result_code": code,
        "result_content": content,
        "rendered": rendered,
        "usage": usage,
        "attachments": attachments if rendered else None,
    }


def _to_prompt_execution(result: dict, run_id: int) -> PromptExecution:
    rendered = result["rendered"]
    usage = result["usage"] or TokenUsage()
    return PromptExecution(
        run_id=run_id,
        prompt_id=rendered.prompt_id if rendered else None,
        start_time=result["start_time"],
        end_time=result["end_time"],
        result_code=result["result_code"],
        result_content=result["result_content"],
        system_snapshot=rendered.system_snapshot if rendered else None,
        prompt_snapshot=rendered.prompt_snapshot if rendered else None,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        thinking_tokens=usage.thinking_tokens,
    )


def _to_preview(result: dict) -> dict:
    """preview 回傳實際會送出的內容(含 log),不寫檔、不入庫。"""
    rendered = result["rendered"]
    return {
        "prompt_name": result["prompt_name"],
        "prompt_id": rendered.prompt_id if rendered else None,
        "system": rendered.system if rendered else None,
        "prompt": rendered.prompt if rendered else None,
        "attachments": [
            f"{a.filename or '(unnamed)'} | {a.mime_type} | {len(a.data)} bytes"
            for a in result["attachments"] or []
        ],
        "error": result["result_content"] if result["result_code"] == "ERROR" else None,
    }


def run_pipeline(
    db: Session,
    run_id: int,
    character_id: int,
    range_start: datetime | str | None = None,
    range_end: datetime | str | None = None,
    preview: bool = False,
) -> int | dict:
    print(
        f"[run_pipeline] start | run_id:[{run_id}] character_id:[{character_id}] preview:[{preview}]"
    )
    start_time = datetime.now()
    timestamp = str(int(time.time()))
    results = []

    # preflight lint:只看這次會跑的 prompt(DB 缺也算 ERROR);ERROR 中止(不組 prompt、不打 AI),
    # WARN 印出繼續。存 prompt 時已 lint 過,這裡擋的是 context 端改名/停用 type 造成的對不上。
    issues = [
        i
        for i in lint_prompts(db, character_id, PIPELINE_PROMPTS)
        if i.level != "INFO"
    ]
    for i in issues:
        print(f"[run_pipeline] lint {i.level} | {i.prompt} | {i.message}")
    errors = [i for i in issues if i.level == "ERROR"]
    if errors:
        raise PromptLintError(errors)

    # load parameter file
    log_content = assemble_dialogue(character_id, db, range_start, range_end)

    # log 輸入模式:inline(純文字內嵌,預設) / attachment(夾檔)
    log_input_mode = os.getenv("LOG_INPUT_MODE", "inline")
    if log_input_mode == "attachment":
        # placeholder 換成指向附件的提示,真正 log 走附件;各 prompt 共用同一個 Attachment
        log_text = "（完整劇情內容請見附件檔案 story_log.txt）"
        log_attachments = [
            Attachment(
                data=log_content.encode("utf-8"),
                mime_type="text/plain",
                filename="story_log.txt",
            )
        ]
    else:
        log_text = log_content
        log_attachments = None

    # 背景 context 由各 prompt 的標籤自行宣告,引擎依 character_id 到 DB 撈;
    # 這裡只帶 run 輸入(劇情)。
    run_params = {"log_content": log_text}

    # recap 目前停用(頁碼無關版只吃 log_content,重新啟用時併回下方迴圈)
    # results.append(
    #     _run_prompt(
    #         "recap", timestamp, db, character_id, run_params,
    #         preview=preview, attachments=log_attachments,
    #     )
    # )

    for prompt_name in PIPELINE_PROMPTS:
        results.append(
            _run_prompt(
                prompt_name,
                timestamp,
                db,
                character_id,
                run_params,
                preview=preview,
                attachments=log_attachments,
            )
        )

    end_time = datetime.now()
    ok_count = sum(1 for r in results if r["result_code"] == "SUCCESS")
    blocked_count = sum(1 for r in results if r["result_code"] == "BLOCKED")
    error_count = sum(1 for r in results if r["result_code"] == "ERROR")

    print(
        f"[run_pipeline] end | total=[{(end_time - start_time).total_seconds()}]s | ok=[{ok_count}] | blocked=[{blocked_count}] | error=[{error_count}]"
    )

    if preview:
        # 只組 prompt 回傳內容，不打 AI、不寫檔、不入庫
        return {"prompts": [_to_preview(r) for r in results]}

    executions = [_to_prompt_execution(r, run_id) for r in results]
    return insert_prompt_executions(db, executions)
