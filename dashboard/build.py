#!/usr/bin/env python3
"""
Dashboard 建置腳本（v2）
讀取 Threads / Facebook / Instagram / 新聞 資料，
正規化 + 情緒分析後內嵌進 docs/index.html。

修改重點：
  - 移除 PTT / Dcard 資料來源
  - 統計改為「當月」計算，隔月歸零
  - 最熱門討論改為一年內
  - 加入活動類 / 口味類分類
  - 品牌競爭儀表板改為當月、聲量來源移除 Dcard/PTT
  - 行銷建議根據討論熱度（留言數）而非單純提及次數

執行方式：
  python3 dashboard/build.py
"""

import json
import glob
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUT_HTML = BASE_DIR / "docs" / "index.html"

# ── 當月計算範圍 ─────────────────────────────────────────────────────────────
NOW = datetime.now()
CURRENT_MONTH_START = NOW.strftime("%Y-%m-01")
ONE_YEAR_AGO = (NOW - timedelta(days=365)).strftime("%Y-%m-%d")

BRANDS = [
    "拉亞", "麥味登", "Q Burger", "弘爺", "晨間廚房", "美而美",
    "美芝城", "萬佳香", "早安公雞", "呷尚寶", "蕃茄村",
]

KEYWORDS = [
    "加盟", "早餐", "創業", "副業", "開店", "連鎖", "餐飲加盟",
    "早午餐", "咖啡加盟", "手搖飲加盟",
    "拉亞", "拉亞漢堡", "拉雅", "Laya", "Laya Burger",
    "麥味登", "Q Burger", "QBurger", "q burger", "qburger",
    "弘爺", "晨間廚房", "美而美",
    "美芝城", "萬佳香", "早安公雞", "呷尚寶", "JSP", "蕃茄村",
    "聯名", "franchise",
]

HOT_KEYWORDS = [
    "加盟", "早餐", "創業", "副業", "開店", "連鎖", "餐飲", "早午餐", "咖啡", "手搖飲",
    "拉亞", "麥味登", "Q Burger", "弘爺", "晨間廚房", "美而美",
    "美芝城", "萬佳香", "早安公雞", "呷尚寶", "蕃茄村",
    "漢堡", "三明治", "蛋餅", "飲料", "外送", "franchise", "展店", "加盟費",
    "保證金", "權利金", "回本", "利潤", "坪數", "人力", "聯名",
]

BRAND_SENTIMENT_TARGETS = ["拉亞", "麥味登", "Q Burger"]

# ── 分類關鍵字 ────────────────────────────────────────────────────────────────
ACTIVITY_KEYWORDS = ["聯名", "限定", "活動", "新品", "上市"]
TASTE_KEYWORDS = ["好吃", "難吃", "推薦", "開箱", "試吃", "口味"]
FRANCHISE_KEYWORDS = ["加盟", "加盟金", "加盟費", "創業", "開店", "展店"]

POSITIVE_KEYWORDS = [
    "推薦", "好吃", "划算", "值得", "優惠", "滿意", "讚", "不錯", "喜歡", "方便",
    "實惠", "超值", "棒", "好用",
    "成功", "賺錢", "獲利", "穩定", "支持", "加盟成功", "展店", "回本", "利潤", "周轉",
    "好喝", "新鮮", "份量足", "CP值高", "服務好", "環境好", "乾淨",
    "人氣", "排隊", "熱門", "暢銷", "口碑", "老顧客", "回頭客",
    "總部支援", "輔導", "培訓完善", "教學", "系統完整", "後勤", "物流穩定",
    "創業成功", "被動收入", "斜槓", "自由", "當老闆",
]

NEGATIVE_KEYWORDS = [
    "難吃", "貴", "失望", "後悔", "差", "爛", "騙", "黑心", "倒閉", "虧", "糟",
    "不值", "避雷", "踩雷", "詐騙",
    "虧損", "賠錢", "撐不下去", "關店", "退出", "違約", "糾紛", "客訴", "抱怨",
    "食材差", "衛生差", "油", "膩", "難下嚥", "份量少", "價格貴",
    "總部不管", "撒手不管", "加盟費過高", "坑", "割韭菜", "剝削",
    "競爭激烈", "難撐", "沒客人", "生意差", "虧本", "撐不住",
    "品質下降", "變難吃", "換料", "偷工減料",
]

STRONG_POSITIVE = ["好吃", "推薦", "必吃", "CP值高", "超值", "回本快", "必點", "口碑"]
STRONG_NEGATIVE = ["踩雷", "難吃", "黑心", "詐騙", "倒閉", "割韭菜", "偷工減料", "虧損"]

# ── 排除平台 ──────────────────────────────────────────────────────────────────
EXCLUDED_PLATFORMS = {"ptt", "dcard"}


# ── 情緒分析 ──────────────────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> str:
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    pos += sum(1 for kw in STRONG_POSITIVE if kw in text)
    neg += sum(1 for kw in STRONG_NEGATIVE if kw in text)
    if pos == 0 and neg == 0:
        return "neutral"
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def add_sentiment(post: dict) -> dict:
    text = post.get("title", "") + " " + post.get("summary", "")
    post["sentiment"] = analyze_sentiment(text)
    return post


def classify_post(post: dict) -> str:
    """分類文章為 活動/口味/加盟/其他"""
    text = post.get("title", "") + " " + post.get("summary", "")
    if any(kw in text for kw in ACTIVITY_KEYWORDS):
        return "活動"
    if any(kw in text for kw in TASTE_KEYWORDS):
        return "口味"
    if any(kw in text for kw in FRANCHISE_KEYWORDS):
        return "加盟"
    return "其他"


# ── 讀取 + 正規化 ─────────────────────────────────────────────────────────────

def load_threads(path: Path) -> list:
    if not path.exists():
        print(f"  ⚠  找不到 {path.name}"); return []
    posts = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(posts, dict):
        posts = posts.get("posts", [])
    return [add_sentiment({
        "title":         (p.get("text") or "")[:60],
        "url":           p.get("url", ""),
        "platform":      "threads",
        "date":          (p.get("created_at") or "")[:10],
        "comment_count": p.get("replies", 0),
        "summary":       (p.get("text") or "")[:150],
        "market":        "台灣",
    }) for p in posts]


def load_facebook(path: Path) -> list:
    if not path.exists():
        print(f"  ⚠  找不到 {path.name}"); return []
    posts = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(posts, dict):
        posts = posts.get("posts", [])
    return [add_sentiment({
        "title":         (p.get("text") or "")[:60],
        "url":           p.get("url", ""),
        "platform":      "facebook",
        "date":          (p.get("created_at") or "")[:10],
        "comment_count": p.get("comments", 0),
        "summary":       (p.get("text") or "")[:150],
        "market":        "台灣",
    }) for p in posts]


def load_news(path: Path) -> list:
    if not path.exists():
        print(f"  ⚠  找不到 {path.name}"); return []
    posts = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(posts, dict):
        posts = posts.get("posts", [])
    return [add_sentiment({
        "title":         p.get("title", ""),
        "url":           p.get("url", ""),
        "platform":      p.get("platform", "news"),
        "date":          (p.get("date") or "")[:10],
        "comment_count": 0,
        "summary":       p.get("summary", ""),
        "market":        p.get("market", "台灣"),
    }) for p in posts]


# ── 活動資料載入 ──────────────────────────────────────────────────────────────

BAD_TITLES = {"skip to main content", "トップページ", ""}
BAD_URL_PREFIXES = ("javascript:", "#", "")

