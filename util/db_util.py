import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# engine 在 import 當下建立,入口(API/script)不一定已 load .env,這裡自己 load(不覆蓋既有環境變數)
load_dotenv()

DB_DIR = Path("./data")
DB_DIR.mkdir(exist_ok=True)

# SQL_ECHO=true 時印出 SQL(dev debug 用);預設關閉,demo/截圖不被 SQL log 洗版
SQL_ECHO = os.getenv("SQL_ECHO", "false").strip().lower() in ("1", "true", "yes")

engine = create_engine(f"sqlite:///{DB_DIR}/novel.db", echo=SQL_ECHO)
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