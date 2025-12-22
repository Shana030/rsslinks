import requests # 雖然主體用 Playwright，但 requests 在其他地方可能仍有用，故保留
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import datetime
import os
from playwright.sync_api import sync_playwright

# 讀取 categories.json（若不存在則回退到內建清單）
import json
import re

def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", s)
    s = s.strip("_")
    # 也可將中文轉為拼音，但簡單做法為保留並用 ascii-safe filename
    return s

DEFAULT_CATEGORIES = [
    {"name": "精選內容", "url": "https://fc.bnext.com.tw/category/picks"},
    {"name": "實戰建議", "url": "https://fc.bnext.com.tw/category/tips"},
    {"name": "趨勢解析", "url": "https://fc.bnext.com.tw/category/trends"},
    {"name": "深度故事", "url": "https://fc.bnext.com.tw/category/stories"},
    {"name": "BNET Articles", "url": "https://www.bnext.com.tw/articles"},
    {"name": "BNET AI", "url": "https://www.bnext.com.tw/categories/ai"},
]

def default_filename_from_url(url):
    """Try to get a sensible ASCII filename from the URL's last path segment."""
    try:
        parts = url.rstrip('/').split('/')
        last = parts[-1]
        # keep only safe chars
        safe = re.sub(r'[^0-9A-Za-z_-]+', '_', last).strip('_')
        if safe:
            return safe
    except Exception:
        pass
    return ''


def make_ascii_filename(base: str, fallback_index: int = 0) -> str:
    # base -> slugify then strip non-ascii
    s = slugify(base)
    s = re.sub(r'[^0-9a-zA-Z_-]+', '_', s)
    s = s.strip('_')
    if not s:
        s = f"category_{fallback_index}"
    return s


def load_categories(path='categories.json'):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            # 確保每項都有 name/url 和預設 file
            for idx, item in enumerate(data):
                if 'name' not in item or 'url' not in item:
                    raise ValueError('每個 category 必須包含 name 與 url')
                # support explicit xml filename via 'xml' field (preferred),
                # fallback to legacy 'file' for backward compatibility
                filename = None
                if item.get('xml'):
                    filename = item.get('xml')
                elif item.get('file'):
                    filename = item.get('file')

                if filename:
                    # ensure .xml
                    if not filename.lower().endswith('.xml'):
                        filename = filename + '.xml'
                    # sanitize to ASCII-safe filename (warn if sanitized)
                    safe = re.sub(r'[^0-9A-Za-z._-]+', '_', filename)
                    if safe != filename:
                        print(f"Warning: filename '{filename}' contained unsafe characters; sanitized to '{safe}'")
                    item['file'] = safe
                else:
                    # derive from URL path last segment if possible
                    derived = default_filename_from_url(item['url'])
                    if derived:
                        item['file'] = f"{derived}.xml"
                    else:
                        item['file'] = f"{make_ascii_filename(item['name'], idx)}.xml"
            print(f"Loaded categories from {path}: {[c['name'] for c in data]}")
            return data
        except Exception as e:
            print(f"讀取 {path} 失敗，使用內建清單: {e}")
    # fallback
    for idx, item in enumerate(DEFAULT_CATEGORIES):
        if 'file' not in item:
            item['file'] = f"{make_ascii_filename(item['name'], idx)}.xml"
    print("使用預設 categories")
    return DEFAULT_CATEGORIES

# 使用 load_categories() 取得 CATEGORIES
CATEGORIES = load_categories()



from urllib.parse import urljoin


def fetch_category_with_playwright(cat):
    print(f"正在使用 Playwright 抓取: {cat['name']}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # 在 Actions 中通常為 True
        page = browser.new_page()

        try:
            # 如果目標 URL 在 60 秒內沒有回應，就跳過該 URL（等待下一次排程）
            timeout_ms = 60_000
            try:
                page.goto(cat['url'], wait_until='networkidle', timeout=timeout_ms)
            except Exception as e:
                print(f"導覽 {cat['url']} 失敗或超時 ({timeout_ms}ms)，已跳過此 category: {e}")
                return  # 跳過本 category，繼續下一個

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

                    # 抓取文章頁面的 meta description 與 image（若在 60s 內沒有回應則跳過該文章）
                    desc = ''
                    image = None
                    article_html = None
                    art_timeout_ms = 60_000
                    art_page = None
                    try:
                        art_page = browser.new_page()
                        art_page.goto(href, wait_until='domcontentloaded', timeout=art_timeout_ms)
                        article_html = art_page.content()
                    except Exception as e:
                        print(f"導覽文章 {href} 失敗或超時 ({art_timeout_ms}ms)，跳過此文章: {e}")
                    finally:
                        if art_page:
                            try:
                                art_page.close()
                            except Exception:
                                pass

                    if article_html:
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
    skip_index = os.environ.get('SKIP_INDEX', 'false').lower() in ('1','true','yes')
    for cat in CATEGORIES:
        fetch_category_with_playwright(cat)
    if not skip_index:
        write_index(out_dir)
    else:
        print("SKIP_INDEX is set; skipping generation of docs/index.html")