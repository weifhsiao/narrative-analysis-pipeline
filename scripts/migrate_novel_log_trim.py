"""從 novel_log 拔掉 5 個格式衍生欄位:page / story_date / story_time / raw_location / is_spinoff。

這些欄位是從自製 RP log 狀態欄(|page.671|2/9|晨|地點|)硬拆出來的,pipeline 沒有任何一支在讀;
且狀態欄整行仍原封留在 content 文字裡(parser 未拆走),故拔欄位零分析損失。

用法:
    python -m scripts.migrate_novel_log_trim            # dry-run,只預覽會拔哪些欄
    python -m scripts.migrate_novel_log_trim --write     # 真的執行(先自動備份 novel.db)

SQLite 3.35+ 支援 ALTER TABLE DROP COLUMN,不需重建表;rows 原封不動。
fresh clone 無 DB 時無需遷移——create_all 會直接依新 model 建表。
"""
import shutil
import sys

from util.db_util import engine, DB_DIR

DROP_COLS = ["page", "story_date", "story_time", "raw_location", "is_spinoff"]
DB_PATH = DB_DIR / "novel.db"


def existing_columns(conn) -> list[str]:
    rows = conn.exec_driver_sql("PRAGMA table_info(novel_log)").fetchall()
    return [r[1] for r in rows]  # r[1] = column name


def row_count(conn) -> int:
    return conn.exec_driver_sql("SELECT COUNT(*) FROM novel_log").scalar()


def main(write: bool) -> None:
    if not DB_PATH.exists():
        print(f"找不到 DB:{DB_PATH}(fresh clone 由 create_all 直接建新 schema,無需遷移)")
        return

    with engine.connect() as conn:
        before = existing_columns(conn)
        cnt_before = row_count(conn)

    print(f"目前 novel_log 欄位:{before}")
    print(f"目前 rows:{cnt_before}")

    to_drop = [c for c in DROP_COLS if c in before]
    if not to_drop:
        print("沒有可拔的欄位(可能已遷移過),不動作。")
        return
    print(f"將拔除:{to_drop}")

    if not write:
        print("\n[dry-run] 未執行。加 --write 才真的拔欄位。")
        return

    # 備份(呼應「保留既有資料」)
    bak = DB_PATH.with_suffix(".db.bak")
    shutil.copy2(DB_PATH, bak)
    print(f"\n已備份:{bak}")

    with engine.begin() as conn:
        for c in to_drop:
            conn.exec_driver_sql(f"ALTER TABLE novel_log DROP COLUMN {c}")
            print(f"  DROP COLUMN {c} ✓")

    with engine.connect() as conn:
        after = existing_columns(conn)
        cnt_after = row_count(conn)

    print(f"\n完成。novel_log 欄位:{after}")
    print(f"rows:{cnt_after}(遷移前 {cnt_before})")
    if cnt_after != cnt_before:
        raise SystemExit(f"⚠️ row 數變了({cnt_before}→{cnt_after})!請用 {bak} 還原。")


if __name__ == "__main__":
    main(write="--write" in sys.argv)
