from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

DB_DIR = Path("./data")
DB_DIR.mkdir(exist_ok=True)

engine = create_engine(f"sqlite:///{DB_DIR}/novel.db", echo=True)
SessionLocal = sessionmaker(engine)


# yield:交給呼叫方使用，最後確保關閉
def get_db():
    db = SessionLocal()
    try:
        yield db  # 會先停在這直到呼叫方跑完
        db.commit()  # 成功就commit
    except Exception:
        db.rollback()  # 失敗rollback
        raise
    finally:
        db.close()