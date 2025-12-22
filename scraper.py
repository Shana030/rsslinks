import requests # 雖然主體用 Playwright，但 requests 在其他地方可能仍有用，故保留
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import datetime
import os
from playwright.sync_api import sync_playwright

# 定義目標分類與輸出的檔名
CATEGORIES = [
    {"name": "精選內容", "url": "https://fc.bnext.com.tw/category/picks", "file": "picks.xml"},
    {"name": "實戰建議", "url": "https://fc.bnext.com.tw/category/tips", "file": "tips.xml"},
    {"name": "趨勢解析", "url": "https://fc.bnext.com.tw/category/trends", "file": "trends.xml"},
    {"name": "深度故事", "url": "https://fc.bnext.com.tw/category/stories", "file": "stories.xml"},
    {"name": "BNET Articles", "url": "https://www.bnext.com.tw/articles", "file": "bnext_articles.xml"},
    {"name": "BNET AI", "url": "https://www.bnext.com.tw/categories/ai", "file": "bnext_ai.xml"},
]

def fetch_category_with_playwright(cat):
    print(f"正在使用 Playwright 抓取: {cat['name']}...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # 在 Actions 中通常為 True
        page = browser.new_page()
        
        try:
            page.goto(cat['url'], wait_until='networkidle', timeout=60000) # 等待網路靜止，確保內容載入
            # 您可以根據頁面實際載入情況調整等待策略
            # 例如: page.wait_for_selector('div.item-box', timeout=30000)
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # --- 以下部分與之前類似，但現在是從 Playwright 取得的 HTML 中解析 ---
            
            # 找出文章連結（支援不同 bnext 網域：/articles/view/ 或 /article/），選用有標題文字的連結並去重
            anchors = soup.select('a[href*="/articles/view/"], a[href*="/article/"]')

            fg = FeedGenerator()
            fg.id(cat['url'])
            fg.title(f"未來商務 - {cat['name']}")
            fg.link(href=cat['url'], rel='alternate')
            fg.description(f"自動抓取的未來商務 {cat['name']} 頻道 (Playwright)")
            fg.language('zh-TW')

            seen = set()
            added = 0
            # 遍歷 anchors，選用有標題文字的連結
            for a in anchors:
                if added >= 15:
                    break
                try:
                    href = a.get('href')
                    title = a.get_text(strip=True)
                    if not href or not title:
                        continue
                    # 補全相對路徑
                    if href.startswith('/'):
                        href = "https://fc.bnext.com.tw" + href
                    if href in seen:
                        continue
                    seen.add(href)

                    fe = fg.add_entry()
                    fe.id(href)
                    fe.title(title)
                    fe.link(href=href)
                    fe.description("無描述")
                    fe.pubDate(datetime.datetime.now(datetime.timezone.utc))
                    added += 1
                except Exception as e:
                    print(f"單則處理出錯: {e}")
            print(f"Found {len(anchors)} article anchors, added {added} entries.")

            # 確保輸出到 docs/ 以便 GitHub Pages 發佈（或改成別的資料夾視 Pages 設定）
            output_dir = os.environ.get('OUTPUT_DIR', 'docs')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, cat['file'])
            fg.rss_file(output_path)
            print(f"已生成: {output_path}")
            
        except Exception as e:
            print(f"抓取 {cat['url']} 失敗: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    for cat in CATEGORIES:
        fetch_category_with_playwright(cat)