from sqlalchemy import select, update
from sqlalchemy.orm import Session
from util.models import CharacterContext


def create_context(db: Session, ctx: CharacterContext) -> CharacterContext:
    db.add(ctx)
    db.flush()
    db.refresh(ctx)
    return ctx


# UI 列表與 prompt 內的 context 用同一個順序
_CONTEXT_ORDER = (CharacterContext.sort_order, CharacterContext.context_id)


def get_context(db: Session, context_id: int) -> CharacterContext | None:
    return db.get(CharacterContext, context_id)


def get_contexts_by_character(db: Session, character_id: int) -> list[CharacterContext]:
    stmt = (
        select(CharacterContext)
        .where(CharacterContext.character_id == character_id)
        .order_by(*_CONTEXT_ORDER)
    )
    return db.execute(stmt).scalars().all()


def get_contexts_by_type(
    db: Session, character_id: int, context_type: str
) -> list[CharacterContext]:
    """某角色某 type 的整組,含停用。"""
    stmt = (
        select(CharacterContext)
        .where(
            CharacterContext.character_id == character_id,
            CharacterContext.context_type == context_type,
        )
        .order_by(*_CONTEXT_ORDER)
    )
    return db.execute(stmt).scalars().all()


def get_active_contexts_by_type(
    db: Session, character_id: int, context_type: str
) -> list[CharacterContext]:
    stmt = (
        select(CharacterContext)
        .where(
            CharacterContext.character_id == character_id,
            CharacterContext.context_type == context_type,
            CharacterContext.is_active.is_(True),
        )
        .order_by(*_CONTEXT_ORDER)
    )
    return db.execute(stmt).scalars().all()


def list_context_types(db: Session) -> set[str]:
    """回傳 DB 現有的所有 context_type（去重）。

    供 prompt 引擎判斷某個 <T> 標籤是不是 context 標籤（而非結構標籤）。
    """
    stmt = select(CharacterContext.context_type).distinct()
    return set(db.execute(stmt).scalars().all())


def update_context(
    db: Session, context_id: int, changes: dict
) -> CharacterContext | None:
    ctx = db.get(CharacterContext, context_id)
    if ctx is None:
        return None
    for field, value in changes.items():
        setattr(ctx, field, value)
    db.flush()
    db.refresh(ctx)
    return ctx


def set_sort_orders(db: Session, context_ids: list[int]) -> None:
    """依 context_ids 的順序把 sort_order 寫成 0..n-1。

    排序不算改內容:明寫 updated_at=自己,model 的 onupdate 就不會觸發。
    """
    for n, context_id in enumerate(context_ids):
        db.execute(
            update(CharacterContext)
            .where(CharacterContext.context_id == context_id)
            .values(sort_order=n, updated_at=CharacterContext.updated_at)
        )
    db.flush()
