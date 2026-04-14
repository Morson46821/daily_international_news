import feedparser
import json
import time
import ssl
import urllib.request
import requests
import trafilatura
from trafilatura.settings import use_config
from difflib import SequenceMatcher
import re
import torch
from sentence_transformers import SentenceTransformer, util
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import sys
import random
import time
from country_named_entity_recognition import find_countries
import email.utils  # 新增：用於解析 RSS 日期
from datetime import datetime, timedelta, timezone
from curl_cffi import requests as curl_requests # 引入 curl_cffi

# --- 新增：環境與模型初始化 ---
# 自動偵測設備：優先 MPS (Mac) > CUDA (Nvidia) > CPU
device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
print(f"系統：正在使用 [{device}] 設備運行 NLP 語義模型")

# 加載模型
# Tony 這是NLP的AI模型，當多個來源（如 BBC 和 Reuters）都報導了同一則新聞時，標題可能長得不一樣。這時會使用 NLP 模型將標題或內文轉化為「語義向量」，計算它們之間的相似度。
semantic_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2').to(device)

# 基礎環境設定
ssl._create_default_https_context = ssl._create_unverified_context
config = use_config()
config.set("DEFAULT", "MAX_FILE_SIZE", "10000000")

# 🟢 關鍵修正 1：將 session 定義在這裡，讓所有函數都能共用
session = requests.Session()

# Ollama 設定
# Tony 使用Gemma4:e2b 的modal去來分辦World的新聞屬於那個地區
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma4:e2b" 


# 地理關鍵字與映射 (保持原有邏輯)
# Tony 這個program按幾個step去判斷一篇region是world的新聞到底是屬於那個地區，首先是根據以下關鍵字，將標題存在對應關鍵字的新聞歸到那個地區


REGION_KEYWORDS = {
    "香港": ["Hong Kong", "HKers", "Central", "Kowloon"],
    "中國": ["China", "Mainland", "Beijing", "Shanghai", "CCP", "Xi Jinping", "Shenzhen"],
    "北美": [
        "US", "USA", "America", "Washington", "New York", "Trump", "Biden", "Hegseth", 
        "Harris", "Elon Musk", "White House", "Pentagon", "Congress", "Senate", 
        "Canada", "Ottawa", "Toronto", "Vancouver", "Trudeau"
    ],
    "歐洲": [
        "Europe", "UK", "London", "France", "Paris", "Germany", "Berlin", "Ukraine", 
        "Kyiv", "Russia", "Moscow", "EU", "NATO", "Brussels", "Starmer", "Macron", 
        "Scholz", "Putin", "Zelenskyy", "Italy", "Rome", "Spain", "Madrid", "Poland",
        "Hungary"
    ],
    "亞洲": [
        "Japan", "Tokyo", "Osaka", "Ishiba", "Korea", "Seoul", "Yoon Suk-yeol", 
        "Taiwan", "Taipei", "TSMC", "Lai Ching-te", "India", "Delhi", "Modi", 
        "Vietnam", "Hanoi", "Singapore", "ASEAN", "Thailand", "Bangkok", 
        "Philippines", "Manila", "Indonesia", "Jakarta", "Myanmar"
    ],
    "中東": [
        "Iran", "Tehran", "Israel", "Gaza", "Hamas", "Tel Aviv", "Netanyahu", 
        "Hormuz", "Syria", "Dubai", "UAE", "Beirut", "Lebanon", "Hezbollah", 
        "Saudi Arabia", "Riyadh", "Red Sea", "Yemen", "Houthis", "Qatar", "Doha"
    ],
    "非洲": [
        "Africa", "Egypt", "Cairo", "Nigeria", "Lagos", "South Africa", "Cape Town", 
        "Johannesburg", "Kenya", "Nairobi", "Ethiopia", "Sudan", "Libya", "AU", "Maghreb"
    ],
    "南美及拉丁美洲": [
        "Brazil", "Brasilia", "Lula", "Argentina", "Milei", "Buenos Aires", 
        "Chile", "Santiago", "Colombia", "Peru", "Venezuela", "Maduro", 
        "Mexico", "Mexico City", "Cuba", "Havana", "Panama"
    ]
}

#首先程式會依據RSS list中的region判斷新聞的地區，但如果見到新聞的網址有以下的keyword, 就會更新新聞的分區
URL_REGION_MAP = {
    "hong-kong": "香港", "china": "中國", "middle-east": "中東",
    "united-kingdom": "歐洲", "europe": "歐洲", "asia": "亞洲",
    "us-and-canada": "北美", "americas": "北美", "africa": "非洲",
    "latin-america": "南美及拉丁美洲", "south-america": "南美及拉丁美洲"
}

