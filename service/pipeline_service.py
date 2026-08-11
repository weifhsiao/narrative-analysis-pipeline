import os
import time
from datetime import datetime
from util.file_util import (
    load_character_content,
    load_all_scenarios,
    load_prompt,
    write_debug_file,
    write_response,
)
from util.ai_client import get_client, Attachment, AIBlockedError
from util.models import PromptExecution
from util.crud.prompt import insert_prompt_executions
from sqlalchemy.orm import Session
from service.novel_log_service import assemble_dialogue


def _run_prompt(
    prompt_name: str,
    timestamp: str,
    preview: bool = False,
    attachments: list[Attachment] | None = None,
    **kwargs,
) -> dict:
    ai_model = os.getenv("GEMINI_MODEL", "UNKNOWN")
    start_time = datetime.now()
    print(f"prompt=[{prompt_name}]  | model=[{ai_model}] | preview=[{preview}] | start.")
    debug_path = None
    try:
        system, prompt = load_prompt(f"{prompt_name}", **kwargs)
        attachment_info = "".join(
            f"\n[attachment] {a.filename or '(unnamed)'} | {a.mime_type} | {len(a.data)} bytes"
            for a in (attachments or [])
        )
        debug_path = write_debug_file(
            f"{'='*10}{prompt_name} ai_model:[{ai_model}]{'='*10}\n\n system_instruction:[{system}]\n\n{prompt}{attachment_info}\n\n{'='*10}{prompt_name} end{'='*10}\n\n",
            timestamp,
            f"{prompt_name}",
        )
        if preview:
            code, content = "PREVIEW", None
        else:
            response = get_client().generate(prompt, system, attachments=attachments)
            write_response(response, timestamp, f"{prompt_name}")
            code, content = "SUCCESS", response
    except AIBlockedError as e:
        # 200 but no usable text (content/safety block). Store the real reason,
        # not a downstream error. generate() raises before write_response, so no
        # empty response file is written.
        code, content = "BLOCKED", str(e)
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
        "debug_path": debug_path,
    }


def _to_prompt_execution(result: dict, run_id: int) -> PromptExecution:
    return PromptExecution(
        run_id=run_id,
        prompt_id=None,  # prompt_template啟用後加入
        start_time=result["start_time"],
        end_time=result["end_time"],
        result_code=result["result_code"],
        result_content=result["result_content"],
    )


def run_pipeline(
    db: Session,
    run_id: int,
    character_id: str,
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

    # load parameter file
    log_content, final_page = assemble_dialogue(
        character_id, db, range_start, range_end
    )
    current_relationship_status = load_character_content(character_id, "relationship")
    scenarios = load_all_scenarios(character_id)
    existing_timeline = load_character_content(character_id, "timeline")

    # log 輸入模式:inline(純文字內嵌,預設) / attachment(夾檔)
    log_input_mode = os.getenv("LOG_INPUT_MODE", "inline")
    if log_input_mode == "attachment":
        # placeholder 換成指向附件的提示,真正 log 走附件;4 個 prompt 共用同一個 Attachment
        log_kwarg = "（完整劇情內容請見附件檔案 story_log.txt）"
        log_attachments = [
            Attachment(
                data=log_content.encode("utf-8"),
                mime_type="text/plain",
                filename="story_log.txt",
            )
        ]
    else:
        log_kwarg = log_content
        log_attachments = None

    # short_summary
    results.append(
        _run_prompt(
            "recap",
            timestamp,
            preview=preview,
            attachments=log_attachments,
            page_num=final_page,
            log_content=log_kwarg,
        )
    )

    # summary
    background_content = f"{current_relationship_status}\n\n{scenarios}\n\n"
    results.append(
        _run_prompt(
            "summary",
            timestamp,
            preview=preview,
            attachments=log_attachments,
            log_content=log_kwarg,
            background_context=background_content,
        )
    )

    # timeline
    results.append(
        _run_prompt(
            "timeline",
            timestamp,
            preview=preview,
            attachments=log_attachments,
            existing_timeline=existing_timeline,
            background_context=current_relationship_status,
            log_content=log_kwarg,
        )
    )

    # relationship
    results.append(
        _run_prompt(
            "relationship",
            timestamp,
            preview=preview,
            attachments=log_attachments,
            log_content=log_kwarg,
            current_relationship_status=current_relationship_status,
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
        # 只組 prompt + 寫 debug 檔，不打 AI、不入庫
        return {
            "timestamp": timestamp,
            "files": [str(r["debug_path"]) for r in results if r["debug_path"]],
        }

    executions = [_to_prompt_execution(r, run_id) for r in results]
    return insert_prompt_executions(db, executions)
