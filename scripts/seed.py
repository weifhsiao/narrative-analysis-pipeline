"""建立 Quickstart 用的虛構範例資料(角色、run、預先產生的分析結果、角色 context)。

⚠️ 會先清空 character / run / prompt_execution / novel_log / character_context 再重建。
DB 裡若有 seed 以外的資料(例:真實角色、匯入過的 log、自己跑出的結果),預設拒絕執行、
不動任何資料;確定要清掉才加 --yes。prompt_template 不在清除範圍。

用法:
    python -m scripts.seed          # 空 DB 或只有 seed 資料時照常重建
    python -m scripts.seed --yes    # DB 有其他資料也清掉重建
"""
import argparse
import sys

from pathlib import Path
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from util.db_util import SessionLocal, engine
from util.models import Base, Character, CharacterContext, Run, NovelLog, PromptExecution

# range_type: 1=log_time / 2=page（未來擴充）
RANGE_TYPE_LOG_TIME = 1
BASE_DIR = Path(__file__).parent.parent
EXAMPLE_RESULTS_DIR = BASE_DIR / "examples" / "results"

SEED_CHARACTERS = [
    {"character_id": 1, "name": "顧望舒"},
]

SEED_RUNS = [
    {
        "run_id": 1,
        "character_id": 1,
        "range_type": RANGE_TYPE_LOG_TIME,
        "range_start": "2026-06-20 21:02:11",
        "range_end": "2026-06-27 21:20:47",
    },
]

# 虛構範例 context,時間點對齊 examples/sample_log.txt 開場的「發生過的劇情」(2/14~2/28)。
# type 名 = prompt 的填空標籤名;prompts/*.txt 新增 context 標籤時這裡也要補,
# 否則 import_prompts / pipeline 的 lint 會報 ERROR(tests/test_seed.py 會擋)。
SEED_CONTEXTS = [
    {
        "character_id": 1,
        "context_type": "relationship",
        "sort_order": 0,
        "title": "關係狀態總結",
        "context_content": """\
# 關係狀態總結 (更新至 2026/02/28 船票)

## 當前狀態
沈曉棠為撰寫地方誌造訪白沙嘴燈塔,與守塔人顧望舒建立每週四晚間整理受潮舊書的協作關係。兩人相處以工作為主,彼此客氣而有分寸。沈曉棠發現夾著船票的手寫日記後,顧望舒首次在她面前流露情緒並提前結束整理,雙方之間出現一段尚未說開的留白。

## 關鍵詞與互動

### 專屬稱呼
- 顧望舒 對 沈曉棠 的稱呼:
- 「寫地方誌的人」:起源於沈曉棠初訪燈塔時的身分,代表顧望舒對其來意的認知,距離感仍在。
- 沈曉棠 對 顧望舒 的稱呼:
- 「望舒先生」:起源於沈曉棠對守塔人的禮貌稱謂。

### 象徵信物
- 薑茶杯:沈曉棠 2/21 留下自製薑茶作為謝禮,顧望舒將其用過的杯子留在圖書室。

### 專屬約定
- 每週四晚間上塔整理舊書(持續中)。
- 顧望舒承諾教沈曉棠修補書脊(持續中)。
- 船票的事「下次再談」(持續中,2/28 由顧望舒提出)。""",
    },
    {
        "character_id": 1,
        "context_type": "scenario",
        "sort_order": 1,
        "title": "發生過的劇情 I",
        "context_content": """\
- 2/14 沈曉棠為撰寫地方誌初次造訪白沙嘴燈塔圖書室,借閱《霧津潮汐誌》,與守塔人顧望舒約定每週四晚間上塔協助整理受潮舊書。
- 2/21 兩人修復第一批水漬書。顧望舒示範以吸潮紙陰乾書頁,沈曉棠留下自製薑茶作為謝禮,顧望舒承諾下週教她修補書脊。""",
    },
    {
        "character_id": 1,
        "context_type": "scenario",
        "sort_order": 2,
        "title": "發生過的劇情 II",
        "context_content": """\
- 2/28 沈曉棠在待修書堆裡發現一本夾著泛黃船票的手寫日記,顧望舒見到船票後神色一沉,只說「這本先放著,下次再談」,提前結束了當晚的整理。""",
    },
    {
        "character_id": 1,
        "context_type": "timeline",
        "sort_order": 0,
        "title": "時間軸",
        "context_content": """\
- 2026/02/14 沈曉棠初訪白沙嘴燈塔圖書室,約定每週四晚間協助整理舊書。
- 2026/02/21 修復第一批水漬書;薑茶謝禮;修補書脊之約。
- 2026/02/28 發現夾著船票的手寫日記;顧望舒提前結束整理。""",
    },
]


