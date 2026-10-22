"""掃 DB 裡各支 prompt 最新版的填空標籤,跑 pipeline 之前先抓出對不上的地方(手動全面體檢)。
存 prompt(import_prompts)與 pipeline 開跑前都會自動 lint;這支用在 context 端改動後想整體檢查時。
用法:
    python -m scripts.lint_prompts                  # 全域:標籤 ↔ run 參數 / DB context_type
    python -m scripts.lint_prompts --character 2    # 加查該角色缺哪些 prompt 會用到的 type
有 ERROR 時 exit 1(WARN/INFO 不影響)。
"""
import argparse
import sys

from util.db_util import SessionLocal, quiet_sql
from service.prompt_service import lint_prompts


def main():
    parser = argparse.ArgumentParser(description="prompt 標籤 lint")
    parser.add_argument("--character", type=int, default=None, help="加查此角色的 context 覆蓋")
    args = parser.parse_args()

    quiet_sql()

    db = SessionLocal()
    try:
        issues = lint_prompts(db, args.character)
    finally:
        db.close()

    for i in issues:
        print(f"[{i.level:5}] {i.prompt or '-':14} {i.message}")

    counts = {lv: sum(1 for i in issues if i.level == lv) for lv in ("ERROR", "WARN", "INFO")}
    print(f"\nERROR {counts['ERROR']} / WARN {counts['WARN']} / INFO {counts['INFO']}")
    sys.exit(1 if counts["ERROR"] else 0)


if __name__ == "__main__":
    main()
