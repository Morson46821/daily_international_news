import time
import re
import html
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from curl_cffi import requests

# 設定香港時區
HK_TZ = timezone(timedelta(hours=8))

def fetch_wion_article_metadata(url):
    """
    從文章內頁提取精確的發佈日期和摘要描述
    """
    try:
        response = requests.get(url, impersonate="chrome", timeout=15)
        if response.status_code != 200:
            return None, "點擊查看詳情"

        page_html = response.text
        
        # 1. 提取發佈時間 (從 dataLayer 提取 ISO 格式)
        publish_match = re.search(r"'publish_date':'(.*?)'", page_html)
        final_dt = None
        if publish_match:
            iso_date = publish_match.group(1)
            dt = datetime.fromisoformat(iso_date)
            final_dt = dt.astimezone(HK_TZ)

        # 2. 提取摘要 (從 meta description 提取)
        summary = "點擊查看詳情"
        desc_match = re.search(r'<meta name="description" content="(.*?)"', page_html)
        if desc_match:
            summary = html.unescape(desc_match.group(1)).strip()
            if len(summary) < 10:
                summary = "點擊查看詳情"

        return final_dt, summary
    except Exception as e:
        print(f"      ⚠️ 解析失敗 ({url}): {e}")
        return None, "點擊查看詳情"

def generate_wion_rss(max_pages=2):
    """
    產生 RSS Feed，修正導航至 Page 2 的邏輯並保持純文字新聞過濾
    """
    fg = FeedGenerator()
    fg.title('WION Latest News - Pro Version')
    fg.link(href='https://www.wionews.com/latest-news')
    fg.description(f'已修正分頁導航邏輯 (共 {max_pages} 頁)')
    fg.language('en')

    base_url = "https://www.wionews.com/latest-news"
    unique_links = set()
    total_count = 0
    
    # 過濾分類 (不含 video 和 photo)
    categories = ["/world/", "/india/", "/business/", "/entertainment/", "/science/", "/trending/"]

    for page in range(1, max_pages + 1):
        # 🟢 關鍵修正：WION 的分頁使用 ?page=X 而非 /page/X
        current_page_url = base_url if page == 1 else f"{base_url}?page={page}"
        print(f"📡 正在處理第 {page}/{max_pages} 頁: {current_page_url}")
        
        try:
            response = requests.get(current_page_url, impersonate="chrome", timeout=20)
            if response.status_code != 200:
                print(f"  ❌ 無法讀取第 {page} 頁")
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            all_links = soup.find_all('a', href=True)
            
            page_count = 0
            for link_tag in all_links:
                href = link_tag['href']
                title = link_tag.get_text(strip=True)
                
                # 僅抓取指定的文字新聞分類
                if not any(p in href for p in categories): continue
                # 排除 video 和 photo (雙重保險)
                if any(p in href for p in ["/videos/", "/photos/"]): continue
                
                if len(title) < 20: continue
                
                full_url = href if href.startswith('http') else "https://www.wionews.com" + href
                if full_url in unique_links: continue
                
                print(f"  🔍 [{total_count+1}] 提取內容: {title[:40]}...")
                
                pub_date, summary = fetch_wion_article_metadata(full_url)
                
                if not pub_date:
                    pub_date = datetime.now(HK_TZ)

                unique_links.add(full_url)
                fe = fg.add_entry()
                fe.id(full_url)
                fe.title(title)
                fe.link(href=full_url)
                fe.description(summary)
                fe.pubDate(pub_date)
                
                total_count += 1
                page_count += 1
                time.sleep(0.3)
            
            print(f"  ✅ 第 {page} 頁處理完成，新增了 {page_count} 則新聞。")
                
        except Exception as e:
            print(f"❌ 處理第 {page} 頁時出錯: {e}")

    output_file = 'wion_world.xml'
    fg.rss_file(output_file, pretty=True)
    print(f"\n✨ 完成！已儲存至 {output_file}")

if __name__ == "__main__":
    generate_wion_rss(max_pages=4)