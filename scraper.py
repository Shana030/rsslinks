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


def _parse_pubdate_from_soup(art_soup):
    # 嘗試從常見 meta 或 time 標籤解析發佈時間
    # 優先順序: article:published_time / og:published_time / article:published / meta[name=date] / <time datetime>
    from dateutil import parser as date_parser
    candidates = [
        ('meta', {'property': 'article:published_time'}),
        ('meta', {'property': 'og:published_time'}),
        ('meta', {'property': 'article:published'}),
        ('meta', {'name': 'date'}),
        ('meta', {'name': 'pubdate'}),
        ('meta', {'itemprop': 'datePublished'}),
        ('meta', {'property': 'article:published'}),
    ]
    for tag, attr in candidates:
        el = art_soup.find(tag, attrs=attr)
        if el and el.get('content'):
            try:
                dt = date_parser.parse(el.get('content'))
                return dt
            except Exception:
                pass
    # time 標籤
    t = art_soup.find('time')
    if t:
        if t.get('datetime'):
            try:
                from dateutil import parser as date_parser
                return date_parser.parse(t.get('datetime'))
            except Exception:
                pass
        text = t.get_text(strip=True)
        try:
            return date_parser.parse(text)
        except Exception:
            pass
    return None


def _load_existing_feed_items(path):
    import xml.etree.ElementTree as ET
    items = []
    if not os.path.exists(path):
        return items
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        # RSS 項目可能在 channel/item
        for item in root.findall('.//item'):
            link_el = item.find('link')
            guid_el = item.find('guid')
            title_el = item.find('title')
            desc_el = item.find('description')
            pub_el = item.find('pubDate')
            enclosure_el = item.find('enclosure')
            link = (link_el.text.strip() if link_el is not None and link_el.text else None)
            guid = (guid_el.text.strip() if guid_el is not None and guid_el.text else None)
            title = (title_el.text if title_el is not None and title_el.text else '')
            desc = (desc_el.text if desc_el is not None and desc_el.text else '')
            pub = None
            if pub_el is not None and pub_el.text:
                try:
                    from dateutil import parser as date_parser
                    pub = date_parser.parse(pub_el.text)
                except Exception:
                    pub = None
            image = None
            if enclosure_el is not None and enclosure_el.get('url'):
                image = enclosure_el.get('url')
            items.append({'id': guid or link, 'link': link, 'title': title, 'description': desc, 'pubDate': pub, 'image': image})
    except Exception as e:
        print(f"解析既有 RSS ( {path} ) 發生錯誤: {e}")
    return items


def _format_datetime_for_feed(dt):
    if dt is None:
        return datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def fetch_category_with_playwright(cat):
    print(f"正在使用 Playwright 抓取: {cat['name']}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # 在 Actions 中通常為 True
        page = browser.new_page()

        try:
            timeout_ms = 60_000
            try:
                page.goto(cat['url'], wait_until='networkidle', timeout=timeout_ms)
            except Exception as e:
                print(f"導覽 {cat['url']} 失敗或超時 ({timeout_ms}ms)，已跳過此 category: {e}")
                return

            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            anchors = soup.select('a[href*="/articles/view/"], a[href*="/article/"]')

            # 載入既有 feed 項目（若有），以便只加入新的條目
            output_dir = os.environ.get('OUTPUT_DIR', 'docs')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, cat['file'])
            existing = _load_existing_feed_items(output_path)
            existing_ids = set([e['id'] for e in existing if e.get('id')])

            new_items = []
            seen = set()
            added = 0

            for a in anchors:
                try:
                    href = a.get('href')
                    title = a.get_text(strip=True)
                    if not href or not title:
                        continue
                    href = urljoin(cat['url'], href)
                    if href in seen:
                        continue
                    seen.add(href)
                    if href in existing_ids:
                        # 已存在，不再加入
                        continue

                    # 抓取文章頁面
                    desc = ''
                    image = None
                    pubdate = None
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
                        # description
                        meta = art_soup.find('meta', attrs={'name': 'description'})
                        if not meta:
                            meta = art_soup.find('meta', attrs={'property': 'og:description'})
                        if meta and meta.get('content'):
                            meta_desc = meta.get('content').strip()
                            if meta_desc and meta_desc != title:
                                desc = meta_desc

                        # image
                        meta_img = art_soup.find('meta', attrs={'property': 'og:image'})
                        if not meta_img:
                            meta_img = art_soup.find('meta', attrs={'name': 'twitter:image'})
                        if meta_img and meta_img.get('content'):
                            image = urljoin(href, meta_img.get('content').strip())
                        else:
                            img_tag = art_soup.select_one('article img, .article img, .post img, img')
                            if img_tag and img_tag.get('src'):
                                image = urljoin(href, img_tag.get('src').strip())

                        # pubdate
                        pubdate = _parse_pubdate_from_soup(art_soup)

                    if not pubdate:
                        pubdate = datetime.datetime.now(datetime.timezone.utc)

                    new_items.append({'id': href, 'link': href, 'title': title, 'description': desc, 'pubDate': pubdate, 'image': image})
                    added += 1
                    print(f"新增條目: title='{title[:40]}', href={href}, desc={'有' if desc else '無'}, image={'有' if image else '無'}, pub={pubdate})")
                except Exception as e:
                    print(f"單則處理出錯: {e}")

            if not new_items:
                print(f"{cat['name']} 沒有新的條目，保持既有 RSS 不變。")
                return

            # 合併既有與新項目，依 pubDate 排序，去重
            combined = existing + new_items
            # 用 link 作為唯一鍵
            uniq = {}
            for it in combined:
                key = it.get('link') or it.get('id')
                if not key:
                    continue
                # 優先保留較新的 pubDate
                if key in uniq:
                    if it.get('pubDate') and (not uniq[key].get('pubDate') or it['pubDate'] > uniq[key]['pubDate']):
                        uniq[key] = it
                else:
                    uniq[key] = it
            items_sorted = sorted(uniq.values(), key=lambda x: x.get('pubDate') or datetime.datetime.now(datetime.timezone.utc), reverse=True)

            fg = FeedGenerator()
            fg.id(cat['url'])
            fg.title(cat.get('name') or 'RSS')
            fg.link(href=cat['url'], rel='alternate')
            fg.description(cat.get('description') or f"自動抓取的 {cat.get('name')} 頻道")
            fg.language('zh-TW')

            for it in items_sorted:
                fe = fg.add_entry()
                fe.id(it.get('id') or it.get('link'))
                fe.title(it.get('title') or '')
                if it.get('link'):
                    fe.link(href=it.get('link'))
                if it.get('description'):
                    fe.description(it.get('description'))
                if it.get('image'):
                    try:
                        fe.enclosure(it.get('image'), 0, 'image/*')
                    except Exception:
                        if it.get('description'):
                            fe.description(f"<img src=\"{it.get('image')}\"/>\n" + it.get('description'))
                        else:
                            fe.description(f"<img src=\"{it.get('image')}\"/>")
                fe.pubDate(_format_datetime_for_feed(it.get('pubDate')))

            # 寫檔前比較內容是否有變動，避免無意義 commit
            import io
            tmp = io.BytesIO()
            fg.rss_file(tmp)
            new_content = tmp.getvalue()

            prev_content = None
            if os.path.exists(output_path):
                with open(output_path, 'rb') as fh:
                    prev_content = fh.read()

            if prev_content == new_content:
                print(f"{cat['name']} RSS 內容無變動，不寫檔。")
                return

            with open(output_path, 'wb') as fh:
                fh.write(new_content)
            print(f"已生成並更新: {output_path} (新增 {len(new_items)} 條)" )

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