def _seed_execution_contents() -> list[str]:
    if not EXAMPLE_RESULTS_DIR.exists():
        raise FileNotFoundError(f"Directory {EXAMPLE_RESULTS_DIR} does not exist.")
    return [f.read_text(encoding="utf-8") for f in sorted(EXAMPLE_RESULTS_DIR.glob("*.txt"))]


def find_foreign_data(db: Session) -> list[str]:
    """列出 DB 裡「不是 seed 建的」資料(每類一行說明);空 list = 可以安全重建。

    只讀不寫。表不存在視為空(舊 DB / 全新 DB)。
    """
    tables = set(inspect(db.connection()).get_table_names())
    found: list[str] = []

    def check(model, key, expected: set, label: str):
        if model.__tablename__ not in tables:
            return
        extra = [r for r in db.query(model).all() if key(r) not in expected]
        if extra:
            found.append(f"{model.__tablename__}: {len(extra)} 筆{label}")

    check(
        Character,
        lambda r: (r.character_id, r.name),
        {(c["character_id"], c["name"]) for c in SEED_CHARACTERS},
        "非 seed 角色",
    )
    check(
        Run,
        lambda r: (r.run_id, r.character_id, r.range_type, r.range_start, r.range_end),
        {(r["run_id"], r["character_id"], r["range_type"], r["range_start"], r["range_end"]) for r in SEED_RUNS},
        "非 seed run",
    )
    # 比對所有使用者可改的欄位:只停用、改標題或排序也算改過
    check(
        CharacterContext,
        lambda r: (
            r.character_id, r.context_type, r.context_content, r.sort_order, r.title, r.is_active
        ),
        {
            (
                c["character_id"], c["context_type"], c["context_content"],
                c["sort_order"], c["title"], c.get("is_active", True),
            )
            for c in SEED_CONTEXTS
        },
        "非 seed context",
    )
    check(
        PromptExecution,
        lambda r: (r.run_id, r.prompt_id, r.result_content),
        {(1, None, content) for content in _seed_execution_contents()},
        "非 seed 執行結果",
    )
    check(NovelLog, lambda r: None, set(), " log(seed 不建 log)")
    return found


def wipe_all(db: Session) -> None:
    db.query(PromptExecution).delete()
    db.query(NovelLog).delete()
    db.query(CharacterContext).delete()
    db.query(Run).delete()
    db.query(Character).delete()
    db.flush()


def seed_characters(db: Session) -> None:
    db.add_all(Character(**c) for c in SEED_CHARACTERS)
    db.flush()


def seed_runs(db: Session) -> None:
    db.add_all(Run(**r) for r in SEED_RUNS)
    db.flush()


def seed_prompt_executions(db: Session) -> None:
    db.add_all(
        PromptExecution(run_id=1, result_code="SUCCESS", result_content=content)
        for content in _seed_execution_contents()
    )
    db.flush()


def seed_contexts(db: Session) -> None:
    db.add_all(CharacterContext(**c) for c in SEED_CONTEXTS)
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="清空並建立 Quickstart 範例資料")
    parser.add_argument("--yes", action="store_true", help="DB 有 seed 以外的資料也清掉重建")
    args = parser.parse_args()

    # 先檢查再建表:被擋下時連 schema 都不動
    db = SessionLocal()
    try:
        foreign = find_foreign_data(db)
    except OperationalError as e:
        print("無法讀取 DB 確認有沒有 seed 以外的資料,已中止(未修改任何資料)。")
        print(f"    原因:{e.orig}")
        if "locked" in str(e.orig):
            print("DB 被其他程式鎖住,先關掉正在跑的 API / DB 瀏覽工具再試。")
        else:
            # 舊 schema 下 --yes 也沒用:清表會過,但寫入範例時缺欄位會失敗 rollback
            print("多半是 prompt 版本化之前建立的舊 DB:請先跑 python -m scripts.migrate_prompt_template --write;")
            print("只是想重建範例,就換一個工作目錄,或移走 data/novel.db 再跑 seed。")
        sys.exit(1)
    finally:
        db.close()
    if foreign and not args.yes:
        print("DB 裡有 seed 以外的資料,seed 會把它們清掉,已中止(未修改任何資料):")
        for line in foreign:
            print(f"    {line}")
        print("確定要清掉重建請加 --yes。")
        sys.exit(1)

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        wipe_all(db)
        seed_characters(db)
        seed_runs(db)
        seed_prompt_executions(db)
        seed_contexts(db)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error occurred: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
