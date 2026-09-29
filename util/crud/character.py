from sqlalchemy import select
from sqlalchemy.orm import Session
from util.models import Character


def get_character(db: Session, character_id: int) -> Character | None:
    stmt = select(Character).where(Character.character_id == character_id)
    return db.execute(stmt).scalar_one_or_none()


def get_all_characters(db: Session) -> list[Character]:
    stmt = select(Character)
    return db.execute(stmt).scalars().all()


# insert
def create_character(db: Session, name: str) -> Character:
    character = Character(name=name)
    db.add(character)
    db.flush()
    db.refresh(character)
    return character


# def delete_character(db:Session,character_id):
