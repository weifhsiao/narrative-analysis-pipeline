from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from util import config

# 跟 SQL_ECHO 一樣在 import 時決定:engine 建好後換 DB_PATH 不會生效
DB_PATH = config.db_path()
DB_DIR = DB_PATH.parent
DB_DIR.mkdir(exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=config.sql_echo())
SessionLocal = sessionmaker(engine)


def quiet_sql() -> None:
    """報告型 CLI(lint / import_prompts / eval)用:就算 .env 開了 SQL_ECHO,輸出也不被 SQL log 洗掉。"""
    engine.echo = False


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