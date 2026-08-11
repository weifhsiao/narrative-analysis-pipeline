import re
from datetime import datetime
from .models import NovelLog

# REGEX
first_line_reg = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.*?):?$"
remove_first_line_reg = r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*"
find_time_and_sander_reg = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*([^:]+):"
page_reg = r"^page\.?\s*"
## date有YYYY/mm/dd,mm/dd兩種格式
date_reg = r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}"
time_reg = r"\d{1,2}\s*[:：]\s*\d{2}|深夜|清晨|上午|下午|晚上|白天|半夜|凌晨"
parted_reg = r"[|｜]"

"""
# 將log轉成dict
## 格式：
    {
    page: str, 
    story_date: str, 
    story_time: str,
    raw_location:str
    }
"""


def parse_log_to_dict(content_to_dict: str, current_year: str):
    result_dict = {
        "page": None,
        "story_date": None,
        "story_time": None,
        "raw_location": None,
    }

    split_content = re.split(parted_reg, content_to_dict)
    # print(f"parse_log_to_dict.split_content:[{split_content}]")

    for content in split_content:
        clean_content = content.strip().lstrip(">").strip()

        # 空的
        if not clean_content:
            continue

        # 取頁數
        if re.search(page_reg, clean_content, re.IGNORECASE):
            # 把page以外的東西都移除

            # page_match = re.search(r"\d+", clean_content)
            # print(page_match.group())
            result_dict["page"] = re.sub(
                page_reg, "", clean_content, flags=re.IGNORECASE
            )
            continue

        # 日期
        if re.search(date_reg, clean_content):
            date_match = re.search(date_reg, clean_content)
            raw_date = date_match.group().replace("/", "-")

            ### 格式為mm/dd，補年份
            if len(raw_date) <= 5:
                raw_date = f"{current_year}-{raw_date}"

            try:
                dt_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                result_dict["story_date"] = dt_obj.strftime("%Y-%m-%d")
            except ValueError:
                result_dict["story_date"] = raw_date

            continue

        # 時間
        if re.search(time_reg, clean_content):
            time_str = clean_content.strip()

            ## 時間有數字的話處理冒號格式
            if re.search(r"\d", time_str):
                time_str = re.sub(r"\s*[:：]\s*", ":", time_str)

            result_dict["story_time"] = time_str
            continue

        # 都沒中 -> 地點
        result_dict["raw_location"] = clean_content

    return result_dict


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
    character_id: int, block: dict, current_state: dict, pending_list: list
) -> list[NovelLog]:
    result_list = []

    if block["sender"] is None:
        return result_list

    # 存user

    for user_block in pending_list:
        result_list.append(build_novel_log(character_id, user_block, current_state))

    # 存角色
    result_list.append(build_novel_log(character_id, block, current_state))

    return result_list


def build_novel_log(character_id: int, block: dict, current_state: dict) -> NovelLog:
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
        page=current_state["page"],
        story_date=current_state["story_date"],
        story_time=current_state["story_time"],
        raw_location=current_state["raw_location"],
        is_spinoff=current_state.get("is_spinoff", 0),
    )

    return novel_log
