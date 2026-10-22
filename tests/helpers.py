"""建測試資料的小工具：每個測試自己建需要的資料，看測試本身就知道前提。"""
from datetime import datetime

from sqlalchemy.orm import Session

from service.prompt_service import parse_prompt_file
from util.crud.prompt import create_prompt_version
from util.models import Character, CharacterContext, NovelLog, PromptTemplate, Run


def add_character(db: Session, name: str = "測試角色") -> int:
    character = Character(name=name)
    db.add(character)
    db.flush()
    return character.character_id


def add_context(
    db: Session,
    character_id: int,
    context_type: str,
    content: str,
    *,
    sort_order: int = 0,
    active: bool = True,
) -> None:
    db.add(
        CharacterContext(
            character_id=character_id,
            context_type=context_type,
            context_content=content,
            sort_order=sort_order,
            is_active=active,
        )
    )
    db.flush()


def add_log(db: Session, character_id: int, content: str, at: str) -> None:
    db.add(
        NovelLog(
            character_id=character_id,
            raw_log_time=datetime.fromisoformat(at),
            sender="user",
            content=content,
        )
    )
    db.flush()


def add_run(db: Session, character_id: int, start: str, end: str) -> int:
    run = Run(character_id=character_id, range_type=1, range_start=start, range_end=end)
    db.add(run)
    db.flush()
    return run.run_id


def add_prompt(db: Session, name: str, text: str) -> PromptTemplate:
    """以 prompts/*.txt 的格式寫一版 prompt 進 DB。

    直接走 crud、不經 save_prompt 的 lint——才能放進「壞掉的」prompt，
    模擬 DB 內容與 context 對不上的情況（pipeline preflight 要擋的就是這種）。
    """
    system, prompt = parse_prompt_file(text)
    return create_prompt_version(db, name, system, prompt)
