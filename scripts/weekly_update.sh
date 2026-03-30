#!/bin/bash
# 載入環境變數
source ~/.zshrc
# 設定路徑
cd /Users/chihong.wang/Desktop/marketing-tools
echo "=============================="
echo "開始週更新：$(date '+%Y-%m-%d %H:%M')"
echo "=============================="
# 1. 爬蟲
echo "[1/4] 執行 Dcard 爬蟲..."
python3 research-db/dcard_scraper.py
echo "[2/4] 執行社群媒體爬蟲 (Threads/Facebook/Instagram)..."
python3 research-db/social_scraper.py
echo "[3/5] 執行 PTT 爬蟲..."
python3 research-db/ptt_scraper.py
echo "[3.5/5] 執行新聞爬蟲 (Yahoo / LINE Today)..."
python3 research-db/news_scraper.py
echo "[4/5] 執行便利商店&速食品牌活動監測..."
python3 research-db/promo_scraper.py
# 2. 重新產生 Dashboard
echo "[5/5] 重新產生 Dashboard..."
python3 dashboard/build.py
# 3. 推上 GitHub
echo "推送到 GitHub..."
git add docs/index.html
git commit -m "自動更新 $(date '+%Y-%m-%d')"
git push origin main
echo ""
echo "✅ 完成！Dashboard 已更新："
echo "https://ms2black-art.github.io/franchise-monitor"
echo "=============================="
echo "[6/5] 執行拉亞網站智慧更新分析..."
python3 /Users/chihong.wang/Desktop/marketing-tools/laya-website/scripts/smart_update.py
echo "✅ 智慧更新報告已產生，請查看 laya-website/reports/ 資料夾"
