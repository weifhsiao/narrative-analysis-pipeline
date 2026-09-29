"""⑥ prompt 模板入庫的 schema 遷移。

- prompt_template:改成 append-only 版本表(加 root_prompt_id / version / max_length、
  拿掉 updated_at、加 unique(root_prompt_id, version))。SQLite 無法對既有表補 constraint,
  且此表入庫前從未被使用(0 筆),所以直接 DROP 後依新 model 重建;有資料就中止不動。
- prompt_execution:ADD COLUMN 快照(system_snapshot / prompt_snapshot)與 AI 用量
  (model / input_tokens / output_tokens / thinking_tokens)。既有列新欄位為 NULL,不回填。

用法:
    python -m scripts.migrate_prompt_template            # dry-run,只預覽會做什麼
    python -m scripts.migrate_prompt_template --write    # 真的執行(先自動備份 novel.db)

fresh clone 無 DB 時無需遷移——create_all 會直接依新 model 建表。
遷移完再跑 `python -m scripts.import_prompts` 把 prompts/*.txt 匯入。
"""
import shutil
import sys
from datetime import datetime

from util.db_util import engine, DB_DIR, DB_PATH
from util.models import PromptTemplate


TEMPLATE_NEW_COLS = ["root_prompt_id", "version", "max_length"]
EXEC_ADD_COLS = {
    "system_snapshot": "VARCHAR",
    "prompt_snapshot": "VARCHAR",
    "model": "VARCHAR",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "thinking_tokens": "INTEGER",
}


def columns(conn, table: str) -> list[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]  # r[1] = column name


def row_count(conn, table: str) -> int:
    return conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()


def main(write: bool) -> None:
    if not DB_PATH.exists():
        print(f"找不到 DB:{DB_PATH}(fresh clone 由 create_all 直接建新 schema,無需遷移)")
        return

    with engine.connect() as conn:
        template_cols = columns(conn, "prompt_template")
        template_rows = row_count(conn, "prompt_template")
        exec_cols = columns(conn, "prompt_execution")
        exec_rows = row_count(conn, "prompt_execution")

    rebuild_template = not set(TEMPLATE_NEW_COLS) <= set(template_cols)
    exec_to_add = {c: t for c, t in EXEC_ADD_COLS.items() if c not in exec_cols}

    print(f"prompt_template 欄位:{template_cols}(rows {template_rows})")
    print(f"prompt_execution 欄位:{exec_cols}(rows {exec_rows})")

    if not rebuild_template and not exec_to_add:
        print("已是新 schema(可能已遷移過),不動作。")
        return
    if rebuild_template:
        if template_rows:
            raise SystemExit(
                f"⚠️ prompt_template 已有 {template_rows} 筆,DROP 重建會丟資料,中止。請手動遷移。"
            )
        print("將重建 prompt_template(0 筆,DROP 後依新 model 建表)")
    if exec_to_add:
        print(f"將對 prompt_execution 加欄位:{list(exec_to_add)}")

    if not write:
        print("\n[dry-run] 未執行。加 --write 才真的遷移。")
        return

    # 帶時間戳,不蓋掉前幾次遷移留下的 novel.db.bak
    bak = DB_DIR / f"novel_{datetime.now():%Y%m%d%H%M}.db.bak"
    shutil.copy2(DB_PATH, bak)
    print(f"\n已備份:{bak}")

    with engine.begin() as conn:
        if rebuild_template:
            conn.exec_driver_sql("DROP TABLE prompt_template")
            PromptTemplate.__table__.create(conn)
            print("  prompt_template 重建 ✓")
        for c, t in exec_to_add.items():
            conn.exec_driver_sql(f"ALTER TABLE prompt_execution ADD COLUMN {c} {t}")
            print(f"  ADD COLUMN prompt_execution.{c} ✓")

    with engine.connect() as conn:
        exec_rows_after = row_count(conn, "prompt_execution")
        print(f"\n完成。prompt_template 欄位:{columns(conn, 'prompt_template')}")
        print(f"prompt_execution 欄位:{columns(conn, 'prompt_execution')}")

    print(f"prompt_execution rows:{exec_rows_after}(遷移前 {exec_rows})")
    if exec_rows_after != exec_rows:
        raise SystemExit(f"⚠️ row 數變了({exec_rows}→{exec_rows_after})!請用 {bak} 還原。")


if __name__ == "__main__":
    main(write="--write" in sys.argv)
