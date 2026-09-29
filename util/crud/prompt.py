from sqlalchemy import func, select
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
    stmt = (
        select(PromptExecution)
        .where(PromptExecution.run_id == run_id)
        .order_by(PromptExecution.prompt_exec_id)
    )

    return db.execute(stmt).scalars().all()


def get_prompt_execution_by_id(
    db: Session, prompt_exec_id: int
) -> PromptExecution | None:
    stmt = select(PromptExecution).where(
        PromptExecution.prompt_exec_id == prompt_exec_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_prompt_template_by_id(db: Session, prompt_id: int) -> PromptTemplate | None:
    stmt = select(PromptTemplate).where(PromptTemplate.prompt_id == prompt_id)
    return db.execute(stmt).scalar_one_or_none()


def get_latest_prompt_template(db: Session, prompt_name: str) -> PromptTemplate | None:
    """name 對應那支 prompt 的最新版;同一支各版 name 一致,取 max(version)。"""
    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.prompt_name == prompt_name)
        .order_by(PromptTemplate.version.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_latest_prompt_templates(db: Session) -> list[PromptTemplate]:
    """每支 prompt(root)各取最新版,依 name 排序。"""
    latest = (
        select(
            PromptTemplate.root_prompt_id,
            func.max(PromptTemplate.version).label("version"),
        )
        .group_by(PromptTemplate.root_prompt_id)
        .subquery()
    )
    stmt = (
        select(PromptTemplate)
        .join(
            latest,
            (PromptTemplate.root_prompt_id == latest.c.root_prompt_id)
            & (PromptTemplate.version == latest.c.version),
        )
        .order_by(PromptTemplate.prompt_name)
    )
    return db.execute(stmt).scalars().all()


def create_prompt_version(
    db: Session,
    prompt_name: str,
    system_instruction: str,
    prompt: str,
    max_length: int | None = None,
) -> PromptTemplate:
    """append-only:name 沒有既有版本就建 v1(root 指自己),有就接在最新版後面 +1。

    不做驗證(lint / 內容相同跳過),那是 service 層 save_prompt 的事。
    """
    latest = get_latest_prompt_template(db, prompt_name)
    template = PromptTemplate(
        prompt_name=prompt_name,
        system_instruction=system_instruction,
        prompt=prompt,
        max_length=max_length,
        version=latest.version + 1 if latest else 1,
        root_prompt_id=latest.root_prompt_id if latest else None,
    )
    db.add(template)
    db.flush()
    if latest is None:
        # v1 的 root 是自己:id 要 flush 後才拿得到
        template.root_prompt_id = template.prompt_id
        db.flush()
    db.refresh(template)

    return template
