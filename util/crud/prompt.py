from sqlalchemy import select
from sqlalchemy.orm import Session
from util.models import PromptExecution, PromptTemplate
from datetime import datetime


# create_prompt_execution
def create_prompt_execution(
    db: Session,
    run_id: int,
    prompt_id: int,
    parent_exec_id: int | None = None,
) -> PromptExecution:
    prompt_execution = PromptExecution(run_id=run_id, prompt_id=prompt_id)

    if parent_exec_id is not None:
        prompt_execution.parent_exec_id = parent_exec_id

    db.add(prompt_execution)
    db.flush()
    db.refresh(prompt_execution)

    return prompt_execution


def insert_prompt_executions(db: Session, list: list[PromptExecution]):
    db.add_all(list)
    db.flush()
    return len(list)


# update_prompt_execution
def update_prompt_execution(
    db: Session,
    prompt_exec_id: int,
    result_code: str,
    result_content: str,
) -> PromptExecution | None:

    prompt_execution = db.execute(
        select(PromptExecution).where(PromptExecution.prompt_exec_id == prompt_exec_id)
    ).scalar_one_or_none()

    if prompt_execution is None:
        return

    prompt_execution.result_code = result_code
    prompt_execution.result_content = result_content
    prompt_execution.end_time = datetime.now()

    db.flush()
    db.refresh(prompt_execution)

    return prompt_execution


# get_prompt_executions_by_run
def get_prompt_executions_by_run(db: Session, run_id: int) -> list[PromptExecution]:
    stmt = select(PromptExecution).where(PromptExecution.run_id == run_id)

    return db.execute(stmt).scalars().all()


def get_prompt_execution_by_id(
    db: Session, prompt_exec_id: int
) -> PromptExecution | None:
    stmt = select(PromptExecution).where(
        PromptExecution.prompt_exec_id == prompt_exec_id
    )
    return db.execute(stmt).scalar_one_or_none()


# get_all_prompt_template
def get_all_prompt_template(db: Session) -> list[PromptTemplate]:
    stmt = select(PromptTemplate)
    return db.execute(stmt).scalars().all()


def get_prompt_template_by_id(db: Session, prompt_id: int) -> PromptTemplate | None:
    stmt = select(PromptTemplate).where(PromptTemplate.prompt_id == prompt_id)
    return db.execute(stmt).scalar_one_or_none()


# create_prompt_template
def create_prompt_template(
    db: Session, prompt_template: PromptTemplate
) -> PromptTemplate:
    db.add(prompt_template)
    db.flush()
    db.refresh(prompt_template)

    return prompt_template


# update_prompt
def update_prompt(
    db: Session,
    prompt_id: int,
    prompt_name: str | None = None,
    system_instruction: str | None = None,
    prompt: str | None = None,
) -> PromptTemplate | None:
    prompt_template = db.execute(
        select(PromptTemplate).where(PromptTemplate.prompt_id == prompt_id)
    ).scalar_one_or_none()

    if prompt_template is None:
        return None

    if prompt_name is not None:
        prompt_template.prompt_name = prompt_name

    if system_instruction is not None:
        prompt_template.system_instruction = system_instruction

    if prompt is not None:
        prompt_template.prompt = prompt

    db.flush()
    db.refresh(prompt_template)

    return prompt_template
