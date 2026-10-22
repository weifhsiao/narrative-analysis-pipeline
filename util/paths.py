from pathlib import Path

# 一律以 repo 根目錄為基準,不看 cwd:從別的目錄執行也不會在那裡另建 data/ 與空 DB
REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
