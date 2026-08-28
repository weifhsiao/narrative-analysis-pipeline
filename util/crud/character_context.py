from sqlalchemy import select
from sqlalchemy.orm import Session
from util.models import CharacterContext


def create_context(db: Session, ctx: CharacterContext) -> CharacterContext:
    db.add(ctx)
    db.flush()
    db.refresh(ctx)
    return ctx


def get_context(db: Session, context_id: int) -> CharacterContext | None:
    return db.get(CharacterContext, context_id)


def get_contexts_by_character(db: Session, character_id: int) -> list[CharacterContext]:
    stmt = (
        select(CharacterContext)
        .where(CharacterContext.character_id == character_id)
        .order_by(CharacterContext.sort_order, CharacterContext.context_id)
    )
    return db.execute(stmt).scalars().all()


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
