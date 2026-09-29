from util.paths import REPO_DIR

# 測試會把它換成 tmp_path
BASE_DIR = REPO_DIR


def write_response(content: str, timestamp: str, name: str = "response"):
    path = BASE_DIR / "data" / "api_response" / f"{timestamp}" / f"{name}.txt"
    # 路徑不存在就新建
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