#Tony 這行代碼定義了一組 「停用詞 (Stop Words)」。在自然語言處理（NLP）中，停用詞是指那些在語句中出現頻率極高，但對於理解核心語義或區分文章主題貢獻極小的詞彙。
# --- 停用詞集合 
STOP_WORDS = {
    # 中文核心虛詞
    "的", "原", "是", "在", "了", "和", "與", "或", "中", "於", "及", "之", "地", "得",
    # 英文冠詞與連詞
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "until", "while",
    # 介詞
    "of", "at", "by", "for", "with", "about", "against", "between", "into", "through", 
    "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", 
    "out", "on", "off", "over", "under",
    # 代名詞與指示詞
    "it", "its", "they", "them", "their", "who", "whom", "which", "what", "that", 
    "these", "those", "all", "any", "both", "each", "few", "more", "most", "other", "some",
    # 動詞與助動詞
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having", 
    "do", "does", "did", "doing", "can", "will", "should", "s", "t", "re", "ve", "m", "ll",
    # 新聞常用詞（中性噪音）
    "says", "said", "say", "reports", "reporting", "claims", "claimed", "tells", "told", 
    "breaking", "news", "update", "live", "latest", "according",
    # 副詞
    "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "now"
}


#這段 clean_text(t) 函數是你程式中的**「文字洗滌器」**。它的核心作用是在進行新聞比對之前，把原始標題或內容中的「雜訊」去掉，只留下最關鍵的資訊。
def clean_text(t):
    if not t: return ""
    # 保留數字、字母與中文字，這對判定新聞事件（如日期、金額、編號）非常重要
    t = t.lower()
    t = re.sub(r'[\(\[\uff08\uff3b].*?[\)\]\uff09\uff3d]', '', t)
    t = re.sub(r'[^\w\s\u4e00-\u9fa5\d]', '', t) # 修改：保留數字 \d
    return t.strip()

#這段 is_similar 函數是你程式中的**「輕量級比對引擎」**。它的作用是在動用昂貴的 AI 模型（如 SentenceTransformer）之前，先用純數學演算法來快速判斷兩個新聞標題是否相似。
def is_similar(s1, s2, threshold=0.55):
    """純演算法標題比對"""
    str1, str2 = clean_text(s1), clean_text(s2)
    if not str1 or not str2: return False

    seq_score = SequenceMatcher(None, str1, str2).ratio()
    words1 = set(str1.split()) if str1.isascii() else set(str1)
    words2 = set(str2.split()) if str2.isascii() else set(str2)
    
    # 過濾停用詞並要求長度大於 1
    set1 = {w for w in words1 if w not in STOP_WORDS and len(w) > 1}
    set2 = {w for w in words2 if w not in STOP_WORDS and len(w) > 1}
    
    jaccard_score = 0
    if set1 and set2:
        jaccard_score = len(set1 & set2) / len(set1 | set2)

    return max(seq_score, jaccard_score) > threshold

