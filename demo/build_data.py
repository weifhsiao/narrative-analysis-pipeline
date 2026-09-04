"""
產生 demo/data.js：把 examples/sample_log.txt 依 util/parse_log_util 的正則邏輯
解析成結構化 turn，並讀入 examples/results/ 的四份分析輸出，輸出成 window.DEMO_DATA。

刻意複製 parser 的 regex，讓 demo 的「解析」呈現與真實 pipeline 一致。
純靜態產物；之後接真實 API 時，把前端讀 data.js 換成打 API 即可。

用法： python demo/build_data.py
"""
import json
import re
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --- 與 util/parse_log_util.py 對齊的 regex ---
first_line_reg = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.*?):?$"
find_time_and_sander_reg = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*([^:]+):"
page_reg = r"^page\.?\s*"
date_reg = r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}"
time_reg = r"\d{1,2}\s*[:：]\s*\d{2}|深夜|清晨|上午|下午|晚上|白天|半夜|凌晨"
parted_reg = r"[|｜]"

CURRENT_YEAR = "2026"


def parse_state_line(line: str):
    """複製 parse_log_to_dict：從 `> page.31｜date｜time｜location｜...` 抽出欄位。"""
    result = {"page": None, "story_date": None, "story_time": None, "raw_location": None}
    for content in re.split(parted_reg, line):
        clean = content.strip().lstrip(">").strip()
        if not clean:
            continue
        if re.search(page_reg, clean, re.IGNORECASE):
            result["page"] = re.sub(page_reg, "", clean, flags=re.IGNORECASE)
            continue
        if re.search(date_reg, clean):
            raw = re.search(date_reg, clean).group().replace("/", "-")
            if len(raw) <= 5:
                raw = f"{CURRENT_YEAR}-{raw}"
            try:
                result["story_date"] = datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                result["story_date"] = raw
            continue
        if re.search(time_reg, clean):
            t = clean
            if re.search(r"\d", t):
                t = re.sub(r"\s*[:：]\s*", ":", t)
            result["story_time"] = t
            continue
        result["raw_location"] = clean
    return result


def is_header(line: str) -> bool:
    return bool(re.match(first_line_reg, line))


def split_turns(raw: str):
    turns = []
    cur = None
    for line in raw.splitlines():
        if is_header(line):
            m = re.match(find_time_and_sander_reg, line.strip())
            if m:
                t, sender = m.group(1), m.group(2).strip()
                remaining = line[m.end():].strip()
            else:
                m2 = re.match(first_line_reg, line.strip())
                t, sender, remaining = m2.group(1), m2.group(2).strip(), ""
            cur = {"time": t, "sender": sender, "lines": []}
            if remaining:
                cur["lines"].append(remaining)
            turns.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    return turns


def classify(sender: str) -> str:
    if sender.startswith("Scene") or sender.startswith("Environment"):
        return "system"
    return "dialogue"


def build():
    raw = (REPO / "examples/sample_log.txt").read_text(encoding="utf-8")
    turns = split_turns(raw)

    records = []
    pending_user = []
    for tr in turns:
        kind = classify(tr["sender"])
        state = None
        raw_header = None
        for ln in tr["lines"]:
            probe = ln.strip().lstrip(">").strip()
            if re.match(page_reg, probe, re.IGNORECASE):
                state = parse_state_line(ln)
                raw_header = ln.strip()
        content = "\n".join(tr["lines"]).strip()  # 保留完整內文（含 > page 頁首行）

        rec = {
            "time": tr["time"], "sender": tr["sender"], "kind": kind,
            "has_header": state is not None, "raw_header": raw_header, "content": content,
            "page": None, "story_date": None, "story_time": None, "location": None,
        }
        if kind == "system":
            records.append(rec)
            continue
        if state is not None:
            for pu in pending_user:
                pu.update(page=state["page"], story_date=state["story_date"],
                          story_time=state["story_time"], location=state["raw_location"])
            pending_user = []
            rec.update(role="ai", page=state["page"], story_date=state["story_date"],
                       story_time=state["story_time"], location=state["raw_location"])
            records.append(rec)
        else:
            rec["role"] = "user"
            records.append(rec)
            pending_user.append(rec)

    results = {}
    for k, p in {
        "recap": "examples/results/01_recap.txt",
        "relationship": "examples/results/02_relationship.txt",
        "summary": "examples/results/03_summary.txt",
        "timeline": "examples/results/04_timeline.txt",
    }.items():
        results[k] = (REPO / p).read_text(encoding="utf-8").strip()

    data = {"raw": raw, "turns": records, "results": results}
    out = REPO / "demo/data.js"
    out.write_text(
        "// 自動產生（demo/build_data.py）：examples/sample_log.txt + examples/results/*\n"
        "window.DEMO_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    dlg = [r for r in records if r["kind"] == "dialogue"]
    print(f"turns={len(records)} dialogue={len(dlg)} -> {out.relative_to(REPO)}")


if __name__ == "__main__":
    build()
