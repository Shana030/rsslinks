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
    # 優先順序: JSON-LD datePublished > article:published_time > og:published_time > <time datetime>
    from dateutil import parser as date_parser
    import json
    import re

    # 優先解析 JSON-LD 結構化數據
    json_ld_scripts = art_soup.find_all('script', type='application/ld+json')
    for script in json_ld_scripts:
        try:
            # 清理可能的註解和特殊字符
            content = script.string
            if content:
                # 移除可能的 HTML 註解
                content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
                data = json.loads(content)
                # 支持單個對象或數組
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict):
                        # 檢查 datePublished
                        if 'datePublished' in item:
                            try:
                                return date_parser.parse(item['datePublished'])
                            except Exception:
                                pass
                        # 檢查 publishedDate (有些網站用這個)
                        if 'publishedDate' in item:
                            try:
                                return date_parser.parse(item['publishedDate'])
                            except Exception:
                                pass
        except Exception:
            pass

    # 回退到 meta 標籤解析
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

    # 取得今日日期（台灣時區）
    import pytz
    tw_tz = pytz.timezone('Asia/Taipei')
    today_tw = datetime.datetime.now(tw_tz).date()

    # 檢查是否為初始化模式（抓取前N篇）
    initial_fetch = os.environ.get('INITIAL_FETCH', 'false').lower() in ('1', 'true', 'yes')
    max_items = int(os.environ.get('MAX_ITEMS', '20')) if initial_fetch else None

    if initial_fetch:
        print(f"初始化模式: 抓取列表頁前 {max_items} 篇文章")
    else:
        print(f"只抓取今日發佈的文章: {today_tw}")

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

            # 通用文章連結偵測：不依賴特定 URL 格式
            # 策略：選取所有連結，用啟發式規則過濾
            from urllib.parse import urlparse

            base_domain = urlparse(cat['url']).netloc
            all_anchors = soup.find_all('a', href=True)

            filtered_anchors = []
            for a in all_anchors:
                href = a.get('href', '').strip()
                if not href:
                    continue

                # 取得完整 URL
                full_url = urljoin(cat['url'], href)
                parsed = urlparse(full_url)

                # 過濾規則：
                # 0. 排除帶有錨點的連結（頁面內跳轉，如「繼續閱讀」）
                if parsed.fragment:
                    continue

                # 1. 必須是同域名或子域名
                if not parsed.netloc.endswith(base_domain.replace('www.', '')):
                    continue

                # 2. 排除常見的非文章連結
                path_lower = parsed.path.lower()
                path_stripped = parsed.path.rstrip('/')

                # 檢查是否為文章 URL 的明顯特徵
                has_article_keyword = any(kw in path_lower for kw in ['/article/', '/post/', '/p/', '/news/', '/story/'])

                # 如果不包含文章關鍵字，進行嚴格過濾
                if not has_article_keyword:
                    # 排除分類/標籤頁（包含但路徑段數少於3的）
                    if any(kw in path_lower for kw in ['/categories/', '/category/', '/tag/', '/tags/']):
                        path_segments = [p for p in parsed.path.split('/') if p]
                        # /categories/ai 只有2段 -> 排除
                        # /categories/ai/article/123 有4段 -> 保留（但這種情況少見）
                        if len(path_segments) <= 2:
                            continue

                    # 排除作者頁
                    if any(kw in path_lower for kw in ['/author/', '/authors/']):
                        continue

                # 排除其他系統頁面
                excluded_patterns = [
                    '/page/', '/search', '/login', '/register', '/account',
                    '/cart', '/checkout', '/product',
                    '/privacy', '/terms', '/about', '/contact',
                    '/rss', '/feed', '.xml', '.json',
                    '/wp-admin', '/wp-content', '/wp-includes',
                    '/static/', '/assets/', '/images/', '/img/',
                    '.jpg', '.png', '.gif', '.pdf', '.css', '.js'
                ]
                if any(pattern in path_lower for pattern in excluded_patterns):
                    continue

                # 3. 排除首頁和分類頁（路徑太短）
                path_parts = [p for p in parsed.path.split('/') if p]
                if len(path_parts) < 1:
                    continue

                # 4. 檢查標題文字
                title = a.get_text(strip=True)

                # 特殊處理：如果 URL 包含明顯的文章模式，允許沒有標題
                # /article/, /post/, /p/ 關鍵字
                has_article_pattern = any(pattern in path_lower for pattern in ['/article/', '/post/', '/p/'])

                # 或日期路徑模式: /2025/12/24/ (年/月/日)
                import re
                has_date_pattern = bool(re.search(r'/\d{4}/\d{1,2}/\d{1,2}/', parsed.path))

                if not has_article_pattern and not has_date_pattern:
                    # 非文章 URL，必須有標題文字
                    if not title or len(title) < 5:
                        continue

                    # 排除導航類文字
                    nav_keywords = ['上一頁', '下一頁', 'next', 'previous', 'prev', '更多', 'more', '首頁', 'home']
                    if title.lower() in nav_keywords or any(kw in title.lower() for kw in nav_keywords if len(kw) > 3):
                        continue

                filtered_anchors.append(a)

            anchors = filtered_anchors
            print(f"通用過濾後找到 {len(anchors)} 個可能的文章連結")

            # 載入既有 feed 項目（若有），以便只加入新的條目
            output_dir = os.environ.get('OUTPUT_DIR', 'docs')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, cat['file'])
            existing = _load_existing_feed_items(output_path)
            existing_ids = set([e['id'] for e in existing if e.get('id')])

            new_items = []
            seen = set()
            added = 0
            skipped_old = 0
            skipped_existing = 0

            # 在初始化模式下，限制處理的連結數量以避免過長執行時間
            # 每個來源最多抓取前 20 篇文章（列表頁顯示的數量）
            max_links_to_process = 20 if initial_fetch else len(anchors)
            anchors_to_process = anchors[:max_links_to_process] if initial_fetch else anchors

            for a in anchors_to_process:
                try:
                    href = a.get('href')
                    title = a.get_text(strip=True)
                    if not href:
                        continue

                    href = urljoin(cat['url'], href)
                    if href in seen:
                        continue
                    seen.add(href)
                    if href in existing_ids:
                        # 已存在，不再加入
                        skipped_existing += 1
                        continue

                    # 抓取文章頁面以取得標題、描述和發佈日期
                    # 對於 /article/ 等明確的文章 URL，即使列表頁沒有標題也要進入文章頁抓取
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

                        # 從文章頁獲取標題（如果列表頁沒有標題）
                        if not title:
                            # 嘗試從 og:title 或 title 標籤獲取
                            meta_title = art_soup.find('meta', attrs={'property': 'og:title'})
                            if meta_title and meta_title.get('content'):
                                title = meta_title.get('content').strip()
                            elif art_soup.title and art_soup.title.string:
                                title = art_soup.title.string.strip()

                            # 如果還是沒有標題，跳過這篇文章
                            if not title:
                                print(f"跳過無標題文章: {href}")
                                continue
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

                    # 檢查是否為今日發佈（僅在非初始化模式）
                    if not initial_fetch:
                        pubdate_tw = pubdate.astimezone(tw_tz).date()
                        if pubdate_tw != today_tw:
                            print(f"跳過非今日文章: {title[:40]} (發佈日期: {pubdate_tw})")
                            skipped_old += 1
                            continue

                    new_items.append({'id': href, 'link': href, 'title': title, 'description': desc, 'pubDate': pubdate, 'image': image})
                    added += 1
                    print(f"新增條目: title='{title[:40]}', href={href}, desc={'有' if desc else '無'}, image={'有' if image else '無'}, pub={pubdate})")

                    # 初始化模式下檢查是否已達到上限
                    if initial_fetch and added >= max_items:
                        print(f"已達到最大項目數 {max_items}，停止抓取")
                        break
                except Exception as e:
                    print(f"單則處理出錯: {e}")

            print(f"{cat['name']} 抓取統計: 已存在={skipped_existing}, 非今日={skipped_old}, 新增={added}")

            if not new_items:
                print(f"{cat['name']} 沒有今日新的條目，保持既有 RSS 不變。")
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
    # 根據 categories.json 生成 index，包含分類名稱和描述
    # 不包含任何動態資訊（如文章數量、時間），以避免不必要的 commit
    feeds_info = []
    for cat in CATEGORIES:
        feeds_info.append({
            'name': cat.get('name', cat['file']),
            'file': cat['file'],
            'url': cat.get('url', ''),
            'description': cat.get('description', '')
        })

    # 寫入 index.html（完全靜態，除非 categories.json 變更否則不會改變）
    index_path = os.path.join(output_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as fh:
        fh.write("<!doctype html>\n<html lang=\"zh-TW\">\n<head>\n  <meta charset=\"utf-8\" />\n  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />\n  <title>RSS Links - 自動產生的 RSS 訂閱源</title>\n  <style>\n    body { font-family: system-ui, -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }\n    h1 { color: #333; }\n    .feed-item { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 8px; background: #f9f9f9; }\n    .feed-item h3 { margin: 0 0 10px 0; }\n    .feed-item a { color: #0066cc; text-decoration: none; font-weight: 500; }\n    .feed-item a:hover { text-decoration: underline; }\n    .source-url { color: #888; font-size: 0.85em; word-break: break-all; }\n    footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em; }\n  </style>\n</head>\n<body>\n  <h1>RSS Links</h1>\n  <p>自動產生的 RSS 訂閱源</p>\n")
        for feed in feeds_info:
            # RSS XML 檔案透過 jsDelivr CDN 從 GitHub Release 提供（正確的 Content-Type）
            feed_url = f"https://cdn.jsdelivr.net/gh/Shana030/rsslinks@latest-feeds/{feed['file']}"
            fh.write(f"  <div class=\"feed-item\">\n")
            fh.write(f"    <h3><a href=\"{feed_url}\">{feed['name']}</a></h3>\n")
            if feed['description']:
                fh.write(f"    <p>{feed['description']}</p>\n")
            if feed['url']:
                fh.write(f"    <div class=\"source-url\">來源: <a href=\"{feed['url']}\" target=\"_blank\">{feed['url']}</a></div>\n")
            fh.write(f"  </div>\n")
        fh.write("  <footer>\n    <p>自動更新，每6小時執行一次</p>\n  </footer>\n</body>\n</html>")
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