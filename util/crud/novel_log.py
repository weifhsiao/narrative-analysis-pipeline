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


def get_existing_log_keys(
    db: Session, character_id: int, range_start: datetime, range_end: datetime
) -> set[tuple[datetime, str]]:
    # 去重用:時間範圍內既有的 (raw_log_time, sender)
    stmt = select(NovelLog.raw_log_time, NovelLog.sender).where(
        NovelLog.character_id == character_id,
        NovelLog.raw_log_time >= range_start,
        NovelLog.raw_log_time <= range_end,
    )
    return {(row.raw_log_time, row.sender) for row in db.execute(stmt)}


def _coerce_dt(value: datetime | str | None) -> datetime | None:
    # 邊界可能是 datetime，也可能是 run 表 String 欄讀回來的字串。
    # 轉成 datetime 後綁定才會帶 .000000，與 raw_log_time 同精度可正確比較。
    if value is None or isinstance(value, datetime):
        return value
    value = value.strip()
    if not value:
        return None
    return datetime.fromisoformat(value)


def get_novel_logs(
    db: Session,
    character_id: int,
    range_start: datetime | str | None = None,
    range_end: datetime | str | None = None,
) -> list[NovelLog]:
    range_start = _coerce_dt(range_start)
    range_end = _coerce_dt(range_end)

    stmt = select(NovelLog).where(NovelLog.character_id == character_id)

    if range_start is not None:
        stmt = stmt.where(NovelLog.raw_log_time >= range_start)
    if range_end is not None:
        stmt = stmt.where(NovelLog.raw_log_time <= range_end)
    # 同一秒的(user 與角色回覆、Scene 與 Environment)照寫入順序排;
    # 少了 novel_log_id,SQLite 走唯一索引時會改成依 sender 字序,對話順序會反過來
    stmt = stmt.order_by(NovelLog.raw_log_time, NovelLog.novel_log_id)
    return db.execute(stmt).scalars().all()


def get_neighbor_logs(
    db: Session, character_id: int, pivot: datetime, before: bool, limit: int = 20
) -> list[NovelLog]:
    # 斷層檢查用:pivot 之前(或之後)最近的幾則,由近到遠
    if before:
        stmt = select(NovelLog).where(
            NovelLog.character_id == character_id, NovelLog.raw_log_time < pivot
        ).order_by(NovelLog.raw_log_time.desc())
    else:
        stmt = select(NovelLog).where(
            NovelLog.character_id == character_id, NovelLog.raw_log_time > pivot
        ).order_by(NovelLog.raw_log_time)
    return list(db.execute(stmt.limit(limit)).scalars().all())
