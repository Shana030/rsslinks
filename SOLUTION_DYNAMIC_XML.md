# XML 動態生成方案建議

## 當前問題
每次 scraper 執行都會更新 XML 文件並 commit 到 repo，導致：
- Git 歷史記錄過多
- Repo 體積持續增長
- 無意義的 commit noise

## 解決方案比較

### 方案 A: 完全動態生成（使用 Serverless）✨ 推薦

#### 架構
```
RSS Reader → Vercel/Cloudflare Function → 即時執行 scraper → 返回 XML
```

#### 優點
- ✅ Repo 完全乾淨，零 commit
- ✅ 永遠是最新資料
- ✅ 不佔用 GitHub Actions 額度

#### 缺點
- ❌ 需要額外平台（但 Vercel/Cloudflare 免費額度足夠）
- ❌ 每次訪問都要執行 scraper（可加快取層）
- ❌ 需要重構程式碼

#### 實作成本
**中等**（約 2-3 小時）

---

### 方案 B: GitHub Release Assets（最平衡）🔥 最推薦

#### 架構
```
GitHub Actions → 執行 scraper → 上傳 XML 到 GitHub Release
RSS Reader → 訂閱 Release 中的 XML URL
```

#### 優點
- ✅ Repo 完全乾淨
- ✅ 使用 GitHub 原生功能，無需外部服務
- ✅ 歷史版本保留在 Release tags
- ✅ 可設定自動刪除舊版本

#### 缺點
- ❌ Release assets 有總量限制（但很大）
- ❌ URL 會包含版本號（可用 latest tag 固定）

#### 實作成本
**低**（約 30 分鐘）

#### 實作方式
修改 `.github/workflows/scrape.yml`：
```yaml
- name: Upload XML to Release
  uses: softprops/action-gh-release@v1
  with:
    tag_name: latest-feeds
    files: docs/*.xml
    prerelease: true
```

RSS 訂閱 URL 變為：
```
https://github.com/Shana030/rsslinks/releases/download/latest-feeds/picks.xml
```

---

### 方案 C: 只儲存增量資料（當前改良版）

#### 當前已實作
- ✅ index.html 完全靜態
- ✅ 只在有新文章時才 commit
- ✅ 每 6 小時執行（減少 4 倍）

#### 進一步優化
改為**只儲存 JSON metadata**，前端動態生成 XML：

1. Repo 只存 `feeds-data.json`:
```json
{
  "picks": [
    {"title": "...", "link": "...", "date": "2025-12-24"}
  ]
}
```

2. 用 JavaScript 動態生成 XML：
```html
<script>
  fetch('feeds-data.json')
    .then(r => r.json())
    .then(data => generateRSS(data))
</script>
```

#### 缺點
- RSS reader 無法直接訂閱（需要轉換服務）

---

## 推薦方案：方案 B（GitHub Release）

### 為什麼推薦？
1. **最少改動**：只需修改 workflow，scraper.py 不用動
2. **零成本**：完全使用 GitHub 原生功能
3. **乾淨的 repo**：所有 XML 移出 git 歷史
4. **可追溯**：Release tags 保留歷史版本

### 快速實作步驟

1. 修改 `.github/workflows/scrape.yml`，移除 commit 步驟，改為上傳到 Release

2. 移除 `docs/*.xml` 從 git 追蹤：
```bash
git rm docs/*.xml
echo "docs/*.xml" >> .gitignore
```

3. 更新 index.html 中的連結：
```html
<a href="https://github.com/Shana030/rsslinks/releases/download/latest-feeds/picks.xml">
```

4. 初次執行後，設定定期清理舊 Release（可選）

---

## 你想要哪個方案？

1. **方案 A**：完全動態（需要 Vercel/Cloudflare）
2. **方案 B**：GitHub Release（推薦，最簡單）
3. **維持現狀**：繼續優化當前方案
