from sqlalchemy import select
from sqlalchemy.orm import Session
from util.models import NovelLog
from datetime import datetime


# single insert
def insert_novel_log(db: Session, novel_log: NovelLog) -> NovelLog:
    db.add(novel_log)
    db.flush()
    db.refresh(novel_log)
    return novel_log


# batch insert
def insert_novel_logs(db: Session, novel_logs: list[NovelLog]) -> int:
    db.add_all(novel_logs)
    db.flush()
    return len(novel_logs)


def get_novel_logs(
    db: Session,
    character_id: int,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
) -> list[NovelLog]:
    stmt = select(NovelLog).where(NovelLog.character_id == character_id)

    if range_start and range_end:
        stmt = stmt.where(
            NovelLog.raw_log_time >= range_start, NovelLog.raw_log_time <= range_end
        )
    stmt = stmt.order_by(NovelLog.raw_log_time)
    return db.execute(stmt).scalars().all()