def load_promos() -> list:
    files = sorted(glob.glob(str(DATA_DIR / "promos_*.json")), reverse=True)
    if not files:
        print("  ⚠  找不到 promos_*.json，品牌活動區塊將略過")
        return []
    path = files[0]
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cleaned = []
    for p in raw:
        title = (p.get("title") or "").strip()
        url   = (p.get("url") or "").strip()
        if not title or title.lower() in BAD_TITLES:
            continue
        if len(title) < 3 or len(title) > 100:
            continue
        if any(url.startswith(prefix) for prefix in BAD_URL_PREFIXES if prefix):
            url = ""
        cleaned.append({
            "brand":       p.get("brand", ""),
            "market":      p.get("market", ""),
            "title":       title,
            "description": (p.get("description") or "")[:150],
            "url":         url,
            "image_url":   p.get("image_url", ""),
            "scraped_at":  (p.get("scraped_at") or "")[:10],
        })
    print(f"  ✓  {Path(path).name}  {len(cleaned):>4} 筆活動")
    return cleaned


def load_faq() -> dict:
    files = sorted(glob.glob(str(DATA_DIR / "faq_report_*.json")), reverse=True)
    if not files:
        print("  ⚠  找不到 faq_report_*.json，市場洞察區塊將略過")
        return {}
    path = Path(files[0])
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"  ✓  {path.name}")
    return data


# ── 本月市場洞察產生 ──────────────────────────────────────────────────────────

def generate_monthly_insights(all_posts: list) -> dict:
    """根據當月資料產生市場洞察（取代 FAQ_DATA）"""
    monthly = [p for p in all_posts if p.get("date", "") >= CURRENT_MONTH_START]

    # 各品牌當月統計
    brand_stats = {}
    for brand in BRANDS:
        brand_posts = [p for p in monthly
                       if brand in (p.get("title", "") + " " + p.get("summary", ""))]
        activity_posts = [p for p in brand_posts if classify_post(p) == "活動"]
        taste_posts = [p for p in brand_posts if classify_post(p) == "口味"]
        brand_stats[brand] = {
            "total": len(brand_posts),
            "total_comments": sum(p.get("comment_count", 0) for p in brand_posts),
            "activity_count": len(activity_posts),
            "activity_comments": sum(p.get("comment_count", 0) for p in activity_posts),
            "taste_count": len(taste_posts),
            "taste_comments": sum(p.get("comment_count", 0) for p in taste_posts),
        }

    # Top 3 品牌（依留言數排序）
    top_brands = sorted(brand_stats.items(), key=lambda x: x[1]["total_comments"], reverse=True)[:3]

    # 活動類與口味類總計
    all_activity = [p for p in monthly if classify_post(p) == "活動"]
    all_taste = [p for p in monthly if classify_post(p) == "口味"]

    # 行銷建議（根據留言熱度）
    suggestions = generate_marketing_suggestions(brand_stats, all_activity, all_taste, monthly)

    return {
        "brand_stats": brand_stats,
        "top_brands": top_brands,
        "activity_total": len(all_activity),
        "activity_comments": sum(p.get("comment_count", 0) for p in all_activity),
        "taste_total": len(all_taste),
        "taste_comments": sum(p.get("comment_count", 0) for p in all_taste),
        "suggestions": suggestions,
    }


def generate_marketing_suggestions(brand_stats: dict, activity_posts: list, taste_posts: list, monthly: list) -> list:
    """根據當月各品牌活動/口味類討論數和留言數產生行銷建議"""
    suggestions = []

    # 1. 活動類熱度分析
    if activity_posts:
        total_act_comments = sum(p.get("comment_count", 0) for p in activity_posts)
        suggestions.append(
            f"本月活動類討論共 {len(activity_posts)} 篇、{total_act_comments} 則留言，"
            f"建議加碼聯名/限定活動行銷，搶搭話題流量。"
        )

    # 2. 口味類熱度分析
    if taste_posts:
        total_taste_comments = sum(p.get("comment_count", 0) for p in taste_posts)
        suggestions.append(
            f"本月口味類討論共 {len(taste_posts)} 篇、{total_taste_comments} 則留言，"
            f"建議鼓勵顧客發開箱/試吃文，擴大口碑傳播。"
        )

    # 3. 競品差異分析
    laya = brand_stats.get("拉亞", {})
    competitors = [(b, v) for b, v in brand_stats.items()
                   if b != "拉亞" and v["total_comments"] > laya.get("total_comments", 0)]
    if competitors:
        top_comp = max(competitors, key=lambda x: x[1]["total_comments"])
        suggestions.append(
            f"競品「{top_comp[0]}」本月留言數 {top_comp[1]['total_comments']} 則超越拉亞 {laya.get('total_comments', 0)} 則，"
            f"建議分析其熱門話題並制定對應策略。"
        )
    elif laya.get("total_comments", 0) > 0:
        suggestions.append(
            f"拉亞本月留言數 {laya.get('total_comments', 0)} 則領先競品，建議持續維持話題熱度。"
        )

    # 4. 新品動態
    new_product_posts = [p for p in monthly
                         if any(kw in (p.get("title", "") + " " + p.get("summary", ""))
                                for kw in ["新品", "上市", "限定", "新口味"])]
    if new_product_posts:
        hot_np = max(new_product_posts, key=lambda p: p.get("comment_count", 0))
        suggestions.append(
            f"本月新品話題中「{hot_np.get('title', '')[:20]}」最多留言（{hot_np.get('comment_count', 0)} 則），"
            f"可考慮類似行銷手法。"
        )

    # 5. 補充建議
    if len(suggestions) < 5:
        suggestions.append(
            "建議製作「本月品牌活動懶人包」，彙整各品牌聯名/限定/優惠資訊，"
            "作為社群內容素材，提升互動率。"
        )

    return suggestions[:5]


# ── HTML 生成 ─────────────────────────────────────────────────────────────────

