import json
import requests
import time

# 設定 Ollama API 地址
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "gemma4:e4b-it-q8_0"  # 確保與你本地模型名稱一致

def summarize_article(title, content, source_count):
    """ 將單條新聞的正文發送給 AI 進行總結，並考慮事件熱度 """
    prompt = f"""
    你是一位專業的國際新聞編輯。請閱讀以下新聞正文，並將其轉化為繁體中文摘要。
    此事件由 {source_count} 家主流媒體同時報導，請確保摘要具備權威性。
    
    【新聞原標題】：{title}
    【新聞正文】：{content[:3000]}

    要求：
    1. 提供一個專業、吸引人的繁體中文標題。
    2. 使用 3 個重點（Bullet Points）概述核心事實。
    3. 語氣嚴謹，字數控制在 120-180 字之間。
    4. 輸出格式：
       標題：[中文標題]
       內容：
       • [重點1]
       • [重點2]
       • [重點3]
    5. 不要輸出任何開場白或解釋。
    """

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2  # 進一步降低隨機性，確保穩定性
                #"num_predict": 250  # 限制 AI 最多只產生 250 個 token，這能大幅提速
            }
        }, timeout=120)
        
        if response.status_code == 200:
            return response.json().get('response', 'AI 未能生成摘要').strip()
        else:
            return f"❌ Ollama API 錯誤 (Status: {response.status_code})"
    except Exception as e:
        return f"🔥 AI 處理異常: {e}"

def main():
    # 1. 讀取更新後的資料結構
    input_file = "raw_news_full.json"
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            all_news_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 找不到 {input_file}，請確認 Step 1 已成功執行！")
        return

    final_report = {}

    # 2. 按地區遍歷 (例如：北美、亞洲...)
    for region, event_clusters in all_news_data.items():
        print(f"\n🌍 正在處理 【{region}】 地區的新聞事件...")
        processed_events = []
        
        for idx, event in enumerate(event_clusters):
            main_info = event['main_report']
            source_count = event['total_sources']
            
            print(f"  [{idx+1}/{len(event_clusters)}] 正在生成摘要: {main_info['title']}...")
            
            # 檢查是否有正文可供總結
            if not main_info['content'] or "⚠️" in main_info['content'] or "❌" in main_info['content']:
                ai_summary = "⚠️ 無法提取正文內容，請點擊連結查看原始報導。"
            else:
                ai_summary = summarize_article(main_info['title'], main_info['content'], source_count)
            
            # 組合處理後的單個事件資料
            processed_events.append({
                "event_rank": event['event_rank'],
                "total_sources": source_count,
                "ai_summary": ai_summary,
                "primary_source": {
                    "media": main_info['source'],
                    "original_title": main_info['title'],
                    "link": main_info['link']
                },
                "other_views": event['related_coverage'] # 保留其他報章連結
            })
            
            # 給本地模型一點喘息時間
            time.sleep(1)
        
        final_report[region] = processed_events

    # 3. 儲存為最終成品資料
    output_file = "final_news_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=4)
    
    print(f"\n✨ 全部處理完成！")
    print(f"💾 最終成品已存至: {output_file}")

if __name__ == "__main__":
    main()