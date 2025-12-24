# rsslinks — RSS 訂閱源生成器

這個專案會定期抓取 `categories.json` 中列出的來源，產生 RSS XML 檔案並上傳到 GitHub Release，保持 repo 乾淨無 commit noise。

## 快速開始

### 本地測試
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium  # 第一次或需要時
python scraper.py                      # 生成 docs/*.xml
```

### RSS 訂閱連結格式
所有 RSS feed 都透過 GitHub Release 提供，訂閱連結格式：
```
https://github.com/Shana030/rsslinks/releases/download/latest-feeds/[檔案名稱].xml
```

例如：
- 未來商務｜精選內容：`https://github.com/Shana030/rsslinks/releases/download/latest-feeds/picks.xml`
- 數位時代｜AI與大數據：`https://github.com/Shana030/rsslinks/releases/download/latest-feeds/bnext_ai.xml`

完整訂閱連結列表請參考：https://shana030.github.io/rsslinks/

## 自動化行為

### 每 6 小時自動抓取
- GitHub Actions 排程：`0 */6 * * *`（每 6 小時執行一次）
- 自動執行 `python scraper.py`，抓取**今日發佈**的新文章
- 只加入尚未存在的條目，已存在的文章會自動跳過
- 生成的 XML 檔案**自動上傳到 GitHub Release**（tag: `latest-feeds`）
- **不會 commit XML 到 repo**，保持 git 歷史乾淨
- 只有當 `categories.json` 變更時才會 commit `index.html`

### 手動觸發
在 GitHub Actions 頁面使用 **Run workflow** 手動執行

### index.html 自動維護
- `docs/index.html` 根據 `categories.json` 自動生成
- 包含每個 feed 的名稱、來源連結和 Release 訂閱連結
- 完全靜態，只在 `categories.json` 變更時才更新

## categories.json 格式

每個項目需要包含 `xml` 欄位（使用 ASCII 檔名，避免中文）：
```json
{
  "name": "未來商務｜精選內容",
  "url": "https://fc.bnext.com.tw/category/picks",
  "xml": "picks.xml"
}
```

## 更新模式

### 每日更新模式（預設）
- 腳本讀取既有的 XML 檔案（從 Release 下載或本地），只加入**今日發佈且尚未出現**的條目
- 以 `link` 或 `guid` 辨識重複文章
- 非今日發佈的文章會自動跳過
- 沒有新文章時跳過該來源，不產生空的更新

### 初始化模式（手動執行）
一次性抓取前 N 篇文章（不限今日）：
```bash
INITIAL_FETCH=true MAX_ITEMS=20 python scraper.py
```

## 文章資訊擷取

每篇文章會嘗試擷取：
- **標題**：優先使用 og:title，回退到 `<title>` 標籤
- **描述**：優先使用 meta description（若與標題相同則視為無描述）
- **圖片**：優先使用 og:image，回退到文章首張圖片
- **發佈時間**：解析 JSON-LD、meta 標籤或 `<time>` 標籤，無法解析則使用當前時間


## 故障排除

### 自動化問題
若 GitHub Actions 執行失敗或沒抓到文章：
1. 檢查 Actions 日誌確認錯誤訊息
2. 本地執行 `python scraper.py` 測試
3. 手動觸發 workflow 重試

### 連線超時
- 若頁面在 **60 秒**內沒有回應，腳本會跳過該 URL 並繼續下一個
- 確保整個執行不會被單一慢速源阻塞
- 下次排程會自動重試

### 檢查 RSS 訂閱連結
確認 Release 中的 XML 檔案：
1. 前往 https://github.com/Shana030/rsslinks/releases/tag/latest-feeds
2. 檢查是否有所有的 XML 檔案
3. 若缺少檔案，手動觸發 workflow

## 架構說明

### 為什麼使用 GitHub Release？
- ✅ **乾淨的 repo**：XML 不再產生 commit，git 歷史乾淨
- ✅ **零成本**：完全使用 GitHub 原生功能，無需外部服務
- ✅ **穩定的 URL**：`latest-feeds` tag 確保訂閱連結永久有效
- ✅ **自動更新**：每次 workflow 執行會覆蓋 Release 中的檔案

### 檔案結構
```
.
├── categories.json          # RSS 來源設定（唯一需要手動維護的檔案）
├── scraper.py              # 主要爬蟲程式
├── docs/
│   └── index.html          # GitHub Pages 首頁（自動生成）
└── .github/workflows/
    └── scrape.yml          # 每 6 小時執行的自動化工作流程
```