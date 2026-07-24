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
from util.ai_client import get_client
from util.models import PromptExecution
from util.crud.prompt import insert_prompt_executions
from sqlalchemy.orm import Session
from service.novel_log_service import assemble_dialogue


def _run_prompt(prompt_name: str, timestamp: str, **kwargs) -> dict:
    ai_model = os.getenv("GEMINI_MODEL", "UNKNOWN")
    start_time = datetime.now()
    print(f"prompt=[{prompt_name}]  | model=[{ai_model}] | start.")
    try:
        system, prompt = load_prompt(f"{prompt_name}", **kwargs)
        response = get_client().generate(prompt, system)
        write_response(response, timestamp, f"{prompt_name}")
        write_debug_file(
            f"{'='*10}{prompt_name} ai_model:[{ai_model}]{'='*10}\n\n system_instruction:[{system}]\n\n{prompt}\n\n{'='*10}{prompt_name} end{'='*10}\n\n",
            timestamp,
            f"{prompt_name}",
        )
        code, content = "SUCCESS", response
    except Exception as e:
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


def run_pipeline(db: Session, run_id: int, character_id: str) -> int:
    print(f"[run_pipeline] start | run_id:[{run_id}] character_id:[{character_id}]")
    start_time = datetime.now()
    timestamp = str(int(time.time()))
    results = []

    # load parameter file
    log_content, final_page = assemble_dialogue(character_id, db)
    current_relationship_status = load_character_content(character_id, "relationship")
    scenarios = load_all_scenarios(character_id)
    existing_timeline = load_character_content(character_id, "timeline")

    # short_summary
    results.append(
        _run_prompt(
            "recap",
            timestamp,
            page_num=final_page,
            log_content=log_content,
        )
    )

    # summary
    background_content = f"{current_relationship_status}\n\n{scenarios}\n\n"
    results.append(
        _run_prompt(
            "summary",
            timestamp,
            log_content=log_content,
            background_context=background_content,
        )
    )

    # timeline
    results.append(
        _run_prompt(
            "timeline",
            timestamp,
            existing_timeline=existing_timeline,
            background_context=current_relationship_status,
            log_content=log_content,
        )
    )

    # relationship
    results.append(
        _run_prompt(
            "relationship",
            timestamp,
            log_content=log_content,
            current_relationship_status=current_relationship_status,
        )
    )

    executions = [_to_prompt_execution(r, run_id) for r in results]
    end_time = datetime.now()
    ok_count = sum(1 for r in results if r["result_code"] == "SUCCESS")
    error_count = sum(1 for r in results if r["result_code"] == "ERROR")

    print(
        f"[run_pipeline] end | total=[{(end_time - start_time).total_seconds()}]s | ok=[{ok_count}] | error=[{error_count}]"
    )

    return insert_prompt_executions(db, executions)
