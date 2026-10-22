from sqlalchemy import select, func
from sqlalchemy.orm import Session
from util.models import Run, PromptExecution


# create
def create_run(db: Session, run: Run) -> Run:
    db.add(run)
    db.flush()
    db.refresh(run)

    return run


# query:run 連同底下 prompt_execution 筆數(exec_cnt)一起查
def _runs_with_exec_cnt(db: Session, *where) -> list[Run]:
    stmt = (
        select(Run, func.count(PromptExecution.prompt_exec_id).label("exec_cnt"))
        .outerjoin(
            PromptExecution, PromptExecution.run_id == Run.run_id
        )  # run 接上它的 executions
        .where(*where)
        .group_by(Run.run_id)  # 「照 run 分組」→ 每組數一次
    )

    runs = []
    for row in db.execute(stmt).all():
        row.Run.exec_cnt = row.exec_cnt
        runs.append(row.Run)

    return runs


def get_run(db: Session, run_id: int) -> Run | None:
    runs = _runs_with_exec_cnt(db, Run.run_id == run_id)
    return runs[0] if runs else None


# query by character
def get_runs_by_character(db: Session, character_id: int) -> list[Run]:
    return _runs_with_exec_cnt(db, Run.character_id == character_id)