def build_html(all_posts: list, promos: list, faq_data: dict, ig_data: list = None, monthly_insights: dict = None) -> str:
    today_str      = NOW.strftime("%Y 年 %m 月 %d 日")
    month_str      = NOW.strftime("%Y年%m月")
    data_json      = json.dumps(all_posts,    ensure_ascii=False)
    brands_json    = json.dumps(BRANDS,       ensure_ascii=False)
    keywords_json  = json.dumps(KEYWORDS,     ensure_ascii=False)
    hot_kw_json    = json.dumps(HOT_KEYWORDS, ensure_ascii=False)
    bst_json       = json.dumps(BRAND_SENTIMENT_TARGETS, ensure_ascii=False)
    promos_json    = json.dumps(promos,       ensure_ascii=False)
    faq_json       = json.dumps(faq_data,     ensure_ascii=False)
    ig_json        = json.dumps(ig_data or [], ensure_ascii=False)
    insights_json  = json.dumps(monthly_insights or {}, ensure_ascii=False)
    month_start_json = json.dumps(CURRENT_MONTH_START)
    one_year_ago_json = json.dumps(ONE_YEAR_AGO)

    keywords_str = "・".join(KEYWORDS)

    pos = sum(1 for p in all_posts if p["sentiment"] == "positive")
    neg = sum(1 for p in all_posts if p["sentiment"] == "negative")
    neu = len(all_posts) - pos - neg
    print(f"  → 情緒：正面 {pos} 篇 / 中性 {neu} 篇 / 負面 {neg} 篇")

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>加盟品牌監測 Dashboard</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
  <script>
    const ALL_POSTS               = {data_json};
    const BRANDS                  = {brands_json};
    const KEYWORDS                = {keywords_json};
    const HOT_KEYWORDS            = {hot_kw_json};
    const BRAND_SENTIMENT_TARGETS = {bst_json};
    const PROMOS_DATA             = {promos_json};
    const FAQ_DATA                = {faq_json};
    const INSTAGRAM_DATA          = {ig_json};
    const MONTHLY_INSIGHTS        = {insights_json};
    const MONTH_START             = {month_start_json};
    const ONE_YEAR_AGO            = {one_year_ago_json};
    // 分類關鍵字
    const ACTIVITY_KW = ['聯名','限定','活動','新品','上市'];
    const TASTE_KW    = ['好吃','難吃','推薦','開箱','試吃','口味'];
    const FRANCHISE_KW = ['加盟','加盟金','加盟費','創業','開店','展店'];
    function classifyPost(p) {{
      const text = (p.title||'') + ' ' + (p.summary||'');
      if (ACTIVITY_KW.some(kw => text.includes(kw))) return '活動';
      if (TASTE_KW.some(kw => text.includes(kw))) return '口味';
      if (FRANCHISE_KW.some(kw => text.includes(kw))) return '加盟';
      return '其他';
    }}
    // 當月文章
    const monthlyPosts = ALL_POSTS.filter(p => p.date && p.date >= MONTH_START);
    // 一年內文章
    const yearlyPosts = ALL_POSTS.filter(p => p.date && p.date >= ONE_YEAR_AGO);
  </script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:       #F1F5F9;
      --card:     #FFFFFF;
      --border:   #E2E8F0;
      --text:     #0F172A;
      --muted:    #64748B;
      --radius:   12px;
      --shadow:   0 1px 3px rgba(0,0,0,.08);
      --threads:    #7C3AED;
      --facebook:   #1877F2;
      --yahoo_news: #6001D2;
      --line_today: #06C755;
      --yahoo_jp:   #FF0033;
      --tw_rss:     #E40012;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif;
      background: var(--bg); color: var(--text); min-height: 100vh;
    }}
    header {{
      background: var(--card); border-bottom: 1px solid var(--border);
      padding: 0 24px; height: 60px;
      display: flex; align-items: center; justify-content: space-between;
      position: sticky; top: 0; z-index: 10;
    }}
    header h1 {{ font-size: 18px; font-weight: 700; letter-spacing: -.3px; }}
    header .date {{ font-size: 13px; color: var(--muted); }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}

    /* ── Stat Cards ── */
    .stats {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 24px; }}
    @media (max-width:700px) {{ .stats {{ grid-template-columns: repeat(2,1fr); }} }}
    .card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow);
    }}
    .card .label  {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
    .card .value  {{ font-size: 32px; font-weight: 700; line-height: 1; }}
    .card .sublabel {{
      font-size: 11px; color: var(--muted); margin-top: 8px;
      line-height: 1.6; word-break: break-all;
    }}

    /* ── Chart Cards ── */
    .charts {{ display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 24px; }}
    @media (max-width:700px) {{ .charts {{ grid-template-columns: 1fr; }} }}
    .chart-card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow);
    }}
    .chart-card h2 {{
      font-size: 13px; font-weight: 600; margin-bottom: 16px;
      color: var(--muted); text-transform: uppercase; letter-spacing: .5px;
    }}
    .chart-card canvas {{ max-height: 260px; }}

    /* ── Section Title ── */
    .section-title {{
      font-size: 13px; font-weight: 600; color: var(--muted);
      text-transform: uppercase; letter-spacing: .5px; margin-bottom: 12px;
    }}

    /* ── Sentiment Row ── */
    .sentiment-row {{
      display: grid; grid-template-columns: 1fr 1fr 1fr auto;
      gap: 16px; align-items: start; margin-bottom: 24px;
    }}
    @media (max-width:800px) {{ .sentiment-row {{ grid-template-columns: 1fr 1fr; }} }}
    .sentiment-card {{
      border-radius: var(--radius); padding: 20px;
      box-shadow: var(--shadow); color: #fff;
    }}
    .sentiment-card.positive {{ background: #16A34A; }}
    .sentiment-card.neutral  {{ background: #64748B; }}
    .sentiment-card.negative {{ background: #DC2626; }}
    .sentiment-card .s-label {{ font-size: 12px; opacity: .85; margin-bottom: 6px; }}
    .sentiment-card .s-value {{ font-size: 28px; font-weight: 700; }}
    .sentiment-card .s-pct   {{ font-size: 13px; opacity: .8; margin-top: 2px; }}
    .sentiment-pie {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow);
      min-width: 200px;
    }}
    .sentiment-pie h2 {{
      font-size: 13px; font-weight: 600; margin-bottom: 12px;
      color: var(--muted); text-transform: uppercase; letter-spacing: .5px;
    }}
    .sentiment-pie canvas {{ max-height: 200px; }}

    /* ── Brand Sentiment ── */
    .brand-sentiment-grid {{
      display: grid; grid-template-columns: repeat(3,1fr);
      gap: 16px; margin-bottom: 24px;
    }}
    @media (max-width:700px) {{ .brand-sentiment-grid {{ grid-template-columns: 1fr; }} }}
    .brand-sent-card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow);
    }}
    .brand-sent-card h3 {{ font-size: 15px; font-weight: 700; margin-bottom: 4px; }}
    .brand-sent-card .brand-total {{ font-size: 12px; color: var(--muted); margin-bottom: 14px; }}
    .brand-sent-card canvas {{ max-height: 80px; }}

    /* ── Dual Feed Layout ── */
    .dual-feed {{
      display: grid; grid-template-columns: 1fr 1fr 1fr;
      gap: 16px; margin-bottom: 24px;
    }}
    @media (max-width: 900px) {{ .dual-feed {{ grid-template-columns: 1fr 1fr; }} }}
    @media (max-width: 600px) {{ .dual-feed {{ grid-template-columns: 1fr; }} }}
    .feed-panel {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); box-shadow: var(--shadow);
      display: flex; flex-direction: column; min-height: 0; min-width: 0;
      overflow: hidden;
    }}
    .feed-header {{
      padding: 14px 16px 12px;
      border-bottom: 1px solid var(--border);
      display: flex; align-items: center; justify-content: space-between;
      flex-shrink: 0;
    }}
    .feed-header h2 {{ font-size: 14px; font-weight: 700; }}
    .feed-more {{
      font-size: 12px; color: var(--muted);
      text-decoration: none; white-space: nowrap;
    }}

    /* ── Article List ── */
    .article-list {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden;
    }}
    .article-item {{
      display: flex; align-items: flex-start; gap: 12px;
      padding: 12px 16px; border-bottom: 1px solid var(--border);
      text-decoration: none; color: inherit; transition: background .15s;
    }}
    .article-item:last-child {{ border-bottom: none; }}
    .article-item:hover {{ background: var(--bg); }}
    .tag {{
      flex-shrink: 0; font-size: 11px; font-weight: 600;
      padding: 2px 8px; border-radius: 20px; color: #fff; margin-top: 2px;
    }}
    .tag-threads    {{ background: var(--threads); }}
    .tag-facebook   {{ background: var(--facebook); }}
    .tag-yahoo_news {{ background: var(--yahoo_news); }}
    .tag-line_today {{ background: var(--line_today); }}
    .tag-yahoo_jp   {{ background: var(--yahoo_jp); }}
    .tag-tw_rss     {{ background: var(--tw_rss); }}
    .tag-cat {{ background: #F59E0B; font-size: 10px; padding: 1px 6px; }}
    .article-body {{ flex: 1; min-width: 0; }}
    .article-title {{ font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .article-meta  {{ font-size: 12px; color: var(--muted); margin-top: 3px; display: flex; align-items: center; gap: 6px; }}
    .sentiment-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; display: inline-block; }}
    .sentiment-dot.positive {{ background: #16A34A; }}
    .sentiment-dot.neutral  {{ background: #94A3B8; }}
    .sentiment-dot.negative {{ background: #DC2626; }}

    /* ── Brand Competition Dashboard ── */
    .brand-competition-grid {{
      display: grid; grid-template-columns: repeat(3,1fr);
      gap: 20px; margin-bottom: 32px;
    }}
    @media (max-width: 900px) {{ .brand-competition-grid {{ grid-template-columns: 1fr; }} }}
    .brand-comp-card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .bcc-header {{
      padding: 16px 20px 14px;
      border-bottom: 1px solid var(--border);
      display: flex; align-items: flex-start; justify-content: space-between;
    }}
    .bcc-brand {{ font-size: 18px; font-weight: 800; }}
    .bcc-total {{ font-size: 40px; font-weight: 900; line-height: 1; }}
    .bcc-total-label {{ font-size: 11px; color: var(--muted); margin-top: 2px; }}
    .bcc-section {{ padding: 12px 20px; border-bottom: 1px solid var(--border); }}
    .bcc-section:last-child {{ border-bottom: none; }}
    .bcc-section-title {{ font-size: 12px; font-weight: 700; color: var(--muted); margin-bottom: 8px; }}
    .bcc-sources {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .bcc-source-badge {{
      font-size: 12px; font-weight: 600; padding: 3px 10px;
      border-radius: 20px; background: var(--bg);
      border: 1px solid var(--border);
    }}
    .thermometer-bar {{
      height: 16px; border-radius: 8px; overflow: hidden;
      display: flex; margin-bottom: 6px;
    }}
    .thermo-pos {{ background: #16A34A; height: 100%; }}
    .thermo-neu {{ background: #94A3B8; height: 100%; }}
    .thermo-neg {{ background: #DC2626; height: 100%; }}
    .thermo-labels {{ display: flex; justify-content: space-between; }}
    .thermo-label {{ font-size: 11px; font-weight: 600; }}
    .thermo-label.pos {{ color: #16A34A; }}
    .thermo-label.neu {{ color: #94A3B8; }}
    .thermo-label.neg {{ color: #DC2626; }}
    .topic-cloud {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
    .topic-chip {{ border-radius: 20px; font-weight: 700; padding: 3px 10px; cursor: default; }}
    .bcc-article-title {{
      font-size: 13px; font-weight: 600; line-height: 1.4;
      display: -webkit-box; -webkit-line-clamp: 2;
      -webkit-box-orient: vertical; overflow: hidden;
      color: inherit; text-decoration: none;
    }}
    .bcc-article-title:hover {{ text-decoration: underline; }}
    .bcc-article-meta {{ font-size: 11px; color: var(--muted); margin-top: 3px; }}
    .sparkline-wrap {{ height: 50px; }}
    .bcc-hot-list {{ display: flex; flex-direction: column; gap: 6px; }}
    .bcc-hot-item {{ display: flex; align-items: flex-start; gap: 8px; }}
    .bcc-hot-rank {{
      flex-shrink: 0; font-size: 13px; font-weight: 900;
      width: 18px; text-align: center; line-height: 1.5;
    }}
    .bcc-hot-body {{ flex: 1; min-width: 0; }}

    /* ── Market Insights ── */
    .insight-block {{
      background: #FFF4E8; border: 1px solid #FDDCB5;
      border-radius: var(--radius); padding: 24px;
      margin-bottom: 24px; box-shadow: var(--shadow);
    }}
    .insight-block .insight-title {{
      font-size: 16px; font-weight: 800; color: #7C3C00;
      margin-bottom: 20px; display: flex; align-items: center; gap: 8px;
    }}
    .insight-section {{ margin-bottom: 24px; }}
    .insight-section:last-child {{ margin-bottom: 0; }}
    .insight-section-label {{
      font-size: 12px; font-weight: 700; color: #A0522D;
      text-transform: uppercase; letter-spacing: .5px; margin-bottom: 12px;
    }}
    .topic-list {{ display: flex; flex-direction: column; gap: 8px; }}
    .topic-row {{ display: flex; align-items: center; gap: 10px; }}
    .topic-tag {{
      flex-shrink: 0; background: #F97316; color: #fff;
      font-size: 12px; font-weight: 700; padding: 3px 10px;
      border-radius: 20px; min-width: 64px; text-align: center;
    }}
    .topic-bar-wrap {{ flex: 1; background: #FFE5CC; border-radius: 4px; height: 10px; overflow: hidden; }}
    .topic-bar {{ background: #F97316; height: 100%; border-radius: 4px; transition: width .4s; }}
    .topic-count {{ font-size: 12px; color: #A0522D; font-weight: 600; min-width: 36px; text-align: right; }}
    .brand-top-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    @media (max-width: 700px) {{ .brand-top-grid {{ grid-template-columns: 1fr; }} }}
    .brand-top-card {{
      background: #fff; border: 1px solid #FDDCB5;
      border-radius: 10px; padding: 14px 16px;
    }}
    .brand-top-card .btc-name {{ font-size: 15px; font-weight: 800; color: #7C3C00; margin-bottom: 4px; }}
    .brand-top-card .btc-total {{ font-size: 12px; color: #A0522D; margin-bottom: 10px; }}
    .btc-bar-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
    .btc-bar-row .btc-label {{ font-size: 11px; color: #64748B; width: 50px; flex-shrink: 0; }}
    .btc-bar-wrap {{ flex: 1; background: #F1F5F9; border-radius: 4px; height: 8px; overflow: hidden; }}
    .btc-bar.pos {{ background: #16A34A; height: 100%; border-radius: 4px; }}
    .btc-bar.neg {{ background: #DC2626; height: 100%; border-radius: 4px; }}
    .btc-bar.activity {{ background: #F59E0B; height: 100%; border-radius: 4px; }}
    .btc-bar.taste {{ background: #EC4899; height: 100%; border-radius: 4px; }}
    .btc-bar-row .btc-n {{ font-size: 11px; color: #64748B; min-width: 20px; text-align: right; }}
    .suggestion-list {{ display: flex; flex-direction: column; gap: 10px; }}
    .suggestion-card {{
      background: #fff; border: 1px solid #FDDCB5;
      border-radius: 10px; padding: 14px 16px;
      display: flex; align-items: flex-start; gap: 12px;
    }}
    .suggestion-card .sug-num {{
      flex-shrink: 0; background: #F97316; color: #fff;
      font-size: 12px; font-weight: 800; width: 24px; height: 24px;
      border-radius: 50%; display: flex; align-items: center; justify-content: center;
    }}
    .suggestion-card .sug-text {{ font-size: 13px; color: #3C1F00; line-height: 1.6; }}
  </style>
</head>
<body>
  <header>
    <h1>加盟品牌監測 Dashboard</h1>
    <span class="date">{today_str}</span>
  </header>
  <main>

    <!-- ── Stats ── -->
    <div class="stats">
      <div class="card">
        <div class="label">本月文章數</div>
        <div class="value" id="stat-total">—</div>
      </div>
      <div class="card">
        <div class="label">平台數</div>
        <div class="value" id="stat-platforms">—</div>
        <div class="sublabel">Threads・Facebook・Yahoo新聞・LINE Today</div>
      </div>
      <div class="card">
        <div class="label">監測品牌</div>
        <div class="value" id="stat-brands">—</div>
        <div class="sublabel">拉亞・麥味登・Q Burger・弘爺・晨間廚房・美而美・美芝城・萬佳香・早安公雞・呷尚寶・蕃茄村</div>
      </div>
      <div class="card">
        <div class="label">關鍵字</div>
        <div class="value" id="stat-keywords">—</div>
        <div class="sublabel">{keywords_str}</div>
      </div>
    </div>

    <!-- ── Brand & Platform Charts ── -->
    <div class="charts">
      <div class="chart-card">
        <h2>本月品牌提及次數</h2>
        <canvas id="chartBrands"></canvas>
      </div>
      <div class="chart-card">
        <h2>平台分佈</h2>
        <canvas id="chartPlatform"></canvas>
      </div>
    </div>

    <!-- ── Monthly Market Insights ── -->
    <div class="insight-block" id="insightBlock">
      <div class="insight-title">📊 本月市場洞察</div>

      <div class="insight-section">
        <div class="insight-section-label">🔥 品牌討論熱度（依留言數排序）</div>
        <div class="brand-top-grid" id="insightBrands"></div>
      </div>

      <div class="insight-section">
        <div class="insight-section-label">📂 活動類 vs 口味類討論</div>
        <div class="topic-list" id="insightCategories"></div>
      </div>

      <div class="insight-section">
        <div class="insight-section-label">💡 本月行銷建議</div>
        <div class="suggestion-list" id="insightSuggestions"></div>
      </div>
    </div>

    <!-- ── Sentiment Overview（當月）── -->
    <div class="section-title">本月整體情緒分析</div>
    <div class="sentiment-row">
      <div class="sentiment-card positive">
        <div class="s-label">正面</div>
        <div class="s-value" id="sent-pos">—</div>
        <div class="s-pct"  id="sent-pos-pct">—</div>
      </div>
      <div class="sentiment-card neutral">
        <div class="s-label">中性</div>
        <div class="s-value" id="sent-neu">—</div>
        <div class="s-pct"  id="sent-neu-pct">—</div>
      </div>
      <div class="sentiment-card negative">
        <div class="s-label">負面</div>
        <div class="s-value" id="sent-neg">—</div>
        <div class="s-pct"  id="sent-neg-pct">—</div>
      </div>
      <div class="sentiment-pie">
        <h2>情緒比例</h2>
        <canvas id="chartSentiment"></canvas>
      </div>
    </div>

    <!-- ── Brand Sentiment（當月）── -->
    <div class="section-title">本月品牌情緒分析</div>
    <div class="brand-sentiment-grid" id="brandSentimentGrid"></div>

    <!-- ── Hot Keywords（當月）── -->
    <div class="section-title" style="margin-top:8px">本月關鍵字熱度</div>
    <div class="chart-card" style="margin-bottom:24px">
      <h2>本月關鍵字出現次數（前 20）</h2>
      <canvas id="chartHotKw" style="max-height:400px"></canvas>
    </div>

    <!-- ── Dual Feed ── -->
    <div class="dual-feed">
      <div class="feed-panel">
        <div class="feed-header">
          <h2>🔥 最熱門討論</h2>
          <span class="feed-more">一年內 · Threads・Facebook</span>
        </div>
        <div class="article-list" id="hotDiscussion"></div>
      </div>
      <div class="feed-panel">
        <div class="feed-header">
          <h2>📰 本月台灣品牌新聞</h2>
          <span class="feed-more">Yahoo 奇摩・LINE Today</span>
        </div>
        <div class="article-list" id="hotNewsTW"></div>
      </div>
      <div class="feed-panel">
        <div class="feed-header">
          <h2>🗾 本月日本品牌新聞</h2>
          <span class="feed-more">Yahoo Japan</span>
        </div>
        <div class="article-list" id="hotNewsJP"></div>
      </div>
    </div>

    <!-- ── Brand Competition Dashboard ── -->
    <div class="section-title">🏆 拉亞 vs 麥味登 vs Q Burger 本月品牌競爭儀表板</div>
    <div class="brand-competition-grid" id="brandCompGrid"></div>

  </main>
  <script>
    // ── 工具 ─────────────────────────────────────────────────────────────────
    function countMentions(posts, kw) {{
      return posts.filter(p => (p.title + ' ' + p.summary).includes(kw)).length;
    }}
    function countOccurrences(posts, kw) {{
      let n = 0;
      posts.forEach(p => {{
        const text = p.title + ' ' + p.summary;
        let pos = 0;
        while ((pos = text.indexOf(kw, pos)) !== -1) {{ n++; pos += kw.length; }}
      }});
      return n;
    }}
    function platformLabel(p) {{
      return {{
        threads:'Threads', facebook:'Facebook',
        yahoo_news:'Yahoo新聞', line_today:'LINE Today', yahoo_jp:'Yahoo JP',
        tw_rss:'台灣新聞',
      }}[p] || p;
    }}
    function pct(n, total) {{
      return total ? (n / total * 100).toFixed(1) + '%' : '0%';
    }}

    // ── Stats（當月）─────────────────────────────────────────────────────────
    const platformSet = new Set(monthlyPosts.map(p => p.platform));
    document.getElementById('stat-total').textContent     = monthlyPosts.length.toLocaleString();
    document.getElementById('stat-platforms').textContent = platformSet.size;
    document.getElementById('stat-brands').textContent    = BRANDS.length;
    document.getElementById('stat-keywords').textContent  = KEYWORDS.length;

    // ── 本月品牌提及橫條圖 ────────────────────────────────────────────────────
    new Chart(document.getElementById('chartBrands'), {{
      type: 'bar',
      data: {{
        labels: BRANDS,
        datasets: [{{
          data: BRANDS.map(b => countMentions(monthlyPosts, b)),
          backgroundColor: [
            '#3B82F6','#8B5CF6','#EC4899','#F59E0B','#10B981','#EF4444',
            '#14B8A6','#F97316','#A855F7','#EAB308','#64748B',
          ],
          borderRadius: 6,
        }}],
      }},
      options: {{
        indexAxis: 'y',
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ grid: {{ color: '#F1F5F9' }} }}, y: {{ grid: {{ display: false }} }} }},
      }},
    }});

    // ── 平台分佈圓餅圖（當月）────────────────────────────────────────────────
    const platformOrder  = ['threads','facebook','yahoo_news','line_today','tw_rss','yahoo_jp'];
    const platformColors = {{
      threads:'#7C3AED', facebook:'#1877F2',
      yahoo_news:'#6001D2', line_today:'#06C755', yahoo_jp:'#FF0033', tw_rss:'#E40012',
    }};
    const platformCounts = {{}};
    monthlyPosts.forEach(p => {{ platformCounts[p.platform] = (platformCounts[p.platform]||0) + 1; }});
    new Chart(document.getElementById('chartPlatform'), {{
      type: 'doughnut',
      data: {{
        labels: platformOrder.map(platformLabel),
        datasets: [{{
          data: platformOrder.map(p => platformCounts[p]||0),
          backgroundColor: platformOrder.map(p => platformColors[p]),
          borderWidth: 2, borderColor: '#fff',
        }}],
      }},
      options: {{
        plugins: {{ legend: {{ position:'bottom', labels: {{ padding:16, font:{{ size:12 }} }} }} }},
        cutout: '60%',
      }},
    }});

    // ── 整體情緒統計（當月）──────────────────────────────────────────────────
    const sentCounts = {{ positive:0, neutral:0, negative:0 }};
    monthlyPosts.forEach(p => {{ sentCounts[p.sentiment] = (sentCounts[p.sentiment]||0) + 1; }});
    const total = monthlyPosts.length;
    document.getElementById('sent-pos').textContent     = sentCounts.positive;
    document.getElementById('sent-neu').textContent     = sentCounts.neutral;
    document.getElementById('sent-neg').textContent     = sentCounts.negative;
    document.getElementById('sent-pos-pct').textContent = pct(sentCounts.positive, total);
    document.getElementById('sent-neu-pct').textContent = pct(sentCounts.neutral,  total);
    document.getElementById('sent-neg-pct').textContent = pct(sentCounts.negative, total);
    new Chart(document.getElementById('chartSentiment'), {{
      type: 'doughnut',
      data: {{
        labels: ['正面','中性','負面'],
        datasets: [{{
          data: [sentCounts.positive, sentCounts.neutral, sentCounts.negative],
          backgroundColor: ['#16A34A','#94A3B8','#DC2626'],
          borderWidth: 2, borderColor: '#fff',
        }}],
      }},
      options: {{
        plugins: {{ legend: {{ position:'bottom', labels: {{ padding:12, font:{{ size:11 }} }} }} }},
        cutout: '55%',
      }},
    }});

    // ── 品牌情緒分析（當月）──────────────────────────────────────────────────
    const grid = document.getElementById('brandSentimentGrid');
    BRAND_SENTIMENT_TARGETS.forEach((brand, idx) => {{
      const related = monthlyPosts.filter(p => (p.title + ' ' + p.summary).includes(brand));
      const bp = related.filter(p => p.sentiment === 'positive').length;
      const bn = related.filter(p => p.sentiment === 'negative').length;
      const bnu = related.length - bp - bn;
      const card = document.createElement('div');
      card.className = 'brand-sent-card';
      const canvasId = `chartBrandSent${{idx}}`;
      card.innerHTML = `
        <h3>${{brand}}</h3>
        <div class="brand-total">本月共 ${{related.length}} 篇相關文章</div>
        <canvas id="${{canvasId}}"></canvas>`;
      grid.appendChild(card);
      new Chart(document.getElementById(canvasId), {{
        type: 'bar',
        data: {{
          labels: ['正面','中性','負面'],
          datasets: [{{
            data: [bp, bnu, bn],
            backgroundColor: ['#16A34A','#94A3B8','#DC2626'],
            borderRadius: 4,
          }}],
        }},
        options: {{
          indexAxis: 'y',
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ grid: {{ color:'#F1F5F9' }}, ticks: {{ font: {{ size:11 }} }} }},
            y: {{ grid: {{ display: false }}, ticks: {{ font: {{ size:11 }} }} }},
          }},
        }},
      }});
    }});

    // ── 本月關鍵字熱度排行 ────────────────────────────────────────────────────
    const kwCounts = HOT_KEYWORDS.map(kw => ({{ kw, n: countOccurrences(monthlyPosts, kw) }}));
    kwCounts.sort((a, b) => b.n - a.n);
    const top20 = kwCounts.slice(0, 20);
    new Chart(document.getElementById('chartHotKw'), {{
      type: 'bar',
      data: {{
        labels: top20.map(x => x.kw),
        datasets: [{{
          data: top20.map(x => x.n),
          backgroundColor: '#0EA5E9',
          borderRadius: 5,
        }}],
      }},
      options: {{
        indexAxis: 'y',
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ grid: {{ color:'#F1F5F9' }} }},
          y: {{ grid: {{ display: false }} }},
        }},
      }},
    }});

    // ── 🔥 最熱門討論（一年內 · Threads / Facebook）────────────────────────
    const SOCIAL_PLATFORMS = new Set(['threads','facebook']);
    const hotDiscPosts = [...yearlyPosts]
      .filter(p => SOCIAL_PLATFORMS.has(p.platform) && p.date)
      .sort((a, b) => (b.comment_count ?? 0) - (a.comment_count ?? 0))
      .slice(0, 30);
    const discList = document.getElementById('hotDiscussion');
    if (hotDiscPosts.length === 0) {{
      discList.innerHTML = '<div style="padding:20px 16px;color:var(--muted);font-size:13px">尚無資料</div>';
    }} else {{
      hotDiscPosts.forEach(p => {{
        const cat = classifyPost(p);
        const catTag = cat !== '其他' ? `<span class="tag tag-cat">${{cat}}</span>` : '';
        const a = document.createElement('a');
        a.className = 'article-item';
        a.href = p.url || '#';
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.innerHTML = `
          <span class="tag tag-${{p.platform}}">${{platformLabel(p.platform)}}</span>
          ${{catTag}}
          <div class="article-body">
            <div class="article-title">${{p.title || p.summary || '（無標題）'}}</div>
            <div class="article-meta">
              <span class="sentiment-dot ${{p.sentiment}}"></span>
              ${{p.date}}&ensp;·&ensp;💬 ${{p.comment_count ?? 0}}
            </div>
          </div>`;
        discList.appendChild(a);
      }});
    }}

    // ── 📰 本月台灣品牌新聞 ───────────────────────────────────────────────────
    function renderNewsFeed(containerId, posts, emptyMsg) {{
      const el = document.getElementById(containerId);
      if (posts.length === 0) {{
        el.innerHTML = `<div style="padding:20px 16px;color:var(--muted);font-size:13px">${{emptyMsg || '尚無資料'}}</div>`;
        return;
      }}
      posts.forEach(p => {{
        const a = document.createElement('a');
        a.className = 'article-item';
        a.href = p.url || '#';
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.innerHTML = `
          <span class="tag tag-${{p.platform}}">${{platformLabel(p.platform)}}</span>
          <div class="article-body">
            <div class="article-title">${{p.title || '（無標題）'}}</div>
            <div class="article-meta">${{p.date}}</div>
          </div>`;
        el.appendChild(a);
      }});
    }}

    const TW_NEWS_PLATFORMS = new Set(['yahoo_news','line_today','tw_rss']);
    const twNewsPosts = [...monthlyPosts]
      .filter(p => TW_NEWS_PLATFORMS.has(p.platform) && p.market === '台灣' && p.date)
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 30);
    renderNewsFeed('hotNewsTW', twNewsPosts, '本月暫無新聞');

    // ── 🗾 本月日本品牌新聞 ───────────────────────────────────────────────────
    const jpNewsPosts = [...monthlyPosts]
      .filter(p => p.platform === 'yahoo_jp' && p.market === '日本' && p.date)
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 30);
    renderNewsFeed('hotNewsJP', jpNewsPosts, '本月暫無新聞');

    // ── 品牌競爭儀表板（當月）────────────────────────────────────────────────────
    (function() {{
      const BRAND_COLORS = {{
        '拉亞':     '#E8591A',
        '麥味登':   '#1A6BE8',
        'Q Burger': '#1AE85E',
      }};
      const BRAND_MATCH = {{
        '拉亞':     p => {{ const t = (p.title||'') + ' ' + (p.summary||'');
                           return t.includes('拉亞') || t.includes('Laya') || t.includes('laya'); }},
        '麥味登':   p => {{ const t = (p.title||'') + ' ' + (p.summary||'');
                           return t.includes('麥味登'); }},
        'Q Burger': p => {{ const t = (p.title||'') + ' ' + (p.summary||'');
                           return t.includes('Q Burger') || t.includes('QBurger') ||
                                  t.includes('q burger') || t.includes('qburger'); }},
      }};
      const BRAND_TITLE_KWS = {{
        '拉亞':     ['拉亞', 'Laya', 'laya'],
        '麥味登':   ['麥味登'],
        'Q Burger': ['Q Burger', 'QBurger', 'q burger', 'qburger'],
      }};
      const NEWS_PLATS_COMP = new Set(['yahoo_news','line_today','tw_rss']);
      const NEW_PRODUCT_KW  = ['新品','限定','上市','聯名','新口味','新菜單','新推出'];
      const igTags = INSTAGRAM_DATA || [];
      const igBrandKws = {{
        '拉亞':     ['拉亞', 'laya'],
        '麥味登':   ['麥味登'],
        'Q Burger': ['qburger'],
      }};
      function getIgCount(brand) {{
        const kws = igBrandKws[brand] || [];
        return igTags
          .filter(t => kws.some(kw =>
            (t.tag_name||'').toLowerCase().includes(kw.toLowerCase()) ||
            (t.searched_keyword||'').toLowerCase().includes(kw.toLowerCase())
          ))
          .reduce((sum, t) => sum + (t.media_count || 0), 0);
      }}
      function fmtNum(n) {{
        if (n >= 10000) return (n / 10000).toFixed(1) + '萬';
        if (n >= 1000)  return (n / 1000).toFixed(1) + 'K';
        return String(n);
      }}

      const compGrid = document.getElementById('brandCompGrid');
      Object.entries(BRAND_COLORS).forEach(([brand, color], idx) => {{
        const matchFn   = BRAND_MATCH[brand];
        const titleKws  = BRAND_TITLE_KWS[brand];
        // 當月文章
        const brandPosts = monthlyPosts.filter(matchFn);
        // 聲量來源（移除 Dcard/PTT）
        const src = {{ threads:0, facebook:0, news:0 }};
        brandPosts.forEach(p => {{
          if      (p.platform === 'threads')  src.threads++;
          else if (p.platform === 'facebook') src.facebook++;
          else if (NEWS_PLATS_COMP.has(p.platform)) src.news++;
        }});
        const igCnt = getIgCount(brand);
        // 情緒溫度計（當月）
        const sPos = brandPosts.filter(p => p.sentiment === 'positive').length;
        const sNeg = brandPosts.filter(p => p.sentiment === 'negative').length;
        const tot = brandPosts.length || 1;
        const posP = Math.round(sPos / tot * 100);
        const negP = Math.round(sNeg / tot * 100);
        const neuP = 100 - posP - negP;
        // 熱門議題 Top 5（依留言數排序）
        const topicData = [];
        const actPosts = brandPosts.filter(p => classifyPost(p) === '活動');
        const tastePosts = brandPosts.filter(p => classifyPost(p) === '口味');
        const franPosts = brandPosts.filter(p => classifyPost(p) === '加盟');
        if (actPosts.length) topicData.push({{ name: '活動話題', comments: actPosts.reduce((s,p) => s + (p.comment_count||0), 0), count: actPosts.length }});
        if (tastePosts.length) topicData.push({{ name: '口味話題', comments: tastePosts.reduce((s,p) => s + (p.comment_count||0), 0), count: tastePosts.length }});
        if (franPosts.length) topicData.push({{ name: '加盟話題', comments: franPosts.reduce((s,p) => s + (p.comment_count||0), 0), count: franPosts.length }});
        topicData.sort((a,b) => b.comments - a.comments);
        const maxComments = topicData.length ? topicData[0].comments : 1;
        // 本月新聞
        const newsPosts = brandPosts
          .filter(p => NEWS_PLATS_COMP.has(p.platform))
          .sort((a,b) => b.date.localeCompare(a.date));
        const latestNews = newsPosts[0] || null;
        // 本月新品
        const npPost = brandPosts
          .filter(p => {{
            const title = p.title || '';
            const full  = title + ' ' + (p.summary || '');
            return titleKws.some(kw => title.includes(kw)) &&
                   NEW_PRODUCT_KW.some(kw => full.includes(kw));
          }})
          .sort((a,b) => b.date.localeCompare(a.date))[0] || null;
        // 本月最熱 Top 5（依留言數排序）
        const hotPosts = [...brandPosts]
          .sort((a,b) => (b.comment_count||0) - (a.comment_count||0))
          .slice(0, 5);
        const canvasId = `sparkline_${{idx}}`;
        // HTML 片段
        const topicHTML = topicData.length
          ? topicData.map(t => {{
              const sz = 11 + Math.round((t.comments / maxComments) * 8);
              return `<span class="topic-chip" style="font-size:${{sz}}px;background:${{color}}22;color:${{color}};border:1px solid ${{color}}44">${{t.name}}&thinsp;<small style="opacity:.7">${{t.count}}篇/${{t.comments}}留言</small></span>`;
            }}).join('')
          : '<span style="color:var(--muted);font-size:12px">尚無資料</span>';
        const newsHTML = latestNews
          ? `<a class="bcc-article-title" href="${{latestNews.url||'#'}}" target="_blank" rel="noopener noreferrer">${{latestNews.title||'（無標題）'}}</a><div class="bcc-article-meta">${{latestNews.date}}&ensp;·&ensp;${{platformLabel(latestNews.platform)}}</div>`
          : '<div style="color:var(--muted);font-size:12px">本月暫無新聞</div>';
        const npHTML = npPost
          ? `<a class="bcc-article-title" href="${{npPost.url||'#'}}" target="_blank" rel="noopener noreferrer">${{npPost.title||npPost.summary||'（無標題）'}}</a><div class="bcc-article-meta">${{npPost.date}}&ensp;·&ensp;${{platformLabel(npPost.platform)}}</div>`
          : '<div style="color:var(--muted);font-size:12px">本月暫無新品資訊</div>';
        const hotHTML = hotPosts.length
          ? `<div class="bcc-hot-list">${{
              hotPosts.map((p, i) =>
                `<div class="bcc-hot-item">
                  <span class="bcc-hot-rank" style="color:${{color}}">${{i+1}}</span>
                  <div class="bcc-hot-body">
                    <a class="bcc-article-title" href="${{p.url||'#'}}" target="_blank" rel="noopener noreferrer">${{p.title||p.summary||'（無標題）'}}</a>
                    <div class="bcc-article-meta">${{p.date}}&ensp;·&ensp;${{platformLabel(p.platform)}}&ensp;·&ensp;💬&thinsp;${{p.comment_count||0}}</div>
                  </div>
                </div>`
              ).join('')
            }}</div>`
          : '<div style="color:var(--muted);font-size:12px">尚無資料</div>';
        const igBadge = igCnt > 0
          ? `<span class="bcc-source-badge" style="border-color:#E1306C;color:#E1306C">IG&thinsp;${{fmtNum(igCnt)}}</span>`
          : '';
        const card = document.createElement('div');
        card.className = 'brand-comp-card';
        card.style.borderTop = `4px solid ${{color}}`;
        card.innerHTML = `
          <div class="bcc-header">
            <div class="bcc-brand" style="color:${{color}}">${{brand}}</div>
            <div style="text-align:right">
              <div class="bcc-total" style="color:${{color}}">${{brandPosts.length}}</div>
              <div class="bcc-total-label">本月提及</div>
            </div>
          </div>
          <div class="bcc-section">
            <div class="bcc-section-title">📊 聲量來源</div>
            <div class="bcc-sources">
              <span class="bcc-source-badge" style="border-color:var(--threads);color:var(--threads)">Threads&thinsp;${{src.threads}}</span>
              <span class="bcc-source-badge" style="border-color:var(--facebook);color:var(--facebook)">FB&thinsp;${{src.facebook}}</span>
              <span class="bcc-source-badge" style="border-color:var(--yahoo_news);color:var(--yahoo_news)">新聞&thinsp;${{src.news}}</span>
              ${{igBadge}}
            </div>
          </div>
          <div class="bcc-section">
            <div class="bcc-section-title">🌡️ 本月情緒溫度計</div>
            <div class="thermometer-bar">
              <div class="thermo-pos" style="width:${{posP}}%"></div>
              <div class="thermo-neu" style="width:${{neuP}}%"></div>
              <div class="thermo-neg" style="width:${{negP}}%"></div>
            </div>
            <div class="thermo-labels">
              <span class="thermo-label pos">正面 ${{posP}}%</span>
              <span class="thermo-label neu">中性 ${{neuP}}%</span>
              <span class="thermo-label neg">負面 ${{negP}}%</span>
            </div>
          </div>
          <div class="bcc-section">
            <div class="bcc-section-title">🔥 熱門議題（依留言數排序）</div>
            <div class="topic-cloud">${{topicHTML}}</div>
          </div>
          <div class="bcc-section">
            <div class="bcc-section-title">📰 本月新聞&ensp;<strong style="color:${{color}}">${{newsPosts.length}}</strong>&ensp;篇</div>
            ${{newsHTML}}
          </div>
          <div class="bcc-section">
            <div class="bcc-section-title">🆕 本月新品</div>
            ${{npHTML}}
          </div>
          <div class="bcc-section">
            <div class="bcc-section-title">⚡ 本月最熱 Top 5</div>
            ${{hotHTML}}
          </div>`;
        compGrid.appendChild(card);
      }});
    }})();

    // ── 本月市場洞察 ──────────────────────────────────────────────────────────
    (function() {{
      const insights = MONTHLY_INSIGHTS;
      if (!insights || !insights.brand_stats) return;

      // 品牌討論熱度
      const brandGrid = document.getElementById('insightBrands');
      const top3 = insights.top_brands || [];
      if (top3.length) {{
        top3.forEach(([brand, v]) => {{
          const actW = v.total ? Math.round(v.activity_count / v.total * 100) : 0;
          const tasteW = v.total ? Math.round(v.taste_count / v.total * 100) : 0;
          const card = document.createElement('div');
          card.className = 'brand-top-card';
          card.innerHTML = `
            <div class="btc-name">${{brand}}</div>
            <div class="btc-total">${{v.total}} 篇 · ${{v.total_comments}} 則留言</div>
            <div class="btc-bar-row">
              <span class="btc-label">活動類</span>
              <div class="btc-bar-wrap"><div class="btc-bar activity" style="width:${{actW}}%"></div></div>
              <span class="btc-n">${{v.activity_count}}篇</span>
            </div>
            <div class="btc-bar-row">
              <span class="btc-label">口味類</span>
              <div class="btc-bar-wrap"><div class="btc-bar taste" style="width:${{tasteW}}%"></div></div>
              <span class="btc-n">${{v.taste_count}}篇</span>
            </div>`;
          brandGrid.appendChild(card);
        }});
      }} else {{
        brandGrid.innerHTML = '<div style="color:#A0522D;font-size:13px">本月尚無品牌討論資料</div>';
      }}

      // 活動類 vs 口味類
      const catList = document.getElementById('insightCategories');
      const maxCat = Math.max(insights.activity_comments || 0, insights.taste_comments || 0, 1);
      [
        ['🎯 活動類', insights.activity_total, insights.activity_comments],
        ['🍔 口味類', insights.taste_total, insights.taste_comments],
      ].forEach(([label, cnt, comments]) => {{
        const pctVal = Math.round((comments||0) / maxCat * 100);
        const row = document.createElement('div');
        row.className = 'topic-row';
        row.innerHTML = `
          <span class="topic-tag">${{label}}</span>
          <div class="topic-bar-wrap"><div class="topic-bar" style="width:${{pctVal}}%"></div></div>
          <span class="topic-count">${{cnt}}篇 / ${{comments}}留言</span>`;
        catList.appendChild(row);
      }});

      // 行銷建議
      const sugList = document.getElementById('insightSuggestions');
      (insights.suggestions || []).forEach((s, i) => {{
        const card = document.createElement('div');
        card.className = 'suggestion-card';
        card.innerHTML = `
          <div class="sug-num">${{i + 1}}</div>
          <div class="sug-text">${{s}}</div>`;
        sugList.appendChild(card);
      }});
    }})();

  </script>
</body>
</html>"""


# ── 主程式 ────────────────────────────────────────────────────────────────────

def find_latest(pattern: str):
    files = sorted(glob.glob(str(DATA_DIR / pattern)), reverse=True)
    return Path(files[0]) if files else None


def merge_and_dedup(history: list, weekly: list, key: str = "url") -> tuple[list, int, int]:
    seen = set()
    result = []
    for p in weekly + history:
        k = p.get(key, "")
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        result.append(p)
    hist_urls = {p.get(key, "") for p in history if p.get(key)}
    new_added = sum(1 for p in weekly if p.get(key, "") not in hist_urls)
    return result, len(history), new_added


def main() -> None:
    print(f"\n{'═' * 56}")
    print(f"  Dashboard Build (v2)  →  docs/index.html")
    print(f"  當月起算：{CURRENT_MONTH_START}")
    print(f"  一年前：  {ONE_YEAR_AGO}")
    print(f"{'═' * 56}")

    # ── Threads / Facebook（不再讀取 PTT / Dcard）──────────────
    threads_history  = load_threads(DATA_DIR / "history_threads.json")
    facebook_history = load_facebook(DATA_DIR / "history_facebook.json")
    print(f"  ✓  history_threads.json    {len(threads_history):>4} 篇")
    print(f"  ✓  history_facebook.json   {len(facebook_history):>4} 篇")

    social_weekly_path = find_latest("social_????-??-??.json")
    threads_weekly, facebook_weekly, ig_data = [], [], []
    if social_weekly_path:
        raw_social = json.loads(social_weekly_path.read_text(encoding="utf-8"))
        if isinstance(raw_social, dict):
            # Threads：text 欄位為主要內容
            for p in raw_social.get("threads", []):
                text = (p.get("text") or "")
                threads_weekly.append(add_sentiment({
                    "title": text[:60], "url": p.get("url", ""),
                    "platform": "threads", "date": (p.get("created_at") or "")[:10],
                    "comment_count": p.get("replies", 0), "summary": text[:150],
                    "market": "台灣",
                }))
            # Facebook：text 可能為空，優先用 title/content
            for p in raw_social.get("facebook", []):
                text = (p.get("text") or p.get("title") or p.get("content") or "")
                facebook_weekly.append(add_sentiment({
                    "title": text[:60], "url": p.get("url", ""),
                    "platform": "facebook", "date": (p.get("created_at") or p.get("date") or "")[:10],
                    "comment_count": p.get("comments", p.get("comment_count", 0)),
                    "summary": text[:150],
                    "market": "台灣",
                }))
            # Instagram hashtag 統計
            ig_data = raw_social.get("instagram", [])
        else:
            # 若是 list 格式，依 platform 欄位分流
            for p in raw_social:
                plat = p.get("platform", "")
                text = (p.get("text") or p.get("title") or "")
                if plat == "threads":
                    threads_weekly.append(add_sentiment({
                        "title": text[:60], "url": p.get("url", ""),
                        "platform": "threads", "date": (p.get("created_at") or "")[:10],
                        "comment_count": p.get("replies", 0), "summary": text[:150],
                        "market": "台灣",
                    }))
                elif plat == "facebook":
                    facebook_weekly.append(add_sentiment({
                        "title": text[:60], "url": p.get("url", ""),
                        "platform": "facebook", "date": (p.get("created_at") or p.get("date") or "")[:10],
                        "comment_count": p.get("comments", p.get("comment_count", 0)),
                        "summary": text[:150],
                        "market": "台灣",
                    }))
        print(f"  ✓  {social_weekly_path.name:<26} threads {len(threads_weekly)} 篇 / facebook {len(facebook_weekly)} 篇")
    else:
        print("  ⚠  找不到 social_YYYY-MM-DD.json")

    threads_posts,  thr_hist_n, thr_new_n  = merge_and_dedup(threads_history,  threads_weekly)
    facebook_posts, fb_hist_n,  fb_new_n   = merge_and_dedup(facebook_history, facebook_weekly)
    print(f"  → Threads  合計 {len(threads_posts)} 篇")
    print(f"  → Facebook 合計 {len(facebook_posts)} 篇")

    # ── 新聞（Yahoo 奇摩 / LINE Today / Yahoo JP）──────────────
    news_path = find_latest("news_????-??-??.json")
    news_posts = []
    if news_path:
        news_posts = load_news(news_path)
        # 過濾掉 PTT/Dcard 平台（以防萬一）
        news_posts = [p for p in news_posts if p["platform"] not in EXCLUDED_PLATFORMS]
        print(f"  ✓  {news_path.name:<26} {len(news_posts):>4} 篇")
    else:
        print("  ⚠  找不到 news_YYYY-MM-DD.json")

    # ── 彙整（不含 PTT / Dcard）──────────────────────────────
    all_posts = threads_posts + facebook_posts + news_posts
    # 再次確保沒有 PTT/Dcard 資料混入
    all_posts = [p for p in all_posts if p.get("platform", "") not in EXCLUDED_PLATFORMS]
    print(f"\n  → 合計 {len(all_posts)} 篇（Threads {len(threads_posts)} + Facebook {len(facebook_posts)} + 新聞 {len(news_posts)}）")

    # 為每篇文章加上分類標籤
    for p in all_posts:
        p["category"] = classify_post(p)

    # 當月統計
    monthly_count = sum(1 for p in all_posts if p.get("date", "") >= CURRENT_MONTH_START)
    print(f"  → 當月文章：{monthly_count} 篇")

    promos   = load_promos()
    faq_data = load_faq()

    # 產生本月市場洞察
    monthly_insights = generate_monthly_insights(all_posts)
    print(f"  → 本月洞察已產生")

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(build_html(all_posts, promos, faq_data, ig_data, monthly_insights), encoding="utf-8")

    size_kb = OUT_HTML.stat().st_size / 1024
    print(f"  → 輸出：{OUT_HTML}")
    print(f"  → 檔案大小：{size_kb:.1f} KB")
    print(f"{'═' * 56}\n")


if __name__ == "__main__":
    main()
