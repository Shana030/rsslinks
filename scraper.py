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
            
            items = soup.select('div.item-box') 

            fg = FeedGenerator()
            fg.id(cat['url'])
            fg.title(f"未來商務 - {cat['name']}")
            fg.link(href=cat['url'], rel='alternate')
            fg.description(f"自動抓取的未來商務 {cat['name']} 頻道 (Playwright)")
            fg.language('zh-TW')

            for item in items[:15]: # 抓取前 15 則
                try:
                    title_tag = item.select_one('h3') or item.select_one('.title')
                    link_tag = item.select_one('a')
                    desc_tag = item.select_one('.desc') or item.select_one('.content')
                    
                    if not title_tag or not link_tag:
                        continue

                    title = title_tag.text.strip()
                    link = link_tag['href']
                    description = desc_tag.text.strip() if desc_tag else "無描述"
                    
                    # 確保連結完整
                    if link.startswith('/'):
                        link = "https://fc.bnext.com.tw" + link

                    fe = fg.add_entry()
                    fe.id(link)
                    fe.title(title)
                    fe.link(href=link)
                    fe.description(description)
                    fe.pubDate(datetime.datetime.now(datetime.timezone.utc))
                except Exception as e:
                    print(f"單則處理出錯: {e}")

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