#如果說前面的 is_similar 是快速篩選，那麼這段代碼就是深度診斷。它結合了 NLP（自然語言處理）、停用詞
#過濾、數字邏輯比對以及地理位置校正。它的目標只有一個：確保你的自動化報紙裡，同一個事件不會出現第二次，即便不同媒體的寫法差很多。
def is_content_similar(c1, c2, threshold=0.8):
    if not c1 or not c2:
        return False

    # --- [新增] 1. 斷詞與停用詞過濾 (Tokenization & Stop Words) ---
    # 同時處理中文字元與英文單字
    def get_clean_words(text):
        # 轉小寫並只提取中文單字與英文單詞
        raw_words = re.findall(r'[\u4e00-\u9fa5]|[a-zA-Z]+', text.lower())
        # 過濾掉你在 { } 集合中定義的停用詞
        return [w for w in raw_words if w not in STOP_WORDS]

    # 我們針對前 200 字（標題+導言精華）進行快速比對
    clean_words1 = get_clean_words(c1[:200])
    clean_words2 = get_clean_words(c2[:200])

    # 如果過濾後的關鍵詞完全一致，直接判定為重複（省去跑 AI 模型的時間）
    if clean_words1 == clean_words2 and len(clean_words1) > 5:
        return True

    # --- 2. 取得向量 (Encoding) ---
    #AI 語義理解 (Embedding) 它會把文字轉化為高維度的向量數字。透過計算「餘弦相似度（Cosine Similarity）」
    #，它能發現 「美股強勢反彈」 與 「紐約股市今日大漲」 雖然字面上沒有一個字相同，但語義向量非常接近。
    
    clean_text1 = " ".join(clean_words1)
    clean_text2 = " ".join(clean_words2)
    
    # 如果過濾後內容太少，回退到原始前 600 字
    source1 = clean_text1 if len(clean_text1) > 20 else c1[:600]
    source2 = clean_text2 if len(clean_text2) > 20 else c2[:600]

    emb1 = semantic_model.encode(source1, convert_to_tensor=True)
    emb2 = semantic_model.encode(source2, convert_to_tensor=True)
    
    # 3. 計算餘弦相似度
    cosine_score = util.cos_sim(emb1, emb2).item()
    
    # 4. 數字比對優化：排除常見年份
    #如果兩則新聞語義很像，但數字對不上（例如一個說加息 1 碼，一個說 3 碼），這道防線能防止它們被錯誤合併。
    def get_important_nums(text):
        nums = set(re.findall(r'\b\d{2,}\b', text[:600]))
        return {n for n in nums if n not in ['2023', '2024', '2025', '2026', '2027']}

    nums1 = get_important_nums(c1)
    nums2 = get_important_nums(c2)
    common_nums = nums1 & nums2

    # --- 嚴格判定門檻 ---
    
    # 🔴 門檻 A：極高相似度 (0.85+)
    if cosine_score > 0.85: 
        return True
    
    # 🟡 門檻 B：中高相似度 (0.75 - 0.85)
    if cosine_score > 0.75:
        # 如果有至少 2 個共同關鍵數字
        if len(common_nums) >= 2:
            return True
            
        # 排除特定地理誤判 
        countries1 = set(find_countries(c1[:300])) # 回傳的是國家對象列表
        countries2 = set(find_countries(c2[:300]))
    
        # 獲取國家 ID (如 'HK', 'GB', 'US')
        ids1 = {c[0].alpha_2 for c in countries1}
        ids2 = {c[0].alpha_2 for c in countries2}

        # 核心校正：如果兩篇都提到了國家，但國家 ID 完全對不上
        if ids1 and ids2 and not (ids1 & ids2):
            if cosine_score < 0.92:
                return False

#從RSS中提取新聞
def fetch_content(url, source=None):
    # 隨機 User-Agent 列表
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]

    try:
        # 結合：impersonate(底層偽裝) + headers(上層隨機) + timeout(適中)
        resp = curl_requests.get(
            url, 
            impersonate="chrome", 
            timeout=20, 
            headers={"User-Agent": random.choice(user_agents)},
            verify=False
        )
        
        if resp.status_code == 200:
            # 使用 resp.content (byte串流) 傳給 trafilatura 解析效果最好
            content = trafilatura.extract(resp.content, config=config)
            
            # 確保內容長度足夠，避免抓到空白頁或阻擋頁面
            if content and len(content) > 100:
                return content
        else:
            print(f"      ⚠️ 請求失敗 (Status: {resp.status_code}): {url}")
            
    except Exception as e:
        # 抓取異常時不中斷主程式
        print(f"      ❌ curl_cffi 抓取異常: {str(e)}")
        
    return None
        
        
#利用AI將前面幾步都無法分類的新聞再分類        
def ask_ollama_region(title):
    regions = ["香港", "中國", "北美", "歐洲", "亞洲", "中東", "非洲", "南美及拉丁美洲"]
    # 優化 Prompt：給予明確範例，增加穩定性
    prompt = f"""
    任務：判斷新聞標題的地理位置。
    選項：{', '.join(regions)}
    規則：只回傳地名，不可有標點符號或解釋。若無法判斷，回傳「其他」。

    範例：
    標題：German males under 45 may need military approval
    地區：歐洲

    現在開始：
    標題：{title}
    地區："""

    try:
        payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        response = requests.post(OLLAMA_URL, json=payload, timeout=15)
        # 取得結果並移除所有空白與換行
        result = response.json().get("response", "").strip().replace(" ", "")

        # 關鍵優化：只要 AI 回傳中包含關鍵字，就回傳該地區
        for reg in regions:
            if reg in result:
                return reg
        return "其他"
    except Exception as e:
        print(f"    ❌ AI 調用失敗: {e}")
        return "其他"

