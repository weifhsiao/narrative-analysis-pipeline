import argparse
from evals.prompt_evals import length_check
from util.crud.prompt import get_prompt_execution_by_id
from util.db_util import SessionLocal, engine

engine.echo = False
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execution-id", type=int, required=True, help="Prompt execution ID"
    )
    parser.add_argument(
        "--limit", type=int, default=700, help="Length limit for the recap text"
    )
    args = parser.parse_args()

    prompt_exec_id = args.execution_id
    length_limit = args.limit

    with SessionLocal() as db:
        prompt_execution = get_prompt_execution_by_id(db, prompt_exec_id)

        if prompt_execution is None:
            raise Exception("prompt_execution is None.")
        elif prompt_execution.result_code != "SUCCESS":
            raise Exception(f"result_code is [{prompt_execution.result_code}]")
        elif not prompt_execution.result_content:  # None,"",0,[]都會抓
            raise Exception(f"prompt_execution length <= 0")

        result_text = prompt_execution.result_content

    is_pass, length = length_check(result_text, length_limit)
    print(
        f"execution_id=[{prompt_exec_id}] | length_check: {length} chars (limit={length_limit}) → {'PASS' if is_pass else 'FAIL'}"
    )
