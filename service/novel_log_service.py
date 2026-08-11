from datetime import datetime
from util.parse_log_util import (
    is_new_turn_header,
    build_novel_logs,
    parse_log_header_line,
    parse_log_to_dict,
)
from sqlalchemy.orm import Session
from util.db_util import SessionLocal
from util.crud.novel_log import insert_novel_logs, get_novel_logs


def parse_and_import(
    character_id: int, user_name: str, content: str, db: Session
) -> int:
    novel_log_batch_insert_list = []

    print(f"log_parser start. character_id:[{character_id}]")

    # 前一情景狀態
    current_state = {
        "page": None,
        "story_date": None,
        "story_time": None,
        "raw_location": None,
        "is_spinoff": False,
    }
    ## user發話(prompt)的狀態通常在下一個角色回覆的狀態欄，先放入暫存區直到讀到下一個狀態欄
    user_content_list = []

    # 轉換的
    block = {"raw_log_time": None, "sender": None, "content": []}

    # 玩家的回合
    is_user_turn = False

    # 迴圈讀行
    for line in content.splitlines():
        # strip
        clean_line = line.strip()

        if not clean_line:
            continue

        # 確認是否屬於第一行標籤
        if is_new_turn_header(line):
            if block["sender"] is not None:
                # 先把前一個block儲存清空
                novel_log_batch_insert_list.extend(
                    build_novel_logs(
                        character_id, block, current_state, user_content_list
                    )
                )
                block = {"raw_log_time": None, "sender": None, "content": []}
                user_content_list = []

            # speaker = user -> 存sender,content,raw_log_time 進暫存區
            raw_time, sender, remaining_content = parse_log_header_line(clean_line)

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

                if "#" in remaining_content or "番外" in remaining_content:
                    current_state["is_spinoff"] = True

            # 若為第一行但沒有"|" -> v1 狀態欄，塞log日期(用in效能比較好)
            if "|" in clean_line or "｜" in clean_line:
                # 有狀態欄，送parser 更新到current state
                parsed_dict = parse_log_to_dict(remaining_content, "2025")
                current_state["page"] = parsed_dict["page"]
                current_state["story_date"] = parsed_dict["story_date"]
                current_state["story_time"] = parsed_dict["story_time"]
                current_state["raw_location"] = parsed_dict["raw_location"]
                current_state["is_spinoff"] = parsed_dict.get(
                    "is_spinoff", current_state["is_spinoff"]
                )
                block["raw_log_time"] = raw_time
                block["sender"] = sender
                block["content"].append(remaining_content)
                continue
            else:
                block["raw_log_time"] = raw_time
                block["sender"] = sender
                block["content"].append(remaining_content)
                continue
        else:
            if is_user_turn:
                user_content_list[-1]["content"].append(clean_line)
            else:
                # 否的話將content串起來
                block["content"].append(clean_line)

    # 最後一圈直接轉換
    novel_log_batch_insert_list.extend(
        build_novel_logs(character_id, block, current_state, user_content_list)
    )

    import_cnt = insert_novel_logs(db, novel_log_batch_insert_list)
    print(f"新增[{import_cnt}]筆 記錄")
    # db.commit() # db_util層的yield會commit

    print("log_parser finished.")
    return import_cnt


def assemble_dialogue(
    character_id: int,
    db: Session,
    range_start: datetime | str | None = None,
    range_end: datetime | str | None = None,
) -> tuple[str, str]:
    novel_logs = get_novel_logs(db, character_id, range_start, range_end)
    dialogue_list = []
    final_page = None

    for log in novel_logs:
        log_content = log.content.strip() if log.content else ""

        if log_content:
            dialogue_list.append(log_content)

        page = log.page.strip() if log.page else None
        if page:
            final_page = page

    return "\n\n".join(dialogue_list), final_page


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