# --- 在檔案頂部定義全域計數器，用於追蹤 GPU/AI 負載 ---
AI_CALL_COUNT = 0 


#這段 infer_region 函數是你程式中的**「地理分揀中心」。它的核心邏輯是「由快到慢、由省錢到費錢」**。
def infer_region(title, link, current_region, source_name,summary=None):
    """
    判定新聞的地理位置：優先使用連結與關鍵字，最後才調用 AI 判定。
    """
    global AI_CALL_COUNT  # 聲明使用全域變數，以便在函數內更新計數

    # 1. 預先檢查：若來源本身已有明確地區（如 SCMP 香港、BBC 亞洲），直接回傳
    if current_region != "World": 
        return current_region 

    link_l = (link or "").lower()
    title_l = (title or "").lower()
    summary_l = (summary or "").lower()

    # 2. 快速過濾：透過 URL 路徑判定地區 (最節省效能)
    # 🟢 修正：如果是 Google News 的跳轉連結，直接跳過 URL 比對，因為路徑已被加密
    if "google.com" not in link_l:
        for pattern, reg in URL_REGION_MAP.items():
            if pattern in link_l: 
                return reg
    else:
        # 你可以在這裡加個小 Log 方便觀察 (可選)
        # print(f"     (Google News 連結，跳過 URL 比對)")
        pass

    # 3. 關鍵字比對：先找標題，再找摘要
    
    for reg, keywords in REGION_KEYWORDS.items():
        # A. 先看標題是否有關鍵字
        if any(kw.lower() in title_l for kw in keywords): 
            return reg
        
        # B. [新增] 若標題沒中，看摘要 (Summary) 是否有關鍵字
        if summary_l and any(kw.lower() in summary_l for kw in keywords):
            return reg

    # 4. AI 救援：若以上規則皆未命中，則調用 Ollama 模型進行判定
    global AI_CALL_COUNT
    AI_CALL_COUNT += 1 

    # --- 這裡才是真正「送進 AI」的文章 ---
    summary_snippet = (summary or "無摘要").replace('\n', ' ')
    print(f"  🧠 [呼叫 AI 中] 來源: {source_name}")
    print(f"     ├─ 標題: {title}")
    print(f"     └─ 摘要: {summary_snippet}")
    
    result = ask_ollama_region(title)
    
    print(f"     📍 AI 回傳結果 -> 【{result}】")
    print("-" * 50)
    
    return result
    
    
    return ask_ollama_region(title)
    
