# rsslinks — 簡潔說明

這個專案會定期抓取 `categories.json` 裡列的來源，產生 RSS XML 檔放在 `docs/`（供 GitHub Pages 發佈）。

核心指引（簡化版）

- 本地測試：
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  python -m playwright install chromium  # 第一次或需要時
  python scraper.py                      # 生成 docs/*.xml 與 docs/index.html
  ```
- 若結果正確，手動提交並推上遠端：
  ```bash
  git add docs/*.xml docs/index.html
  git commit -m "Update generated RSS feeds"
  git push origin main
  ```

自動化行為（簡述）

- **每小時自動抓取**（GitHub Actions 排程 `0 * * * *`）：
  - 自動執行 `python scraper.py`，抓取**今日發佈**的新文章。
  - 只加入尚未存在的條目，已存在的文章會自動跳過。
  - 自動更新 `docs/*.xml` 和 `docs/index.html`。
  - 若有變更，自動 commit 並 push 回 main 分支。

- 當你 **推送修改到 `categories.json`** 時，會觸發自動重新生成：
  - 在 runner 上執行 `python scraper.py` 並 **自動產生 / 更新 `docs/*.xml`**（抓取對應來源）。
  - 自動更新 `docs/index.html`（根據 categories.json 的內容生成）。
  - 若有 `docs/*.xml` 的變更，工作流程會自動 **commit 並 push 回原分支**。

- 若你想手動觸發一次（例如在 GitHub UI），也可以使用工作流程的 **Run workflow**（workflow_dispatch）。

- **index.html 自動維護**：
  - `docs/index.html` 現在會根據 `categories.json` **自動生成**，包含每個 feed 的名稱、描述、文章數量和來源連結。
  - 你只需要維護 `categories.json` 一個檔案即可。

關於 `xml` 欄位（新）

- 建議在 `categories.json` 的每個項目加入 `xml` 欄位，明確指定輸出的 RSS 檔名（使用 ASCII，避免中文檔名）：
```json
{"name": "精選內容", "url": "https://fc.bnext.com.tw/category/picks", "xml": "picks.xml"}
```
- 若某個來源有抓取問題，請回報以修正程式或擷取邏輯（目前不支援手動設定 CSS selector，亦無手動限制每次新增數量的欄位）。

增量更新與欄位行為（重要）

- **每日更新模式**（預設）：
  - 腳本會讀取既有 `docs/<xml>`，只**加入今日發佈且尚未出現的條目**（以 `link` 或 `guid` 辨識）。
  - 已存在的文章會自動跳過，非今日發佈的文章也會跳過。
  - 這樣可以確保每小時的自動抓取只會新增今日的新文章，不會重複抓取舊文章。

- **初始化模式**（手動執行）：
  - 如果需要一次性抓取前 N 篇文章（例如初始化），可以設定環境變數：
    ```bash
    INITIAL_FETCH=true MAX_ITEMS=100 python scraper.py
    ```
  - 此模式會抓取所有文章（不限今日），直到達到 MAX_ITEMS 數量或列表頁沒有更多文章。

- 每則新文章會嘗試擷取：標題、描述（優先使用 meta description；若與標題相同則當作無描述）、預設圖片（og:image 或首張 img）以及發佈時間（嘗試解析常見 meta 與 time 標籤）。若無發佈時間則以執行時間代替。
- 若該來源沒有新文章，腳本會跳過寫檔，避免無意義的 commit。


發生問題時的簡單手動流程

- 若自動化卡住或沒抓到條目：
  1. 在本地執行 `python scraper.py`，檢查 `docs/*.xml` 是否有條目。
  2. 若需要修擷取規則或手動建立 `docs/index.html`，可直接修改並推一個分支，再建立 PR 手動合併。

- 連線超時行為：
  - 若 category 頁面或文章頁在 **60 秒** 內沒有回應，腳本會**跳過該 URL 並繼續下一個**；這樣可以確保整個 run 不會被單一慢速源阻塞，並在下一次排程再重試。


簡潔結語

- 我已把 workflow 設計成「自動檢測 & 建 PR，若沒變更就跳過」，以便你仍保有人工審核的控制權；若你要我把這份 README 再精簡或加入其它指令（例如快速建立 index.html 的 script），告訴我我就改。