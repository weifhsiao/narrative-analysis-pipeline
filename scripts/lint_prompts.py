"""掃 prompts/*.txt 的填空標籤,跑 pipeline 之前先抓出對不上的地方。
用法:
    python -m scripts.lint_prompts                  # 全域:標籤 ↔ run 參數 / DB context_type
    python -m scripts.lint_prompts --character 2    # 加查該角色缺哪些 prompt 會用到的 type
有 ERROR 時 exit 1(WARN/INFO 不影響)。
"""
import argparse
import logging
import sys

from util.db_util import SessionLocal
from service.prompt_service import lint_prompts


def main():
    parser = argparse.ArgumentParser(description="prompt 標籤 lint")
    parser.add_argument("--character", type=int, default=None, help="加查此角色的 context 覆蓋")
    args = parser.parse_args()

    # 就算 .env 開了 SQL_ECHO,lint 報告也要看得到:這支工具固定壓掉 SQL log
    logging.disable(logging.INFO)

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
