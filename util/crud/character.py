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


# update
def update_character(db: Session, character_id: int, name: str) -> Character | None:
    ## ORM寫法先查再改

    character = db.execute(
        select(Character).where(Character.character_id == character_id)
    ).scalar_one_or_none()

    if character is None:
        return None

    ## 用execute select出來的物件會被自動追蹤，所以這邊直接改->flush就可以了（session更新還沒commit）
    character.name = name
    db.flush()
    db.refresh(character)

    return character


# def delete_character(db:Session,character_id):
