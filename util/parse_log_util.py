import re
from datetime import datetime
from .models import NovelLog

# REGEX
first_line_reg = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.*?):?$"
remove_first_line_reg = r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*"
find_time_and_sander_reg = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*([^:]+):"


"""
確認是否屬於log第一行
"""


def is_new_turn_header(line: str):
    return bool(re.match(first_line_reg, line))


def parse_log_header_line(line: str):
    match_obj = re.match(find_time_and_sander_reg, line.strip())
    if match_obj:
        raw_log_str = match_obj.group(1).strip()
        try:
            raw_log_time = datetime.strptime(raw_log_str, "%Y-%m-%d %H:%M:%S")
        except ValueError as e:
            raise ValueError(f"無法解析 raw_log_time:[{raw_log_str}]") from e

        sender = match_obj.group(2).strip()
        remaining_content = line[match_obj.end() :].strip()
        return raw_log_time, sender, remaining_content

    return None, None, None


def remove_timestamp(line: str):
    return re.sub(remove_first_line_reg, "", line)


def build_novel_logs(
    character_id: int, block: dict, pending_list: list
) -> list[NovelLog]:
    result_list = []

    if block["sender"] is None:
        return result_list

    # 存user

    for user_block in pending_list:
        result_list.append(build_novel_log(character_id, user_block))

    # 存角色
    result_list.append(build_novel_log(character_id, block))

    return result_list


def build_novel_log(character_id: int, block: dict) -> NovelLog:
    # not null column check
    raw_log_time = block["raw_log_time"]
    sender = block["sender"]

    if raw_log_time is None:
        raise ValueError("raw_log_time 不可為 None！")
    elif sender is None:
        raise ValueError("sender 不可為 None！")

    novel_log = NovelLog(
        character_id=character_id,
        raw_log_time=raw_log_time,
        sender=sender,
        content="\n".join(block["content"]).strip(),
    )

    return novel_log
