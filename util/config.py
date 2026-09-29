"""全案設定的唯一入口:.env 只在這裡 load,各模組透過這裡的函式取值,不自己 os.getenv。

值在呼叫當下才讀環境變數(測試會 monkeypatch env);只有 SQL_ECHO 在 db_util import 時
就要用,那是 engine 建立時機決定的,不是這裡。
"""
import os

from dotenv import load_dotenv

load_dotenv()  # 不覆蓋既有環境變數

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"


def sql_echo() -> bool:
    """SQL_ECHO=true 時印出 SQL(dev debug 用);預設關閉,demo/截圖不被 SQL log 洗版。"""
    return os.getenv("SQL_ECHO", "false").strip().lower() in ("1", "true", "yes")


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
