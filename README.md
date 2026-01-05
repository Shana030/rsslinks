# rsslinks — RSS 訂閱源生成器

這個專案會定期抓取 `categories.json` 中列出的來源，產生 RSS XML 檔案並透過 GitHub Pages 提供訂閱。

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
所有 RSS feed 都透過 GitHub Pages 提供，訂閱連結格式：
```
https://shana030.github.io/rsslinks/[檔案名稱].xml
```

例如：
- 未來商務｜精選內容：`https://shana030.github.io/rsslinks/picks.xml`
- 數位時代｜AI與大數據：`https://shana030.github.io/rsslinks/bnext_ai.xml`

完整訂閱連結列表請參考：https://shana030.github.io/rsslinks/

## 自動化行為

### 每 6 小時自動抓取
- GitHub Actions 排程：`0 */6 * * *`（每 6 小時執行一次）
- 自動執行 `python scraper.py`，抓取**今日發佈**的新文章
- 只加入尚未存在的條目，已存在的文章會自動跳過
- 生成的 XML 檔案**自動 commit 到 repo**（使用 `[skip ci]` 避免觸發循環）
- 透過 GitHub Pages 自動部署並提供訂閱

### 手動觸發
在 GitHub Actions 頁面使用 **Run workflow** 手動執行

### index.html 自動維護
- `docs/index.html` 根據 `categories.json` 自動生成
- 包含每個 feed 的名稱、來源連結和 Release 訂閱連結
- 完全靜態，只在 `categories.json` 變更時才更新

## 如何新增 RSS 資源

### 步驟 1：更新 categories.json
在 [categories.json](categories.json) 中新增一個項目：
```json
{
  "name": "顯示名稱（支援中文）",
  "url": "要抓取的網頁 URL",
  "xml": "檔案名稱.xml"  // 建議使用英文或拼音，避免中文
}
```

範例：
```json
{
  "name": "TechNews 科技新報｜尖端科技",
  "url": "https://technews.tw/category/cutting-edge/",
  "xml": "technews_cutting-edge.xml"
}
```

### 步驟 2：本地測試（選擇性）
```bash
# 啟動虛擬環境
source .venv/bin/activate

# 執行 scraper 測試新資源
python scraper.py
```

### 步驟 3：提交變更
```bash
git add categories.json
git commit -m "新增 RSS 資源: [資源名稱]"
git push
```

### 自動化流程
一旦 `categories.json` 被推送到 GitHub：

1. **自動觸發 workflow**：[regenerate-on-categories-change.yml](.github/workflows/regenerate-on-categories-change.yml) 會自動執行
2. **生成 XML 檔案**：scraper.py 會為新資源生成對應的 XML 檔案
3. **更新 index.html**：自動在首頁新增該 RSS 的訂閱連結
4. **部署到 GitHub Pages**：新的 RSS feed 立即可用

完成後，新的 RSS 訂閱連結會是：
```
https://shana030.github.io/rsslinks/[你設定的xml檔名]
```

### 注意事項
- ✅ **只需要修改 `categories.json`**，其他檔案會自動生成
- ✅ `xml` 檔名建議使用英文、數字、底線和連字號
- ✅ `name` 可以使用任何語言（中文、英文等）
- ⚠️ 新資源的初次抓取會擷取當日文章，後續每 6 小時自動更新

## categories.json 格式參考

每個項目需要包含三個欄位：
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

## 內容過濾規則

scraper 會自動排除以下類型的頁面，避免抓到非文章內容：
- 分類頁、標籤頁（`/category/`, `/tag/`）
- 作者頁（`/author/`）
- 系統頁面（登入、註冊、購物車等）
- 靜態資源（圖片、CSS、JS 檔案）
- **AI 解方雜貨店和工具清單**（`/solutions/`, `/list?`）

如果需要排除特定路徑，可在 [scraper.py:299-310](scraper.py#L299-L310) 的 `excluded_patterns` 清單中新增規則。


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
確認 GitHub Pages 中的 XML 檔案：
1. 前往 https://shana030.github.io/rsslinks/
2. 檢查是否有所有的 RSS 訂閱連結
3. 若缺少檔案，手動觸發 workflow

## 架構說明

### 為什麼使用 GitHub Pages？
- ✅ **零成本**：完全使用 GitHub 原生功能，無需外部服務
- ✅ **穩定的 URL**：固定的 GitHub Pages URL
- ✅ **自動更新**：每次 commit 後自動部署
- ✅ **正確的 Content-Type**：GitHub Pages 提供正確的 XML 標頭，RSS 閱讀器可正常訂閱
- ⚠️ **會產生 commit**：每次更新會產生一個 commit，但使用 `[skip ci]` 避免觸發循環

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