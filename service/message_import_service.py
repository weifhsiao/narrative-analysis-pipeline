"""訊息清單匯入:與 txt 匯出無關的通用入口(任何來源轉成 sender/time/content 清單即可)。

寫入走 insert_new_novel_logs,去重規則與 txt 匯入相同;另外做頁碼斷層檢查,只提醒不擋。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from service.novel_log_service import insert_new_novel_logs
from util.crud.character import get_character
from util.crud.novel_log import get_neighbor_logs
from util.models import NovelLog
from util.parse_log_util import clean_content, parse_page_no

# raw_log_time 一律存 log 所在地的本地時間(無時區)。台灣沒有日光節約,固定 +8 即可
LOG_TIMEZONE = timezone(timedelta(hours=8))


class MessageImportError(ValueError):
    """輸入不合格,整批不匯入。訊息給使用者直接看。"""


@dataclass
class Message:
    sender: str
    time: datetime
    content: str


@dataclass
class MessageImportReport:
    character_id: int
    character_name: str
    source_character_name: str | None
    total: int
    inserted: int
    skipped: int
    dry_run: bool
    batch_created_at: datetime | None
    first_page: int | None
    last_page: int | None
    warnings: list[str] = field(default_factory=list)


def normalize_time(value: datetime) -> datetime:
    """帶時區的換成台灣時間再拿掉時區;截到秒(txt 匯出只到秒,去重鍵才對得上)。"""
    if value.tzinfo is not None:
        value = value.astimezone(LOG_TIMEZONE).replace(tzinfo=None)
    return value.replace(microsecond=0)


def _neighbor_page(db: Session, character_id: int, pivot: datetime, before: bool) -> int | None:
    for log in get_neighbor_logs(db, character_id, pivot, before=before):
        page = parse_page_no(log.content)
        if page is not None:
            return page
    return None


def _format_gap(start: int, end: int) -> str:
    return f"p.{start}" if start == end else f"p.{start}～{end}"


def check_page_gaps(db: Session, character_id: int, logs: list[NovelLog]) -> tuple[int | None, int | None, list[str]]:
    """比對本批頁碼與 DB 前後相鄰的頁碼,回 (第一頁, 最後一頁, 警告)。"""
    pages = [p for p in (parse_page_no(log.content) for log in logs) if p is not None]
    if not pages:
        return None, None, ["本批找不到頁碼(狀態欄),無法檢查斷層"]

    warnings = []
    first, last = pages[0], pages[-1]

    # 本批自己跳頁(挑選的訊息不連續)
    for prev, cur in zip(pages, pages[1:]):
        if cur > prev + 1:
            warnings.append(f"本批中間缺 {_format_gap(prev + 1, cur - 1)}")
        elif cur <= prev:
            warnings.append(f"本批頁碼沒有遞增:p.{prev} 之後是 p.{cur}")

    times = [log.raw_log_time for log in logs]
    before_page = _neighbor_page(db, character_id, min(times), before=True)
    if before_page is not None and first > before_page + 1:
        warnings.append(f"與 DB 前一段接不上:DB 到 p.{before_page},本批從 p.{first} 開始,缺 {_format_gap(before_page + 1, first - 1)}")
    after_page = _neighbor_page(db, character_id, max(times), before=False)
    if after_page is not None and after_page > last + 1:
        warnings.append(f"與 DB 後一段接不上:本批到 p.{last},DB 下一段從 p.{after_page} 開始,缺 {_format_gap(last + 1, after_page - 1)}")

    return first, last, warnings


def import_messages(
    db: Session,
    character_id: int,
    messages: list[Message],
    source_character_name: str | None = None,
    dry_run: bool = True,
) -> MessageImportReport:
    character = get_character(db, character_id)
    if character is None:
        raise MessageImportError(f"character_id [{character_id}] 不存在")
    if not messages:
        raise MessageImportError("訊息清單是空的")

    logs = []
    for i, message in enumerate(messages, start=1):
        sender = message.sender.strip()
        if not sender:
            raise MessageImportError(f"第 {i} 則缺發話者")
        logs.append(
            NovelLog(
                character_id=character_id,
                raw_log_time=normalize_time(message.time),
                sender=sender,
                content=clean_content(message.content),
            )
        )
    logs.sort(key=lambda log: log.raw_log_time)

    first_page, last_page, warnings = check_page_gaps(db, character_id, logs)
    if source_character_name and source_character_name not in character.name:
        warnings.append(f"來源角色名「{source_character_name}」與 DB 角色「{character.name}」不同,確認 character_id 是否正確")

    result = insert_new_novel_logs(db, character_id, logs, dry_run=dry_run)
    return MessageImportReport(
        character_id=character_id,
        character_name=character.name,
        source_character_name=source_character_name,
        total=len(logs),
        inserted=result.inserted,
        skipped=result.skipped,
        dry_run=dry_run,
        batch_created_at=result.batch_created_at,
        first_page=first_page,
        last_page=last_page,
        warnings=warnings,
    )


def format_report(report: MessageImportReport) -> str:
    mode = "dry-run(未寫入)" if report.dry_run else "已寫入"
    pages = f"p.{report.first_page}～{report.last_page}" if report.first_page is not None else "無頁碼"
    lines = [
        f"[{mode}] 線 {report.character_id}「{report.character_name}」",
        f"共 {report.total} 則:新增 {report.inserted}、略過已存在 {report.skipped};頁碼 {pages}",
    ]
    if report.batch_created_at is not None:
        lines.append(f"批號(created_at):{report.batch_created_at}")
    lines += [f"⚠ {w}" for w in report.warnings]
    return "\n".join(lines)
