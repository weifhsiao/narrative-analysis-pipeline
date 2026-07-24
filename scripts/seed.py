from dotenv import load_dotenv

load_dotenv()
from pathlib import Path
from sqlalchemy.orm import Session
from util.db_util import SessionLocal, engine
from util.models import Base, Character, Run, NovelLog, PromptExecution

# range_type: 1=log_time / 2=page（未來擴充）
RANGE_TYPE_LOG_TIME = 1
BASE_DIR = Path(__file__).parent.parent


def wipe_all(db: Session) -> None:
    db.query(PromptExecution).delete()
    db.query(NovelLog).delete()
    db.query(Run).delete()
    db.query(Character).delete()
    db.flush()


def seed_characters(db: Session) -> None:
    characters = [
        Character(character_id=1, name="顧望舒"),
    ]
    db.add_all(characters)
    db.flush()


def seed_runs(db: Session) -> None:
    runs = [
        Run(
            run_id=1,
            character_id=1,
            range_type=RANGE_TYPE_LOG_TIME,
            range_start="2026-06-20 21:02:11",
            range_end="2026-06-27 21:20:47",
        ),
    ]
    db.add_all(runs)
    db.flush()


def seed_prompt_executions(db: Session) -> None:
    example_dir = BASE_DIR / "examples" / "results"

    if not example_dir.exists():
        raise FileNotFoundError(f"Directory {example_dir} does not exist.")

    prompt_executions = []
    for file in sorted(example_dir.glob("*.txt")):
        prompt_executions.append(
            PromptExecution(
                run_id=1,
                result_code="SUCCESS",
                result_content=file.read_text(encoding="utf-8"),
            )
        )

    db.add_all(prompt_executions)
    db.flush()


def main() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        bind = db.get_bind()
        db.close()
        bind.dispose()

        db = SessionLocal()

        wipe_all(db)
        seed_characters(db)
        seed_runs(db)
        seed_prompt_executions(db)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error occurred: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
