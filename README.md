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

- 當你 **推送修改到 `categories.json` 或 `docs/index.html`** 時，會觸發自動化流程：
  - 在 runner 上執行 `python scraper.py` 並 **自動產生 / 更新 `docs/*.xml`**（抓取對應來源）。
  - 若有 `docs/*.xml` 的變更，工作流程會自動 **commit 並 push 回原分支**（因此你會在該分支看到更新好的 XML）。
  - `docs/index.html` 預期由你手動維護，工作流程會 **跳過更新 index.html**（避免覆寫你手動的內容）。

- 若你想手動觸發一次（例如在 GitHub UI），也可以使用工作流程的 **Run workflow**（workflow_dispatch）。

關於 `xml` 欄位（新）

- 建議在 `categories.json` 的每個項目加入 `xml` 欄位，明確指定輸出的 RSS 檔名（使用 ASCII，避免中文檔名）：
```json
{"name": "精選內容", "url": "https://fc.bnext.com.tw/category/picks", "xml": "picks.xml"}
```
- 如果未指定，程式會嘗試：1) 從 URL 推導適合的檔名前綴（如 URL 的最後一個路徑段），2) 否則會以 `category_N.xml` 為預設。

發生問題時的簡單手動流程

- 若自動化卡住或沒抓到條目：
  1. 在本地執行 `python scraper.py`，檢查 `docs/*.xml` 是否有條目。
  2. 若需要修 selector 或手動建立 `docs/index.html`，可直接修改並推一個分支，再建立 PR 手動合併。

- 連線超時行為：
  - 若 category 頁面或文章頁在 **60 秒** 內沒有回應，腳本會**跳過該 URL 並繼續下一個**；這樣可以確保整個 run 不會被單一慢速源阻塞，並在下一次排程再重試。

關於 `link_selector`

- 若某個來源無法自動抓到正確連結，可在 `categories.json` 的該項目加 `link_selector`（CSS selector），以提高抓取精準度。

簡潔結語

- 我已把 workflow 設計成「自動檢測 & 建 PR，若沒變更就跳過」，以便你仍保有人工審核的控制權；若你要我把這份 README 再精簡或加入其它指令（例如快速建立 index.html 的 script），告訴我我就改。