def main():
    
    # 更新後的 NEWS_SOURCES：包含路透社與自定義 limit
    NEWS_SOURCES = [
        #香港
        {"name": "SCMP HK", "region": "香港", "url": "https://www.scmp.com/rss/2/feed/", "limit": 10},
        {"name": "HK Free Press", "region": "香港", "url": "https://www.hongkongfp.com/feed/", "limit": 10},
        {"name": "RTHK HK", "region": "香港", "url": "https://rthk.hk/rthk/news/rss/e_expressnews_elocal.xml", "limit": 10},
        # hl=en (語言：英文), gl=HK (地區：美國), ceid=US:en (搜尋身分)
        {"name": "Google News HK", "region": "香港", "url": "https://news.google.com/rss/search?q=Hong+Kong+when:24h&hl=en-US&gl=HK&ceid=US:en", "limit": 10},

        # 中國
        {"name": "SCMP China", "region": "中國", "url": "https://www.scmp.com/rss/4/feed/", "limit": 10},
        {"name": "RTHK China", "region": "中國", "url": "https://rthk.hk/rthk/news/rss/e_expressnews_egreaterchina.xml", "limit": 10},
        {"name": "Google News China", "region": "中國", "url": "https://news.google.com/rss/search?q=China+when:24h&hl=en-US&gl=HK&ceid=US:en", "limit": 10},
        
    
        #北美
        {"name": "BBC North America", "region": "北美", "url": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", "limit": 10},
        
        #南美      
        {"name": "BBC Latin America", "region": "南美及拉丁美洲", "url": "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml", "limit": 10},
        
        
         # 中東
        {"name": "UN News Middle East", "region": "中東", "url": "https://news.un.org/feed/subscribe/en/news/region/middle-east/feed/rss.xml", "limit": 10},
        {"name": "BBC Middle East", "region": "中東", "url": "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "limit": 10},
     
        # 非洲
        {"name": "UN News Africa", "region": "非洲", "url": "https://news.un.org/feed/subscribe/en/news/region/africa/feed/rss.xml", "limit": 10},
     	{"name": "BBC Africa", "region": "非洲", "url": "https://feeds.bbci.co.uk/news/world/africa/rss.xml", "limit": 10},
     	{"name": "DW Africa", "region": "非洲", "url": "https://rss.dw.com/rdf/rss-en-africa", "limit": 10},
     	{"name": "BBC UK News", "region": "歐洲", "url": "https://feeds.bbci.co.uk/news/uk/rss.xml", "limit": 3},
        {"name": "BBC England", "region": "歐洲", "url": "https://feeds.bbci.co.uk/news/england/rss.xml", "limit": 3},
     	
        # 歐洲
        {"name": "UN News Europe", "region": "歐洲", "url": "https://news.un.org/feed/subscribe/en/news/region/europe/feed/rss.xml", "limit": 10},
        {"name": "BBC Europe", "region": "歐洲", "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml", "limit": 10},
        {"name": "DW Europe", "region": "歐洲", "url": "https://rss.dw.com/rdf/rss-en-eu", "limit": 10},

        # 亞洲
        {"name": "UN News Europe", "region": "亞洲", "url": "https://news.un.org/feed/subscribe/en/news/region/asia-pacific/feed/rss.xml", "limit": 25},
        {"name": "BBC Asia", "region": "亞洲", "url": "https://feeds.bbci.co.uk/news/world/asia/rss.xml", "limit": 20},
        {"name": "DW Asia", "region": "亞洲", "url": "https://rss.dw.com/rdf/rss-en-asia", "limit": 20},
        {"name": "SCMP Asia", "region": "亞洲", "url": "https://www.scmp.com/rss/3/feed/", "limit": 20},
     
        #商業
        {"name": "BBC Business", "region": "商業", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "limit": 15},
        {"name": "DW Business", "region": "商業", "url": "https://rss.dw.com/rdf/rss-en-bus", "limit": 15},
        {"name":"ABC Business","region":"商業","url":"https://feeds.abcnews.com/abcnews/moneyheadlines","limit":15},
        {"name":"CBC Business","region":"商業","url":"https://www.cbc.ca/webfeed/rss/rss-business","limit":10},
        {"name":"SCMP Business","region":"商業","url":"https://www.scmp.com/rss/92/feed/","limit":10},
        
        #科技
        {"name":"BBC Tech","region":"科技","url":"https://feeds.bbci.co.uk/news/technology/rss.xml","limit":10},
        {"name":"SCMP Tech","region":"科技","url":"https://www.scmp.com/rss/36/feed/","limit":10},
        
        #World
        {"name": "BBC World News", "region": "World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "limit": 15},
        {"name": "DW World", "region": "World", "url": "https://rss.dw.com/rdf/rss-en-world", "limit": 10},
        {"name": "SCMP World", "region": "World", "url": "https://www.scmp.com/rss/5/feed/", "limit": 10},
        {"name": "AP News", "region": "World", "url": "https://news.google.com/rss/search?q=when:24h+source:Associated_Press", "limit": 20},
        {"name": "Al Jazeera", "region": "World", "url": "https://www.aljazeera.com/xml/rss/all.xml", "limit": 20},
        {"name": "The Guardian", "region": "World", "url": "https://www.theguardian.com/world/rss", "limit": 20},
        {"name": "Reuters", "region": "World", "url": "https://news.google.com/rss/search?q=source:Reuters+when:24h&hl=en-US&gl=US&ceid=US:en", "limit": 25},
        {"name":"NHK World-Japan","region":"World","url":"https://www3.nhk.or.jp/nhkworld/data/en/news/backstory/rss.xml","limit":25},
        {"name":"France 24","region":"World","url":"https://www.france24.com/en/rss","limit":20},
        {"name":"ABC World","region":"World","url":"https://feeds.abcnews.com/abcnews/topstories","limit":10},
        {"name":"ABC World","region":"World","url":"https://feeds.abcnews.com/abcnews/internationalheadlines","limit":10},       
        {"name":"UN News World","region":"World","url":"https://news.un.org/feed/subscribe/en/news/region/americas/feed/rss.xml","limit":10},
        {"name":"UN News World","region":"World","url":"https://news.un.org/feed/subscribe/en/news/region/global/feed/rss.xml","limit":10},
        {"name":"CBC World","region":"World","url":"https://www.cbc.ca/webfeed/rss/rss-world","limit":10},
        {"name":"NPR World","region":"World","url":"https://feeds.npr.org/1001/rss.xml","limit":10},
        {"name":"WION World","region":"World","url":"/Users/tonywong/Documents/Auto-news-feeding/Step1_Scrapper/wion_world.xml","limit":20},
    ]

    pre_filtered_articles = []
    world_queue = [] # <--- 這是您要找的隊伍列
    seen_titles = set()
    confirmed_titles = set()

    # 修改：將 seen_titles 改為針對「每個來源」獨立去重
    # 這樣 Reuters 的標題就不會被 BBC 擋住
    
    print("🚀 第一階段：抓取 30 小時內的新聞...")
    
    # 設定一個共用的 Header
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8',
    }

    global_seen_titles = set()
    overall_source_counts = {}
    pre_filtered_articles = []
    world_queue = []
    
    # 定義 30 小時的時間界限 (使用 UTC 確保一致性)
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=30)
    
    for source in NEWS_SOURCES:
        # 🟢 關鍵修正 1：獲取該來源獨立的 limit，若沒設定則預設抓 15 篇
        max_allowed = source.get('limit', 15) 
        count_for_this_source = 0
        skipped_old = 0 # 統計跳過多少舊聞
        
        try:
            # --- 🟢 修改開始：支援本地檔案讀取 🟢 ---
            # 判斷 URL 是否為本地絕對路徑或以 file:// 開頭
            if source['url'].startswith('/') or source['url'].startswith('file://'):
                local_path = source['url'].replace('file://', '')
                with open(local_path, 'r', encoding='utf-8') as f:
                    xml_data = f.read()
                
            else:
                # 原有的網絡抓取邏輯
                response = requests.get(source['url'], headers=headers, timeout=15, verify=False)
                xml_data = response.text
            # --- 🔴 修改結束 🔴 ---
            
            # 將 xml_data 交給 feedparser 解析 (原本是 response.text)
            feed = feedparser.parse(xml_data)
            
            # 檢查抓取是否成功
            if not feed.entries:
                # 這裡稍微改一下，如果是本地讀取就不印狀態碼
                status_info = f" (狀態碼: {response.status_code})" if 'response' in locals() else ""
                print(f"  ⚠️ {source['name']} 沒有抓到任何文章{status_info}")
                continue

            for entry in feed.entries:
                # 🛑 檢查 1：是否已達到該來源的數量上限
                if count_for_this_source >= max_allowed:
                    break
                
                # 🛑 檢查 2：日期過濾 
                # 優先抓取 parsed 格式，若無則解析原始字串
                date_struct = entry.get('published_parsed') or entry.get('updated_parsed')
                if date_struct:
                    # 將 struct_time 轉為帶有 UTC 時區的 datetime
                    pub_date = datetime(*date_struct[:6], tzinfo=timezone.utc)
                else:
                    # 備援方案：解析原始字串 (如 "Mon, 07 Apr 2026 08:00:00 GMT")
                    raw_date = entry.get('published') or entry.get('updated')
                    if raw_date:
                        try:
                            pub_date = email.utils.parsedate_to_datetime(raw_date)
                        except:
                            pub_date = datetime.now(timezone.utc) # 解析失敗則假設是新的
                    else:
                        pub_date = datetime.now(timezone.utc)

                # 比對時間
                if pub_date < time_threshold:
                    skipped_old += 1
                    continue # 跳過超過 30 小時的新聞
                
                # 🛑 檢查 3：全域標題去重
                t_clean = entry.title.strip().lower()
                
                # 只過濾不同RSS的有同一篇文章的重複
               # --- [核心修改] 跨來源全域標題檢查 ---
                if t_clean in global_seen_titles:
                    # 如果標題已經在之前的任何一個 RSS 來源出現過，就跳過
                    continue
                
                # 如果是新的標題，加入全域記錄
                global_seen_titles.add(t_clean)
                # -----------------------------------

                # 通過所有檢查，加入清單
                article_item = {
                    "source": source['name'], 
                    "region": source['region'], 
                    "title": entry.title, 
                    "link": entry.link,
                    "summary": entry.get('summary') or entry.get('description') or '',
                    "pub_date": pub_date.strftime('%Y-%m-%d %H:%M') # 紀錄日期方便 debug
                }
                
                # 根據來源地區分流
                if source['region'] != "World":
                    pre_filtered_articles.append(article_item)
                else:
                    world_queue.append(article_item)

                count_for_this_source += 1
            overall_source_counts[source['name']] = count_for_this_source
            print(f"  ✅ {source['name']}: 抓取 {count_for_this_source} 篇 (已過濾 {skipped_old} 篇舊聞)")

        except Exception as e:
            print(f"  ❌ {source['name']} 失敗: {e}")
    
    # --- 第二階段處理：只需判定地區，不再需要檢查 limit ---
    #在第一階段中，所有標記為 World（全球混合）的新聞都被丟進了 world_queue。這一階段的任務就是逐一檢
    #查這些新聞，利用你之前寫的 infer_region 函數，幫它們貼上正確的地區標籤（如「香港」、「美國」、「日本」等）。
    infer_total_count = 0 
    ai_process_count_before = AI_CALL_COUNT
    
    print(f"\n🔍 第二階段：處理 World 來源新聞 (地理位置判定)...")
    final_raw_articles = pre_filtered_articles.copy()

    # --- 在 main() 處理 World 來源的迴圈中 ---
    for art in world_queue:
    # 這裡只負責跑邏輯，不印任何東西
        region = infer_region(art['title'], art['link'], "World", art['source'], art.get('summary'))
        art['region'] = region
        
        infer_total_count += 1
        
        # 直接加入最終列表
        final_raw_articles.append(art)
        
        # 記錄已處理的標題
        confirmed_titles.add(t_clean)
        
        # 保持降溫保護 (若 AI 次數增加，則暫停)
        if AI_CALL_COUNT > ai_process_count_before:
            ai_process_count_before = AI_CALL_COUNT
            time.sleep(0.5)

    # 迴圈結束後印出統計
    print(f"\n📊 第二階段地理位置判定完成：")
    print(f"   - 本次處理總篇數: {infer_total_count} 篇")
    print(f"   - 本次實際調用 AI (Ollama) 次數: {AI_CALL_COUNT} 篇")
    
    
    # 接續後續的深度聚類邏輯...
    raw_articles = final_raw_articles 
    final_report = {} 
    # ... (後面代碼保持不變)
  
    unique_regions = sorted(list(set(a['region'] for a in raw_articles)))  
    
    for reg in unique_regions:
        print(f"\n>>> 正在處理地區: [{reg}]")
        pool = [a for a in raw_articles if a['region'] == reg]
        if not pool: continue

        # --- 新增：硬性標題去重與熱度累加 ---
        title_to_article_map = {}
        for a in pool:
            t_key = a['title'].strip().lower()
            if t_key not in title_to_article_map:
                # 建立新項目，並初始化 references 列表
                a['references'] = [] 
                title_to_article_map[t_key] = a
            else:
                # 標題完全一樣：將此來源加入已存在項目的 references 中
                ref_info = {"source": a['source'], "title": a['title'], "link": a['link']}
                title_to_article_map[t_key]['references'].append(ref_info)

        # 重新組成 pool，現在 pool 裡的每個 element 都是唯一的標題
        pool = list(title_to_article_map.values())
        # --- 結束新增 ---

        # 1. 提取所有標題並轉為向量
        titles = [a['title'] for a in pool]
        embeddings = semantic_model.encode(titles, convert_to_tensor=True)
        
        # 2. 語義聚類 (初步分堆)
        clusters = []
        visited = [False] * len(pool)
        cosine_scores = util.cos_sim(embeddings, embeddings)

        for i in range(len(pool)):
            if visited[i]: continue
            # 尋找相似度大於 0.55 的新聞
            match_indices = [j for j, score in enumerate(cosine_scores[i]) if score > 0.55]
            
            current_cluster = []
            for idx in match_indices:
                if not visited[idx]:
                    current_cluster.append(pool[idx])
                    visited[idx] = True
            
            if current_cluster:
                clusters.append(current_cluster)

        # 3. 按初始規模排序
        clusters.sort(key=lambda x: len(x), reverse=True)

        final_selected_events = []
        global_seen_titles = set() # 地區獨立去重

        # 4. 深度內文比對與跨事件合併
        for cluster in clusters[:20]:
            if len(final_selected_events) >= 15: 
                break
            
            successful_candidates = []
            cluster_titles = set()
            
            print(f"  [評估重要性] (初步權重: {len(cluster)}) 檢查來源中...")

            # --- A. 挑選代表文章 (加入標題去重防止重複抓取) ---
            for candidate in cluster:
                clean_title = candidate['title'].strip()
                # 🔴 這裡就是「標題 100% 碰撞」的攔截點
   				# 如果這個標題在 global_seen_titles（之前的事件）
    			# 或 cluster_titles（當前堆疊內）出現過，就直接跳過不抓取、不處理
                if clean_title in global_seen_titles or clean_title in cluster_titles:
                    continue
                
                content = fetch_content(candidate['link'], candidate['source'])
                if content: # <--- 這裡確保只有抓到 content 的才會進入成功名單
                    candidate['content'] = content
                    successful_candidates.append(candidate)
                    cluster_titles.add(clean_title)
                    if len(content) > 2500: break 
			# 從有正文的名單中，挑選「正文字數最多」的一篇作為代表
            if successful_candidates:
                main_candidate = max(successful_candidates, key=lambda x: len(x['content']))
            else:
            # 如果通通抓不到正文，才會退而求其次用標題最長的
                main_candidate = max(cluster, key=lambda x: len(x['title']))
                if main_candidate['title'].strip() in global_seen_titles:
                    continue
                summ = main_candidate.get('summary', "")
                main_candidate['content'] = f"[摘要備援] {re.sub(r'<[^>]+>', '', summ)}" if summ else main_candidate['title']

            # --- B. 合併判定邏輯 ---
            is_merged = False
            for existing in final_selected_events:
                existing_candidate = existing[0]
                
                # 標題相似度比例
                title_ratio = SequenceMatcher(None, main_candidate['title'], existing_candidate['title']).ratio()
                
                # 三重防禦合併：100%完全一樣 OR 標題 80% 像 OR 內文語義 85% 像
                if (main_candidate['title'].strip() == existing_candidate['title'].strip() or 
                    title_ratio >= 0.8 or 
                    is_content_similar(main_candidate['content'], existing_candidate.get('content', ""), threshold=0.85)):
                    
                    print(f"    └─ 🔗 發現重複事件，合併權重 (新總數: {len(existing) + len(cluster)})")
                    existing.extend(cluster) 
                    is_merged = True
                    break
            
            # --- C. 確立新事件 ---
            if not is_merged:
                final_selected_events.append(cluster)
                global_seen_titles.add(main_candidate['title'].strip())
                print(f"    └─ ✅ 確立核心事件：{main_candidate['title'][:50]}...")

        # 5. 輸出前的「最終排序」：根據合併後的總篇數重新排 Rank
        final_selected_events.sort(key=lambda x: len(x), reverse=True)

        #加入計算總篇數
        total_events = 0
        total_articles_in_json = 0

        for region, events in final_report.items():
            total_events += len(events) # 事件數（聚類後的組數）
            for event in events:
                # 1 (主報導) + 相關報導的數量
                total_articles_in_json += 1 + len(event.get('related_coverage', []))
        
        
        # 6. 準備最終 JSON 輸出
        final_report[reg] = []
        for i, event_cluster in enumerate(final_selected_events):
            # 選取標題最長的報導作為主新聞
            main = max(event_cluster, key=lambda x: len(x['title']))
            
            raw_content = main.get('content')
            if raw_content and len(raw_content) > 150 and "無法提取" not in raw_content:
                final_content = raw_content
            else:
                backup_summary = main.get('summary', "")
                if backup_summary and len(backup_summary) > 30:
                    clean_summary = re.sub(r'<[^>]+>', '', backup_summary)
                    final_content = f"[摘要備援] {clean_summary.strip()}"
                else:
                    final_content = "無法提取有效內容 (請檢查連結)"

            final_report[reg].append({
                "event_rank": i + 1,
                "importance_score": len(event_cluster),
                "main_report": {
                    "source": main['source'], 
                    "title": main['title'], 
                    "link": main['link'], 
                    "content": final_content
                },
                "related_coverage": [
                    {"source": a['source'], "title": a['title'], "link": a['link']} 
                    for a in event_cluster if a['link'] != main['link']
                ],
                "total_sources": len(event_cluster)
            })

    with open("raw_news_full.json", "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)
    # --- 更新你的統計印出部分 ---
    print("\n✅ 全球新聞處理完成！")
    print(f"檔案已儲存至: raw_news_full.json")
    
    print(f"\n📊 效能統計報告：")
    print(f"   - 進入判定邏輯的總篇數: {infer_total_count} 篇")
    print(f"   - 實際調用 AI (Ollama) 次數: {AI_CALL_COUNT} 篇")
    #print(f"   - 最終收錄事件數 (Events): {total_events} 組")
    print(f"   - 最終收錄總報導數 (Articles): {total_articles_in_json} 篇")

if __name__ == "__main__":
    main()