import feedparser
import requests
import trafilatura
import re
import ssl
import time
import random
import urllib3
from datetime import datetime, timezone  # <--- 確保這裡加入了 timezone
from trafilatura.settings import use_config
import email.utils # 用於精確解析時區
import os
from curl_cffi import requests as cur_requests #

# 1. 基礎設定
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context
config = use_config()
session = requests.Session()

def clean_text(raw_html):
    """清理 HTML 標籤"""
    if not raw_html: return ""
    clean = re.sub(r'<[^>]+>', '', raw_html)
    return " ".join(clean.split())

def fetch_full_content(url):
    """使用 curl_cffi 繞過封鎖並提取網頁正文"""
    try:
        # 使用 impersonate 模擬真實瀏覽器
        response = cur_requests.get(
            url, 
            impersonate="chrome", 
            timeout=15, 
            verify=False
        )
        
        if response.status_code == 200:
            # 將抓到的 HTML 交給 trafilatura 解析
            content = trafilatura.extract(response.text, config=config)
            if content and len(content.strip()) > 150:
                return content.strip()
        else:
            print(f"      (跳轉或請求失敗，狀態碼: {response.status_code})")
        return None
    except Exception as e:
        print(f"      (提取過程發生錯誤: {e})")
        return None


def run_comparison_test(source_path_or_url, source_name):
    print(f"\n讀取源：[{source_name}]")
    print("=" * 50)
    
    # --- 🟢 更新：支援本地檔案讀取 ---
    try:
        if os.path.exists(source_path_or_url):
            print(f"📂 偵測到本地檔案，正在讀取: {source_path_or_url}")
            with open(source_path_or_url, 'r', encoding='utf-8') as f:
                feed_content = f.read()
            feed = feedparser.parse(feed_content)
        else:
            print(f"🌐 偵測到網路連結，正在請求: {source_path_or_url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
            response = requests.get(source_path_or_url, headers=headers, timeout=10, verify=False)
            feed = feedparser.parse(response.text)
    except Exception as e:
        print(f"❌ 無法讀取來源: {e}")
        return

    # 取得帶有時區資訊的當前 UTC 時間
    now_utc = datetime.now(timezone.utc)
    print(f"當前系統時間 (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)

    for i, entry in enumerate(feed.entries[:5]):  # 測試前 x 篇
        title = entry.get('title', '無標題')
        # 🟢 修正：正確定義 link 變數供後續使用
        link = entry.link 
        
        # --- 1. 通用日期解析與補全 ---
        raw_date = entry.get('published') or entry.get('updated') or "無日期資訊"
        dt = None
        is_fallback = False
        
        if raw_date != "無日期資訊":
            try:
                # 優先級 1：嘗試標準解析 (包含時區與時間)
                dt = email.utils.parsedate_to_datetime(raw_date)
            except:
                # 優先級 2：通用補全 (只要 feedparser 能抓到年月日，就設為 00:00)
                # 這是處理所有「非標準日期格式」的通用方法
                ds = entry.get('published_parsed') or entry.get('updated_parsed')
                if ds:
                    dt = datetime(ds.tm_year, ds.tm_mon, ds.tm_mday, 0, 0, 0, tzinfo=timezone.utc)
                    is_fallback = True

        print(f"新聞 {i+1}: {title[:40]}...")
        print(f"  🔗 URL: {link}")
        print(f"  📅 原始日期: {raw_date}")
        
        # --- 2. 時區與 30 小時判斷測試 ---
        is_recent = False
        if dt:
            dt_utc = dt.astimezone(timezone.utc)
            diff = now_utc - dt_utc
            hours_ago = diff.total_seconds() / 3600
            is_recent = hours_ago <= 30
            
            # 設定顯示標籤：若補全則顯示 [補全 00:00]
            tz_display = f"UTC [補全 00:00]" if is_fallback else f"{dt.tzinfo}"
            
            status_icon = "✅" if is_recent else "❌"
            print(f"  🔍 時區識別: {tz_display} (距離現在: {hours_ago:.1f} 小時)")
            print(f"  🕒 判定結果: {status_icon} {'符合30小時內' if is_recent else '超過30小時'}")
        else:
            print(f"  🔍 時區識別: ⚠️ 完全無法解析日期資訊")

        # 3. 摘要與正文提取測試 (你原有的邏輯，已修正變數)
        raw_summary = (
            entry.get('summary', '') or 
            entry.get('description', '') or 
            entry.get('content', [{}])[0].get('value', '')
        )
        summary_text = clean_text(raw_summary)
        
        if len(summary_text) > 20:
            print(f"  🔹 [摘要提取] ✅ 成功 ({len(summary_text)} 字)")
        else:
            print(f"  🔹 [摘要提取] ❌ 失敗")

        # 使用剛才定義好的 link
        full_content = fetch_full_content(link)
        if full_content:
            print(f"  🔸 [正文提取] ✅ 成功 ({len(full_content)} 字)")
        else:
            print(f"  🔸 [正文提取] ❌ 失敗")
        
        print("-" * 30)
        time.sleep(1)

if __name__ == "__main__":
    # 提醒：你原本提供的 NPR 連結是單篇新聞網頁，而非 RSS Feed 
    # 若要測試 RSS，請確保 URL 是以 .xml 或 .rss 結尾的 Feed 地址
    test_sources = [
        {"name": "HK FREE PRESS", "url": "https://www.hongkongfp.com/feed/"},
        #{"name": "Sixth Tone", "url": "https://www.sixthtone.com/rss"},
        {"name": "BBC", "url": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"},
        {"name": "SCMP China", "url": "https://www.scmp.com/rss/2/feed/"},
        #{"name": "WION", "url": "/Users/tonywong/Documents/Auto-news-feeding/AI_Agent/wion_world.xml"},
    ]

    print("🔍 開始『日期、摘要與正文』綜合測試")
    for src in test_sources:
        run_comparison_test(src['url'], src['name'])