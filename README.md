# rsslinks (版本 1) ✅

簡短說明
- 這個專案會定期（排程）抓取指定的分類 / 網址，產生 RSS XML 檔案並存放在 `docs/`，供 GitHub Pages 發佈使用。
- 目前：**自動排程每小時執行一次，但不會自動 commit/push**（由你自己檢查與推上 repo，以保持你對內容變更的控制）。

---

## 快速開始 🏁
1. 取得原始碼並建立虛擬環境（示意）：
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   # 只在第一次或有需要時：
   python -m playwright install chromium
   ```
2. 本地執行（會在 `docs/` 生成 XML 與更新 `docs/index.html`）：
   ```bash
   python scraper.py
   ```
3. 檢查生成結果：
   - `docs/` 下會看到像 `picks.xml`, `bnext_ai.xml` 等檔案
   - `docs/index.html` 會列出所有 XML 與條目數
4. 若滿意，手動提交並推上 GitHub：
   ```bash
   git add docs/*.xml docs/index.html
   git commit -m "Update generated RSS feeds"
   git push origin main
   ```

---

## 更新抓取來源（categories.json）🧾
- 檔案：`categories.json`（請使用 UTF-8 編輯）。
- 每一個項目至少要有 `name` 與 `url`，可選的欄位：`file`（自訂輸出檔名）、`link_selector`（自訂 CSS 選擇器，見下）。
- 範例：
```json
{
  "name": "Vocus AIUX",
  "url": "https://vocus.cc/salon/alan623/room/aiux",
  "file": "vocus_aiux.xml",
  "link_selector": "a.your-post-link-class"  
}
```
- 操作步驟：
  1. 編輯 `categories.json` 新增或修改項目。
  2. 在本地執行 `python scraper.py`（確認產生 `docs/<file>` 與 `docs/index.html`）。
  3. 手動 `git add` / `git commit` / `git push` 上遠端，Pages 即會在推送後建置與部署。

### 關於 `link_selector`
- 預設 scraper 會嘗試抓取含 `/articles/view/` 或 `/article/` 的連結。若目標網站使用其它結構（例如 Vocus），可以在 `categories.json` 的該項目中加 `link_selector`，放入一個 CSS 選擇器來標定文章連結（例如 `a.post-link` 或 `a[href*="/p/"]`）。
- 使用方法：打開該網站 → Developer Tools → 找到列出文章連結的標籤，右鍵 Copy → Copy selector，或用自訂的簡短 selector。

---

## 自動排程但不自動 push 是什麼意思？⏱️❌
- 系統已在 GitHub Actions 中設定每小時執行一次 workflow。該工作流程會：
  - 在 runner 上執行 `python scraper.py`，嘗試抓取來源並在 runner 的檔案系統中產生 `docs/*.xml`（和 `index.html`）。
  - 在 Actions log 中會顯示每個 feed 的項目數（方便你快速判斷是否抓到內容）。
- **但**工作流程設為“不自動 commit/push” → 也就是說：
  - 即使 workflow 在跑，也不會把產生的 `docs/*.xml` 自動提交回你的 repo（這樣可以避免未經你確認就改變 repo 的狀態）。
  - 若你要把最新的 XML 發佈到 Pages，請在本地或你的流程中手動推上 `main`（或你指定的 branch / docs 資料夾）。

---

## 新增 URL（以 `https://vocus.cc/salon/alan623/room/aiux` 為例）📝
1. 先把來源加入 `categories.json`：
   - 建議同時設定 `file`（例如 `vocus_aiux.xml`）與 `link_selector`，以便更準確抓取。例：
```json
{
  "name": "Vocus AIUX",
  "url": "https://vocus.cc/salon/alan623/room/aiux",
  "file": "vocus_aiux.xml",
  "link_selector": "a[href*='/p/']"
}
```
2. 在本地執行 `python scraper.py`，確認 `docs/vocus_aiux.xml` 是否有條目：「title」「link」是否正確，有無 description 或 image（若 meta 描述與標題不同，會放入 description；如果有 og:image 或第一張 img，會放 image）。
3. 若沒有抓到條目，打開目標網頁、用 Developer Tools 找到正確的 `link_selector`，更新 `categories.json`，再跑一次。
4. 確認沒問題後手動提交並推送。

---

## 注意事項 & 偵錯建議 🛠️
- 若某些頁面載入慢或偶發失敗：
  - 已加入重試機制與延長 timeout（預設每次導覽 timeout 120s、重試 3 次）。
  - 仍建議在本地先測試，或在 workflow log 中查看失敗訊息（Actions → workflow run → 查看步驟輸出）。
- 條目數限制：目前每個分類最大抓取 15 筆（可修改 `scraper.py` 中的限制）。
- description 與 image：腳本會嘗試抓取 meta description（或 og:description）及 og:image；若 meta description 與 title 相同，會留空 description（依你需求可以改成總是填充）。
- 尊重網站的 robots / 使用條款：爬取行為請注意合理頻率，避免對目標站造成負擔。

---

## 版本紀錄
- v1.0 — 初版：
  - 支援從 `categories.json` 載入來源
  - 支援 meta description 與 image 抓取（若與 title 不同）
  - 重試機制與較長 timeout
  - 每小時排程執行，但不自動 push（保留手動 commit/push）

---

如需我也可以：
- 幫你把 `link_selector` 的自訂支援直接寫入 `categories.json` 結構並讓 `scraper.py` 使用（目前 README 已示範，但 scraper 也已兼容簡單情況）；
- 寫一個小指令（`./scripts/add_category.sh`）或 GitHub Actions 的 manual dispatch 來自動新增 category 並測試；

有需要我再幫你把 README 裡面示範的 `link_selector` 直接作用於 scraper（若需要，我會修改 `scraper.py` 讀取該欄）並示範一次完整流程。