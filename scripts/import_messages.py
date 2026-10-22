"""訊息清單(JSON)匯入 novel_log。預設 dry-run 只回報,加 --write 才寫入。

JSON 格式:
    {"character_name": "選填,來源端角色名",
     "messages": [{"sender": "…", "time": "2026-10-18T03:07:16.401+08:00", "content": "…"}]}
time 帶時區會換成台灣時間;不帶時區視為台灣時間。檔名給 `-` 讀 stdin。

用法:python -m scripts.import_messages <json檔|-> --character-id 5 [--write]
"""
import argparse
import json
import sys
from datetime import datetime

from service.message_import_service import Message, MessageImportError, format_report, import_messages
import util.db_util as db_util


def load_payload(raw: str) -> tuple[str | None, list[Message]]:
    try:
        data = json.loads(raw)
        messages = [
            Message(sender=m["sender"], time=datetime.fromisoformat(m["time"]), content=m["content"])
            for m in data["messages"]
        ]
    except (KeyError, TypeError, ValueError) as e:
        raise MessageImportError(f"JSON 格式不符:{e!r}")
    return data.get("character_name"), messages


def run(raw: str, character_id: int, write: bool) -> int:
    """JSON 字串 → 匯入並印報告;其他入口(例如本機的來源轉接器)也走這裡。"""
    try:
        character_name, messages = load_payload(raw)
        with db_util.SessionLocal() as db:
            report = import_messages(db, character_id, messages, character_name, dry_run=not write)
            if write:
                db.commit()
    except MessageImportError as e:
        print(f"匯入失敗:{e}", file=sys.stderr)
        return 1

    print(format_report(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="訊息清單(JSON)匯入 novel_log")
    parser.add_argument("path", help="JSON 檔路徑,`-` 讀 stdin")
    parser.add_argument("--character-id", type=int, required=True)
    parser.add_argument("--write", action="store_true", help="真的寫入(預設只 dry-run)")
    args = parser.parse_args(argv)

    if args.path == "-":
        raw = sys.stdin.read()
    else:
        with open(args.path, encoding="utf-8") as f:
            raw = f.read()
    return run(raw, args.character_id, args.write)


if __name__ == "__main__":
    sys.exit(main())
