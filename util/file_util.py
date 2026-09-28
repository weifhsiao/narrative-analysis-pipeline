from pathlib import Path

# 往上兩層到專案根目錄
BASE_DIR = Path(__file__).parent.parent


def write_debug_file(content: str, timestamp: str, name: str = "prompt_log") -> Path:
    path = BASE_DIR / "data" / "debug_log" / f"{timestamp}" / f"{name}.log"
    # 路徑不存在就新建
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(mode="a", encoding="utf-8") as f:
        f.write(content)

    return path


def write_response(content: str, timestamp: str, name: str = "response"):
    path = BASE_DIR / "data" / "api_response" / f"{timestamp}" / f"{name}.txt"
    # 路徑不存在就新建
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
