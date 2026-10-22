from dataclasses import dataclass
from datetime import datetime
from util.parse_log_util import build_novel_logs, parse_log_header_line
from sqlalchemy.orm import Session
from util.db_util import SessionLocal
from util.crud.novel_log import insert_novel_logs, get_novel_logs, get_existing_log_keys
from util.models import NovelLog


@dataclass
class ImportResult:
    inserted: int
    skipped: int


def insert_new_novel_logs(
    db: Session, character_id: int, novel_logs: list[NovelLog]
) -> ImportResult:
    """所有 novel_log 寫入的共用入口:同線、同秒、同發話者已存在(或同批重複)就跳過。"""
    if not novel_logs:
        return ImportResult(inserted=0, skipped=0)

    times = [log.raw_log_time for log in novel_logs]
    seen = get_existing_log_keys(db, character_id, min(times), max(times))

    new_logs = []
    for log in novel_logs:
        key = (log.raw_log_time, log.sender)
        if key in seen:
            continue
        seen.add(key)
        new_logs.append(log)

    inserted = insert_novel_logs(db, new_logs)
    return ImportResult(inserted=inserted, skipped=len(novel_logs) - inserted)


def parse_and_import(
    character_id: int, user_name: str, content: str, db: Session
) -> ImportResult:
    novel_log_batch_insert_list = []

    print(f"log_parser start. character_id:[{character_id}]")

    ## user發話(prompt)的狀態通常在下一個角色回覆的狀態欄，先放入暫存區直到讀到下一個狀態欄
    user_content_list = []

    # 轉換的
    block = {"raw_log_time": None, "sender": None, "content": []}

    # 玩家的回合
    is_user_turn = False

    # 是否已讀到第一個 turn header；在此之前的行皆為檔案匯出表頭，略過
    seen_first_header = False

    # 迴圈讀行
    for line_no, line in enumerate(content.splitlines(), start=1):
        # strip
        clean_line = line.strip()

        if not clean_line:
            continue

        # 確認是否屬於第一行標籤
        header = parse_log_header_line(clean_line, line_no)
        if header is not None:
            seen_first_header = True
            if block["sender"] is not None:
                # 先把前一個block儲存清空
                novel_log_batch_insert_list.extend(
                    build_novel_logs(character_id, block, user_content_list)
                )
                block = {"raw_log_time": None, "sender": None, "content": []}
                user_content_list = []

            # speaker = user -> 存sender,content,raw_log_time 進暫存區
            raw_time, sender, remaining_content = header

            if user_name == sender:
                is_user_turn = True
                user_block = {
                    "raw_log_time": raw_time,
                    "sender": sender,
                    "content": [remaining_content],
                }
                user_content_list.append(user_block)
                continue
            else:
                # 角色header
                is_user_turn = False

            # 狀態欄(|page.671|2/9|晨|地點| 這種)仍原封留在 content 文字裡,
            # 不再拆成欄位,LLM 分析直接讀 content。
            block["raw_log_time"] = raw_time
            block["sender"] = sender
            block["content"].append(remaining_content)
            continue
        else:
            # 第一個 turn header 之前的行皆為匯出表頭，略過不併入任何 block
            if not seen_first_header:
                continue

            if is_user_turn:
                user_content_list[-1]["content"].append(clean_line)
            else:
                # 否的話將content串起來
                block["content"].append(clean_line)

    # 最後一圈直接轉換
    novel_log_batch_insert_list.extend(
        build_novel_logs(character_id, block, user_content_list)
    )

    result = insert_new_novel_logs(db, character_id, novel_log_batch_insert_list)
    print(f"新增[{result.inserted}]筆 記錄，略過已存在[{result.skipped}]筆")
    # db.commit() # db_util層的yield會commit

    print("log_parser finished.")
    return result


def assemble_dialogue(
    character_id: int,
    db: Session,
    range_start: datetime | str | None = None,
    range_end: datetime | str | None = None,
) -> str:
    novel_logs = get_novel_logs(db, character_id, range_start, range_end)
    dialogue_list = []

    for log in novel_logs:
        log_content = log.content.strip() if log.content else ""

        if log_content:
            dialogue_list.append(log_content)

    return "\n\n".join(dialogue_list)


# 腳本執行->讀檔

if __name__ == "__main__":
    source_dir = "examples"
    source_file_name = "sample_log.txt"

    user_name = "沈曉棠"
    character_id = 1

    with open(f"{source_dir}/{source_file_name}", "r", encoding="utf-8") as f_in:
        print(f"log_parser start. file:[{source_dir}/{source_file_name}]")
        with SessionLocal() as db:
            content = f_in.read()
            parse_and_import(character_id, user_name, content, db)
            db.commit()  # script路徑需自己commit因為取連線不是透過util
    print("[script] log_parser finished.")
