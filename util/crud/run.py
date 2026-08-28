from sqlalchemy import select, func
from sqlalchemy.orm import Session
from util.models import Run, PromptExecution


# create
def create_run(db: Session, run: Run) -> Run:
    db.add(run)
    db.flush()
    db.refresh(run)

    return run


# query
def get_run(db: Session, run_id: int) -> Run | None:
    stmt = (
        select(Run, func.count(PromptExecution.prompt_exec_id).label("exec_cnt"))
        .outerjoin(
            PromptExecution, PromptExecution.run_id == Run.run_id
        )  # run 接上它的 executions
        .where(Run.run_id == run_id)
        .group_by(Run.run_id)  # 「照 run 分組」→ 每組數一次
    )

    row = db.execute(stmt).one_or_none()

    if row is None:
        return None

    run = row.Run
    run.exec_cnt = row.exec_cnt

    return run


# query by character
def get_runs_by_character(db: Session, character_id: int) -> list[Run]:
    stmt = (
        select(Run, func.count(PromptExecution.prompt_exec_id).label("exec_cnt"))
        .outerjoin(PromptExecution, PromptExecution.run_id == Run.run_id)
        .where(Run.character_id == character_id)
        .group_by(Run.run_id)
    )

    rows = db.execute(stmt).all()

    runs = []
    for row in rows:
        row.Run.exec_cnt = row.exec_cnt
        runs.append(row.Run)

    return runs
