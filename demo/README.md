# 前端 Demo（純靜態）

無後端、可公開的前端展示。資料取自 `examples/` 的虛構範例（燈塔守塔人故事）。

## 兩支頁面

| 檔案 | 定位 |
|---|---|
| `index.html` | **教學走查**：四階段 stepper（原始 log → 解析 → Pipeline 執行 → 四種輸出），說明 pipeline 怎麼運作。作品集用。 |
| `app.html` | **分析工作台**：接近真實 UI 的雛形——角色 / Run 的 list + create、Run 詳情（結果 + 來源 turn）、角色的 Context 管理。 |

兩者共用 `data.js`。`app.html` 的建立操作（新增角色 / 新建 run / 新增 context）為**純視覺 mock**，不持久化。

## 執行

```bash
cd demo && python3 -m http.server 8777
# 開 http://localhost:8777/index.html 或 /app.html
```

## 重生資料

`data.js` 由腳本從 `examples/` 產生（解析邏輯對齊 `util/parse_log_util`）：

```bash
python3 demo/build_data.py
```

## 之後接真實 API

前端目前讀 `data.js`；接後端時把讀取點換成打 API 即可。list 類（run / 角色）建議 server-side 分頁；「來源 turn」已做點開才渲染（lazy render）。
