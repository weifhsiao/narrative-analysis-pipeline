# Context 檔案遷移工具（`scripts/migrate_context.py`）

把某個角色 `data/{character_id}/` 底下的文字檔，一次性匯入 `character_context` 資料表。
遷移後 **DB 成為唯一真相來源**，pipeline 不再讀檔；`.txt` 檔降級為備份。

## 前置條件

1. `character_context` 表已建立（`Base.metadata.create_all(engine)`）。
2. 目標角色已存在於 `character` 表（`character_id` 對得上）。
3. 從專案根目錄執行，並帶上 `PYTHONPATH`（否則找不到 `util` 模組）。

## 預期的檔案結構

```
data/{character_id}/
├── relationship.txt        # 關係狀態（單檔）
├── timeline.txt            # 時間軸（單檔）
├── scenarios/
│   ├── scenario1.txt       # 或 scenario_1.txt，兩種命名都可
│   ├── scenario2.txt
│   └── ...                 # 檔名數字決定順序（scenario_10 會正確排在 9 之後）
└── bk/                     # 備份資料夾，會被忽略
```

## 匯入對應規則

| 來源 | `context_type` | `sort_order` | `title` | `is_active` |
|------|---------------|-------------|---------|-------------|
| `relationship.txt` | `relationship` | 0 | 關係狀態總結 | True |
| `timeline.txt` | `timeline` | 0 | 時間軸 | True |
| `scenarios/scenario*.txt` | `scenario` | 1..n（依檔名數字自然排序） | 發生過的劇情 I、II…（羅馬數字） | True |

- 內容會 `strip()` 去頭尾空白；空檔會被略過。
- `bk/` 底下的備份不會被匯入。

## 用法

```bash
# 1) dry-run：只預覽會匯入什麼，不寫入
PYTHONPATH=. python scripts/migrate_context.py <character_id>

# 2) 確認無誤後實際寫入
PYTHONPATH=. python scripts/migrate_context.py <character_id> --write
```

## 安全機制

- **預設 dry-run**：不加 `--write` 一律只預覽，不動資料庫。
- **重複保護**：若該角色在 `character_context` 已有資料，預設**中止**，避免重複匯入。
- `--force`：略過上述保護、硬性再塞。⚠️ 這只是「明知有資料仍寫入」的逃生門，會**疊加造成重複**，不是乾淨的重新匯入機制；要重來請先清掉舊資料（或將舊版 `is_active` 設為 False）。

## 注意事項

- 這是**一次性、單向**的匯入橋，不是持續同步。遷移後編輯 context 請走 API／UI（DB），而不是改 `.txt` 檔——改檔不會影響之後的 run。
- `data/` 內容不進版控（`.gitignore`），本工具本身可公開。
