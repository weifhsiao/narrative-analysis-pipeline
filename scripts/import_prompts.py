"""把 prompts/*.txt 匯入 prompt_template——prompt 寫進 DB 的唯一入口。

pipeline 只讀 DB;改完 .txt 要跑這支才會生效。每支 prompt:
- 與 DB 最新版內容相同 → 跳過
- 不同(或 DB 還沒有)→ 新增一版(append-only,舊版保留)
- lint 有 ERROR → 擋下不存(其他檔照常匯入),最後 exit 1

用法:
    python -m scripts.import_prompts           # 匯入全部 prompts/*.txt
    python -m scripts.import_prompts --force   # lint ERROR 也照存(例:DB 還沒有 prompt 用到的 context_type)
"""
import argparse
import sys

from util.db_util import SessionLocal, quiet_sql
from util.paths import REPO_DIR
from service.prompt_service import PromptLintError, parse_prompt_file, save_prompt

PROMPTS_DIR = REPO_DIR / "prompts"


def main():
    parser = argparse.ArgumentParser(description="匯入 prompts/*.txt 到 prompt_template")
    parser.add_argument("--force", action="store_true", help="lint 有 ERROR 也照存")
    args = parser.parse_args()

    quiet_sql()

    failed = 0
    db = SessionLocal()
    try:
        for path in sorted(PROMPTS_DIR.glob("*.txt")):
            name = path.stem
            system, prompt = parse_prompt_file(path.read_text(encoding="utf-8"))
            try:
                template, issues = save_prompt(db, name, system, prompt, force=args.force)
            except PromptLintError as e:
                failed += 1
                print(f"[擋下] {name}")
                for i in e.issues:
                    print(f"    [{i.level}] {i.message}")
                continue

            if template is None:
                print(f"[跳過] {name}(與最新版相同)")
            else:
                print(f"[新增] {name} v{template.version}(prompt_id {template.prompt_id})")
            for i in issues:
                print(f"    [{i.level}] {i.message}")
        db.commit()
    finally:
        db.close()

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
