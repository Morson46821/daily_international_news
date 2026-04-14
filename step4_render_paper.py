import json
from jinja2 import Template
import datetime
import os
import re
from pathlib import Path


def generate_newspaper():
    try:
        with open("final_news_report.json", "r", encoding="utf-8") as f:
            news_data = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到 final_news_report.json！")
        return

    # --- 1. 定義自定義板塊順序 ---
    custom_order = ["香港", "中國", "亞洲", "北美","歐洲", "中東", "非洲", "南美及拉丁美洲", "商業", "科技", "其他"]
    
    ordered_news = {}
    for region in custom_order:
        if region in news_data:
            ordered_news[region] = news_data[region]
    
    for region in news_data:
        if region not in ordered_news:
            ordered_news[region] = news_data[region]

    # --- 2. 數據預處理 ---
    for region in ordered_news:
        ordered_news[region].sort(key=lambda x: x.get("event_rank", 99))
        for item in ordered_news[region]:
            summary = item.get("ai_summary", "")
            title_match = re.search(r"標題：(.*?)(?:\n|$)", summary)
            item["chinese_title"] = title_match.group(1).strip() if title_match else item["primary_source"].get("original_title", "無標題")

            content_body = re.sub(r"標題：.*?\n", "", summary)
            content_body = re.sub(r"^內容：\n?", "", content_body, flags=re.MULTILINE)
            
            raw_lines = content_body.strip().split('\n')
            clean_points = []
            for line in raw_lines:
                text = re.sub(r'^[ \t\u3000•\-\*]+', '', line).strip()
                if text:
                    clean_points.append(text)
            item["bullet_points"] = clean_points

    html_template = """
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;700;900&display=swap" rel="stylesheet">
        <title>全球 AI 智能報章 - {{ date }}</title>
        <style>
            body { font-family: 'Noto Serif TC', serif; background-color: #f4f1ea; color: #1c1917; }
            
            .news-grid { 
                display: grid; 
                grid-template-columns: 1fr; 
                gap: 4rem;
                align-items: start; 
            }
            @media (min-width: 1024px) { .news-grid { grid-template-columns: 1fr 1fr; } }
            
            .tab-content { display: none; animation: fadeIn 0.6s ease; }
            .tab-content.active { display: block; }
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

            .tab-btn { 
                border-bottom: 3px solid transparent; 
                transition: all 0.3s; 
                cursor: pointer;
                font-size: 1.15rem; 
                color: #44403c;
                font-weight: 700;
            }
            .tab-btn:hover { color: #1c1917; }
            .tab-btn.active { 
                border-bottom: 3px solid #991b1b; 
                color: #991b1b; 
                font-weight: 900; 
            }

            .summary-list { list-style-type: none; padding: 0; margin: 0; }
            .summary-list li {
                position: relative;
                padding-left: 1.5rem;
                margin-bottom: 1.2rem;
                line-height: 1.8;
                text-align: justify;
                /* 加大 Summary 字體 */
                font-size: 1.15rem; 
                color: #27272a;
            }
            .summary-list li::before {
                content: "■";
                position: absolute;
                left: 0;
                top: 0.45rem;
                color: #991b1b;
                font-size: 0.7rem;
            }
            
            .source-link {
                word-break: break-all;
                display: block;
                line-height: 1.6;
            }
        </style>
    </head>
    <body class="p-4 md:p-12">
        <div class="max-w-7xl mx-auto bg-white p-8 md:p-20 shadow-2xl border border-stone-200">
            
            <header class="text-center mb-16 border-b-4 border-black pb-8">
                <h1 class="text-6xl md:text-8xl font-black tracking-tighter mb-4 italic">THE AI OBSERVER</h1>
                <div class="flex justify-between items-center text-[10px] font-bold mt-4 uppercase tracking-[0.4em] text-stone-600 border-t border-black pt-4">
                    <span>Edition {{ date_short }}</span>
                    <span class="text-stone-900 text-sm tracking-normal">全 球 智 能 報 章</span>
                    <span>{{ date }}</span>
                </div>
            </header>

            <nav class="flex flex-wrap justify-center gap-x-10 gap-y-6 mb-16 border-b border-stone-200 pb-8">
                {% for region in news.keys() %}
                <button onclick="showRegion('{{ region }}')" id="btn-{{ region }}" 
                        class="tab-btn px-2 py-1 uppercase tracking-widest">
                    {{ region }}
                </button>
                {% endfor %}
            </nav>

            <main>
                {% for region, articles in news.items() %}
                <section id="content-{{ region }}" class="tab-content">
                    <div class="news-grid">
                        {% for item in articles %}
                        <article class="flex flex-col mb-4 last:mb-0">
                            <div class="flex items-center gap-3 mb-6">
                                <span class="bg-red-800 text-white text-[9px] px-2 py-0.5 font-bold uppercase">Ranking #{{ item.event_rank }}</span>
                                <div class="h-[1px] bg-stone-100 flex-grow"></div>
                            </div>
                            
                            <h3 class="text-3xl font-black leading-tight mb-8 text-stone-900 underline decoration-1 underline-offset-8">
                                <a href="{{ item.primary_source.link }}" target="_blank" class="hover:text-red-900 transition-colors">
                                    {{ item.chinese_title }}
                                </a>
                            </h3>

                            <ul class="summary-list mb-8 flex-grow">
                                {% for point in item.bullet_points %}
                                <li>{{ point }}</li>
                                {% endfor %}
                            </ul>

                            <div class="pt-6 border-t border-stone-100 mt-auto">
                                <p class="text-[9px] font-bold text-stone-400 uppercase tracking-widest mb-4">Verification & Sources</p>
                                <div class="space-y-3">
                                    <a href="{{ item.primary_source.link }}" target="_blank" class="source-link text-xs text-blue-900 font-bold hover:underline">
                                        <span class="italic">— {{ item.primary_source.media }}:</span> {{ item.primary_source.original_title }}
                                    </a>
                                    
                                    {% for other in item.other_views %}
                                    <a href="{{ other.link }}" target="_blank" class="source-link text-xs text-blue-900 font-bold hover:underline">
                                        <span class="italic">— {{ other.source }}:</span> {{ other.title }}
                                    </a>
                                    {% endfor %}
                                </div>
                            </div>
                        </article>
                        {% endfor %}
                    </div>
                </section>
                {% endfor %}
            </main>

            <footer class="mt-24 pt-12 border-t-2 border-black text-center text-stone-500">
                <p class="text-[10px] font-bold uppercase tracking-[0.5em]">AI Curation Engine &copy; 2026</p>
            </footer>
        </div>

        <script>
            function showRegion(regionId) {
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
                const content = document.getElementById('content-' + regionId);
                const btn = document.getElementById('btn-' + regionId);
                if(content && btn) { content.classList.add('active'); btn.classList.add('active'); }
                localStorage.setItem('lastRegion', regionId);
            }
            window.onload = function() {
                const regions = [{% for region in news.keys() %}'{{ region }}',{% endfor %}];
                const last = localStorage.getItem('lastRegion');
                showRegion(regions.includes(last) ? last : regions[0]);
            }
        </script>
    </body>
    </html>
    """

    now = datetime.datetime.now()
    template = Template(html_template)
    # 1. 先生成當天日期的字串 (格式: 2024-03-27)
    file_date = now.strftime("%Y-%m-%d")
        
    # 2. 組合完整的檔案名稱
    filename = f"{file_date}-news.html"

    # 3. 使用動態檔案名稱寫入
    # 3.1. 先將渲染好的 HTML 內容存入變數，避免重複運算
    rendered_content = template.render(
        news=ordered_news, 
        date=now.strftime("%Y年%m月%d日"), 
        date_short=now.strftime("%Y%m%d")
    )

    # 3.2. 定義兩個目標路徑
    paths = [
        Path("/Users/tonywong/Documents/Auto-news-feeding") / filename,
        Path("/Users/tonywong/Dropbox/Daily News") / filename
    ]

    # 3.3. 使用迴圈一式兩份寫入
    for target_file in paths:
        try:
            # 自動建立不存在的資料夾（例如 Dropbox 裡的 Daily News）
            target_file.parent.mkdir(parents=True, exist_ok=True)
        
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(rendered_content)
            print(f"✅ 已成功產生日報檔案: {target_file}")
        except Exception as e:
            print(f"❌ 寫入 {target_file} 失敗: {e}")

if __name__ == "__main__":
    generate_newspaper()