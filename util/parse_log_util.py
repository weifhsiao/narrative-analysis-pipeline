import re
from datetime import datetime
from .models import NovelLog

# 標題行 = 時間戳開頭的行;判定與解析共用 header_prefix_reg,不會各說各話
header_prefix_reg = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*"
header_sender_reg = re.compile(r"([^:]+):")


class LogFormatError(ValueError):
    """log 格式不符,整份不匯入。訊息帶行號,給使用者直接看。"""


def parse_log_header_line(line: str, line_no: int | None = None):
    """時間戳開頭 → 標題行,回 (raw_log_time, sender, remaining_content);
    否則是內文,回 None。像標題行卻解析不了就報錯,不猜。"""
    line = line.strip()
    prefix = re.match(header_prefix_reg, line)
    if not prefix:
        return None

    where = f"第 {line_no} 行" if line_no is not None else "標題行"
    raw_log_str = prefix.group(1)
    try:
        raw_log_time = datetime.strptime(raw_log_str, "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        raise LogFormatError(f"{where}時間無法解析:[{raw_log_str}]") from e

    sender_match = header_sender_reg.match(line, prefix.end())
    sender = sender_match.group(1).strip() if sender_match else ""
    # 全形冒號當分隔時,[^:]+ 會一路吃到狀態欄時間的半形冒號(｜16:40｜),發話者變成亂碼卻不報錯
    if not sender or "：" in sender:
        raise LogFormatError(
            f"{where}是標題行,但找不到「發話者:」(需半形冒號,全形「：」不算):{line[:60]}"
        )

    remaining_content = line[sender_match.end() :].strip()
    return raw_log_time, sender, remaining_content


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
