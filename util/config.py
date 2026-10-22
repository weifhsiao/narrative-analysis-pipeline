"""全案設定的唯一入口:.env 只在這裡 load,各模組透過這裡的函式取值,不自己 os.getenv。

值在呼叫當下才讀環境變數(測試會 monkeypatch env);只有 SQL_ECHO / DB_PATH 在 db_util
import 時就要用,那是 engine 建立時機決定的,不是這裡。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from util.paths import DATA_DIR, REPO_DIR

# 固定讀 repo 根目錄的 .env,不隨 cwd 找;不覆蓋既有環境變數
load_dotenv(REPO_DIR / ".env")

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"


def sql_echo() -> bool:
    """SQL_ECHO=true 時印出 SQL(dev debug 用);預設關閉,demo/截圖不被 SQL log 洗版。"""
    return os.getenv("SQL_ECHO", "false").strip().lower() in ("1", "true", "yes")


def db_path() -> Path:
    """SQLite 檔路徑;DB_PATH 沒設就是 data/novel.db。相對路徑以 repo 根目錄為基準,不看 cwd。"""
    value = os.getenv("DB_PATH", "").strip()
    if not value:
        return DATA_DIR / "novel.db"
    return REPO_DIR / Path(value).expanduser()


def ai_provider() -> str:
    return os.getenv("AI_PROVIDER", "gemini")


def gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "")


def gemini_model() -> str:
    """設定要用的模型。DB 的 model 欄存的是 API 實際回報的版本,不是這個。"""
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def log_input_mode() -> str:
    """log 輸入模式:inline(純文字內嵌,預設) / attachment(夾檔)。"""
    return os.getenv("LOG_INPUT_MODE", "inline")
