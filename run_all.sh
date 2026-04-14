#!/bin/bash

# 自動偵測 Homebrew 路徑並加入環境變數
if [[ $(uname -m) == "arm64" ]]; then
    # Apple Silicon Mac (你的 Mac mini)
    export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:$PATH"
else
    # Intel Mac
    export PATH="/usr/local/bin:$PATH"
fi

# 檢查指令是否存在（除錯用）
command -v colima >/dev/null 2>&1 || { echo "❌ 找不到 colima 指令"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ 找不到 docker 指令"; exit 1; }

# 1. 設定專案路徑
PROJECT_DIR="/Users/tonywong/Documents/Auto-news-feeding"
# 2. 定義你在 Terminal 測試成功的 Python 絕對路徑
PYTHON_EXEC="/Library/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"

cd "$PROJECT_DIR" || { echo "找不到目錄: $PROJECT_DIR"; exit 1; }


# 定義時間格式化函數 (輸入秒數，輸出 x 分 y 秒)
format_time() {
    local SECONDS=$1
    echo "$((SECONDS / 60)) 分 $((SECONDS % 60)) 秒"
}

# 全域任務開始時間
TOTAL_START=$(date +%s)
echo "==========================================================================================="
echo ""
echo ""
echo "🚀 自動化新聞任務開始: $(date "+%Y-%m-%d %H:%M:%S")"
echo ""
echo ""
echo "==========================================================================================="

# --- [準備階段] 啟動必要服務 ---
echo "⚙️  正在啟動後台服務..."

# --- [準備階段] 啟動必要服務 ---
echo "⚙️  正在啟動後台服務..."

# 1. 啟動 Ollama (如果沒開)
if ! pgrep -x "Ollama" > /dev/null; then
    open -a Ollama
    echo "  ✅ Ollama 已啟動"
    sleep 5
fi

# 2. 啟動 Colima
# 確保徹底關閉 Docker Desktop，這點你做得很好
osascript -e 'quit app "Docker"' > /dev/null 2>&1

if ! colima status > /dev/null 2>&1; then
    echo "  ✅ 正在啟動 Colima 引擎..."
    # 建議加上 --network-address，確保每次都有固定 IP 供後續 Scraper 使用
    colima start --network-address
    # 給 Colima 一點時間初始化 Docker Socket
    sleep 3
fi

# 3. 啟動容器
echo "  🚀 正在啟動 Open WebUI..."
# 使用 docker start 之前，最好先確認容器存在
if [ "$(docker ps -aq -f name=open-webui)" ]; then
    docker start open-webui > /dev/null 2>&1
    # 重要：等待 WebUI 內部服務啟動 (尤其你遷移了大量數據)
    echo "  ⏳ 等待 WebUI 回應..."
    sleep 5
else
    echo "  ❌ 找不到 open-webui 容器，請先建立它。"
    exit 1
fi

# --- [Step 1] ---
# --- [新增階段] 執行 Scrapper 資料夾內的腳本並計時 ---
SCRAPPER_START=$(date +%s)
SCRAPPER_DIR="$PROJECT_DIR/Step1_Scrapper"

if [ -d "$SCRAPPER_DIR" ]; then
    echo "==========================================================================================="
    echo "[Step 1/5] 爬蟲擷取每日新聞..."
    echo "🔍 偵測到 Scrapper 資料夾，開始執行預爬蟲程序..."
    cd "$SCRAPPER_DIR" || exit 1
    
    for script in *.py; do
        if [ -f "$script" ]; then
            echo "  ⏳ 正在執行: $script ..."
            $PYTHON_EXEC -u "$script"
            if [ $? -ne 0 ]; then
                echo "  ❌ $script 執行失敗，停止後續流程。"
                exit 1
            fi
        fi
    done
    echo "  ✅ 所有爬蟲腳本執行完畢。"
    cd "$PROJECT_DIR" || exit 1
else
    echo "⚠️ 找不到 Scrapper 資料夾，跳過此步驟。"
fi

SCRAPPER_DUR=$(($(date +%s) - SCRAPPER_START))
# --------------------------------------------------



# --- [Step 2] ---
S1_START=$(date +%s)
echo ""
echo "[Step 2/5] 從RSS擷取每日新聞..."
$PYTHON_EXEC -u step2_extract_daily_news.py
if [ $? -ne 0 ]; then echo "❌ Step 1 失敗"; exit 1; fi
S1_DUR=$(($(date +%s) - S1_START))

# --- [Step 3] ---
S2_START=$(date +%s)
echo ""
echo "=================================================="
echo "[Step 3/5] 正在進行 AI 分析處理 (Ollama)..."
# 注意：確保 Python 腳本內沒有重複 print "[Step 2/4]"
$PYTHON_EXEC -u step3_ai_process.py
if [ $? -ne 0 ]; then echo "❌ Step 2 失敗"; exit 1; fi
S2_DUR=$(($(date +%s) - S2_START))

# --- [Step 4] ---
S3_START=$(date +%s)
echo ""
echo "=================================================="
echo "[Step 4/5] 正在渲染最終文件 (HTML)..."
$PYTHON_EXEC -u step4_render_paper.py
if [ $? -ne 0 ]; then echo "❌ Step 3 失敗"; exit 1; fi
S3_DUR=$(($(date +%s) - S3_START))

# --- [Step 5] ---
S4_START=$(date +%s)
echo ""
echo "=================================================="
echo "[Step 5/5] 正在自動部署至 GitHub Pages..."
# 這裡建議確保 step4_upload_news.sh 具有執行權限
sh step5_upload_news.sh
if [ $? -ne 0 ]; then echo "❌ Step 4 部署失敗"; exit 1; fi
S4_DUR=$(($(date +%s) - S4_START))

# --- 最終結算 ---
TOTAL_END=$(date +%s)
TOTAL_DUR=$((TOTAL_END - TOTAL_START))

# --- [收尾階段] 釋放資源 ---
echo "🧹 任務完成，正在釋放資源..."

# 停止容器並關閉 Colima
docker stop open-webui > /dev/null 2>&1
# 如果你後續還有其他 Docker 任務，其實不必每次都 stop colima
# 但若為了省電省記憶體，這樣做是可以的
colima stop
echo "  ✅ Colima 已停止"

# 關閉 Ollama
pkill -x "Ollama" > /dev/null 2>&1 # 建議用 -x 精確匹配，避免誤殺

echo "✨ 系統資源已成功回收。"

echo ""
echo "✨ 任務圓滿完成，所有資源已強制回收。"
echo "=================================================="

echo ""
echo "=================================================="
echo "📊 運行效能總結報告"
echo "--------------------------------------------------"
echo "⏱️ Step 1 (爬蟲抓取新聞): $(format_time $SCRAPPER_DUR)"
echo "⏱️ Step 2 (RSS抓取新聞): $(format_time $S1_DUR)"
echo "⏱️ Step 3 (AI 摘要)   :  $(format_time $S2_DUR)"
echo "⏱️ Step 4 (渲染存檔)   : $(format_time $S3_DUR)"
echo "⏱️ Step 5 (部署上傳)   : $(format_time $S4_DUR)"
echo "--------------------------------------------------"
echo "🔔 任務結束時間: $(date "+%H:%M:%S")"
echo "✨ 總共運行耗時: $(format_time $TOTAL_DUR)"
echo "🌐 你的新聞網址: https://Morson46821.github.io/daily_international_news/"
echo "✅ 所有流程已成功完成！"
echo "=================================================="