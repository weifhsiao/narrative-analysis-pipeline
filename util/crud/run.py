from sqlalchemy import select
from sqlalchemy.orm import Session
from util.models import Run


# create
def create_run(db: Session, run: Run) -> Run:
    db.add(run)
    db.flush()
    db.refresh(run)

    return run


# query
def get_run(db: Session, run_id: int) -> Run | None:
    stmt = select(Run).where(Run.run_id == run_id)

    return db.execute(stmt).scalar_one_or_none()


# query by character
def get_runs_by_character(db: Session, character_id: int) -> list[Run]:
    stmt = select(Run).where(Run.character_id == character_id)

    return db.execute(stmt).scalars().all()
