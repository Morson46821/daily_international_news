# 1. 進入資料夾
cd /Users/tonywong/Documents/Auto-news-feeding

# 2. 初始化 Git 倉庫
git init

# 3. 設定隱私郵箱 (保護隱私，用你的虛擬郵箱)
git config user.email "274173466+Morson46821@users.noreply.github.com"
git config user.name "Morson46821"

# 4. 連結到遠端倉庫 (重要：請使用 SSH 格式的網址，不要用 https)
git remote add origin git@github.com:Morson46821/daily_international_news.git

# ---------------------------------------------------------
# 5. 【核心自動化】獲取日期並處理連字號檔名
# $(date +%F) 會生成 2026-04-08
# 這裡我們將檔名設定為 YYYY-MM-DD-news.html
TODAY_FILE="$(date +%F)-news.html"
BACKUP_DIR="Backup"

# 確保 Backup 資料夾存在
mkdir -p "$BACKUP_DIR"

# 檢查檔案是否存在
if [ -f "$TODAY_FILE" ]; then
    echo "✅ 找到今日報章: $TODAY_FILE"
    
    # 複製成 index.html (供首頁使用)
    cp "$TODAY_FILE" index.html
    
    # 將原始檔案移動到 Backup 資料夾
    mv "$TODAY_FILE" "$BACKUP_DIR/"
   
    # 6. 加入 Git 
    # 加入 index.html 以及整個 Backup 資料夾的變更
    git add index.html "$BACKUP_DIR/$TODAY_FILE"
    
    # 7. 提交變更
    git commit -m "Daily Publish: $(date +%F)"
    
    # 8. 推送到 GitHub
    git branch -M main
    git push -u origin main
    
    echo "🚀 發佈成功！"
    echo "首頁網址: https://Morson46821.github.io/daily_international_news/"
    echo "今日存檔: https://Morson46821.github.io/daily_international_news/Backup/$TODAY_FILE"
else
    echo "❌ 錯誤：找不到檔案 $TODAY_FILE"
    echo "請確保你的 Python 腳本生成的檔名格式為：年-月-日-news.html"
fi
# ---------------------------------------------------------