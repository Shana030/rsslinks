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

from urllib.parse import urljoin


def fetch_category_with_playwright(cat):
    print(f"正在使用 Playwright 抓取: {cat['name']}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # 在 Actions 中通常為 True
        page = browser.new_page()

        try:
            # 更寬鬆的 timeout 與重試機制
            attempts = 3
            success = False
            for i in range(attempts):
                try:
                    page.goto(cat['url'], wait_until='networkidle', timeout=120000)
                    success = True
                    break
                except Exception as e:
                    print(f"第 {i+1} 次嘗試導覽 {cat['url']} 失敗: {e}")
            if not success:
                raise Exception(f"連續 {attempts} 次導覽失敗")

            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')

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

                    # 將相對路徑轉成絕對路徑（以 category url 為 base）
                    href = urljoin(cat['url'], href)

                    if href in seen:
                        continue
                    seen.add(href)

                    # 抓取文章頁面的 meta description 與 image（重試機制與較長 timeout）
                    desc = ''
                    image = None
                    art_attempts = 2
                    art_success = False
                    article_html = None
                    for j in range(art_attempts):
                        art_page = browser.new_page()
                        try:
                            art_page.goto(href, wait_until='domcontentloaded', timeout=120000)
                            article_html = art_page.content()
                            art_success = True
                            break
                        except Exception as e:
                            print(f"第 {j+1} 次嘗試導覽文章 {href} 失敗: {e}")
                        finally:
                            art_page.close()

                    if art_success and article_html:
                        art_soup = BeautifulSoup(article_html, 'html.parser')
                        # meta description
                        meta = art_soup.find('meta', attrs={'name': 'description'})
                        if not meta:
                            meta = art_soup.find('meta', attrs={'property': 'og:description'})
                        if meta and meta.get('content'):
                            meta_desc = meta.get('content').strip()
                            # 若 meta 描述與標題不同，才放入 description
                            if meta_desc and meta_desc != title:
                                desc = meta_desc

                        # meta image
                        meta_img = art_soup.find('meta', attrs={'property': 'og:image'})
                        if not meta_img:
                            meta_img = art_soup.find('meta', attrs={'name': 'twitter:image'})
                        if meta_img and meta_img.get('content'):
                            image = urljoin(href, meta_img.get('content').strip())
                        else:
                            # fallback: 文章內第一張 img
                            img_tag = art_soup.select_one('article img, .article img, .post img, img')
                            if img_tag and img_tag.get('src'):
                                image = urljoin(href, img_tag.get('src').strip())

                    # 建立 feed entry
                    fe = fg.add_entry()
                    fe.id(href)
                    fe.title(title)
                    fe.link(href=href)
                    if desc:
                        fe.description(desc)
                    else:
                        fe.description('')
                    # 加上圖片為 enclosure（若有）
                    if image:
                        try:
                            fe.enclosure(image, 0, 'image/*')
                        except Exception:
                            # 若 enclosure 失敗，將圖片放入 description（簡單 fallback）
                            if desc:
                                fe.description(f"<img src=\"{image}\" />\n" + desc)
                            else:
                                fe.description(f"<img src=\"{image}\" />")

                    fe.pubDate(datetime.datetime.now(datetime.timezone.utc))
                    added += 1
                    print(f"加入條目: title='{title[:40]}', href={href}, desc={'有' if desc else '無'}, image={'有' if image else '無'})")
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

def write_index(output_dir='docs'):
    files = []
    for fname in sorted(os.listdir(output_dir)):
        if fname.endswith('.xml'):
            path = os.path.join(output_dir, fname)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                count = content.count('<item>')
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
                files.append({'name': fname, 'count': count, 'mtime': mtime})
            except Exception as e:
                print(f"讀取 {path} 時出錯: {e}")

    # 寫入 index.html
    index_path = os.path.join(output_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as fh:
        fh.write("<!doctype html>\n<html lang=\"zh-TW\">\n<head>\n  <meta charset=\"utf-8\" />\n  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />\n  <title>rsslinks</title>\n</head>\n<body>\n  <h1>rsslinks</h1>\n  <p>自動產生的 RSS 檔案</p>\n  <ul>\n")
        for f in files:
            fh.write(f"    <li><a href=\"./{f['name']}\">{f['name']}</a> - {f['count']} items - updated {f['mtime'].astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}</li>\n")
        fh.write("  </ul>\n  <p>Updated: " + datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z') + "</p>\n</body>\n</html>")
    print(f"已更新 index: {index_path}")


if __name__ == "__main__":
    out_dir = os.environ.get('OUTPUT_DIR', 'docs')
    for cat in CATEGORIES:
        fetch_category_with_playwright(cat)
    write_index(out_dir)