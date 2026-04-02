#!/usr/bin/env python3
"""
真實問題挖掘 Agent
從 PTT / Dcard / Threads / 社群週報 / 新聞 挖掘受眾真實問句與市場話題。

執行方式：
  python3 research-db/faq_finder.py

輸出：
  data/faq_report_YYYY-MM-DD.json
  data/faq_report_YYYY-MM-DD.md
"""

import json
import glob
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "data"
TODAY     = datetime.now().strftime("%Y-%m-%d")
CUTOFF_30 = datetime.now() - timedelta(days=30)

# ── 問句偵測詞 ────────────────────────────────────────────────────────────────
QUESTION_PATTERNS = [
    "嗎", "呢", "？", "?",
    "如何", "怎麼", "怎樣", "哪裡", "哪個", "哪家",
    "值不值", "推薦嗎", "有人", "請問", "想問", "求問",
    "有沒有", "可以嗎", "適合嗎", "需要嗎", "好嗎",
    "划算嗎", "難嗎", "容易嗎", "多少", "幾年", "幾個月",
]

# ── 6 大問句分類 ──────────────────────────────────────────────────────────────
CATEGORIES = {
    "💰 加盟費用類": [
        "加盟金", "加盟費", "費用", "權利金", "保證金", "成本", "投資",
        "多少錢", "預算", "資金", "開店費", "月費", "抽成", "分潤",
    ],
    "📈 獲利評估類": [
        "回本", "獲利", "賺錢", "利潤", "毛利", "淨利", "損益",
        "月收", "月營業額", "業績", "營收", "值不值", "划算",
        "多久回本", "幾年", "賺不賺", "虧損",
    ],
    "📋 展店流程類": [
        "加盟流程", "申請", "開店", "展店", "手續", "條件", "資格",
        "店面", "坪數", "裝潢", "培訓", "教育訓練", "試營運",
        "選址", "地點", "合約", "年限", "續約",
    ],
    "🏪 品牌比較類": [
        "哪家好", "比較", "選哪個", "推薦哪", "差別", "差異",
        "vs", "還是", "或是", "哪個品牌", "評價", "口碑",
        "麥味登", "Q Burger", "弘爺", "晨間廚房", "美而美",
        "美芝城", "萬佳香", "早安公雞", "呷尚寶", "蕃茄村",
    ],
    "🍔 消費者體驗類": [
        "好吃", "難吃", "推薦", "必點", "必吃", "口感", "份量",
        "服務", "態度", "環境", "等待", "排隊", "新品", "試吃",
        "菜單", "價格貴", "CP值", "踩雷", "失望", "滿意",
    ],
    "💡 其他創業類": [
        "創業", "副業", "兼職", "全職", "辭職", "轉行", "斜槓",
        "自己開店", "自創品牌", "獨立", "風險", "失敗", "成功",
        "新手", "第一次", "沒經驗",
    ],
}

# ── 新聞熱門話題關鍵字 ────────────────────────────────────────────────────────
NEWS_TOPICS = [
    "聯名", "限定", "新品", "漲價", "加盟展",
    "優惠", "活動", "折扣", "集點", "新口味",
    "展店", "開幕", "新店", "突破", "創新",
    "永續", "環保", "健康", "素食", "外送",
    "漲", "調整", "改革", "轉型", "數位",
]

# ── 競品品牌 ──────────────────────────────────────────────────────────────────
COMPETITOR_BRANDS = [
    "拉亞", "麥味登", "Q Burger", "QBurger",
    "弘爺", "晨間廚房", "美而美", "美芝城",
    "萬佳香", "早安公雞", "呷尚寶", "蕃茄村",
    "麥當勞", "肯德基", "摩斯漢堡",
    "50嵐", "清心福全", "CoCo",
]

# ── 情緒詞 ────────────────────────────────────────────────────────────────────
POSITIVE_WORDS = [
    "好吃", "推薦", "喜歡", "讚", "棒", "優", "便宜", "划算",
    "滿意", "新鮮", "好喝", "必吃", "必點", "值得", "超值",
    "成功", "賺錢", "獲利", "回本快", "穩定",
]
NEGATIVE_WORDS = [
    "難吃", "踩雷", "失望", "貴", "少", "差", "爛", "黑心",
    "詐騙", "騙", "虧損", "失敗", "倒閉", "抱怨", "糟糕",
    "漲價", "縮水", "不新鮮", "態度差", "等很久",
]

PLATFORM_LABEL = {
    "ptt":       "PTT",
    "dcard":     "Dcard",
    "threads":   "Threads",
    "facebook":  "Facebook",
    "instagram": "Instagram",
    "yahoo_news":"Yahoo新聞",
    "line_today":"LINE Today",
    "yahoo_jp":  "Yahoo JP",
}


# ─────────────────────────────────────────────────────────────────────────────
# 資料載入
# ─────────────────────────────────────────────────────────────────────────────

def latest_glob(pattern: str):
    files = sorted(glob.glob(str(DATA_DIR / pattern)), reverse=True)
    return Path(files[0]) if files else None


def load_social_posts() -> list:
    """載入所有社群資料，統一格式為 {title, text, platform, date, url}"""
    posts = []

    # ── PTT ──────────────────────────────────────────────────
    for fname in ("ptt_history_2021.json", "ptt_history_2025.json"):
        pf = DATA_DIR / fname
        if not pf.exists():
            continue
        raw = json.loads(pf.read_text(encoding="utf-8"))
        for p in raw.get("posts", []):
            posts.append({
                "title":    p.get("title", ""),
                "text":     p.get("title", "") + " " + p.get("summary", ""),
                "platform": "ptt",
                "date":     (p.get("date") or "")[:10],
                "url":      p.get("url", ""),
            })

    # ── Dcard history ────────────────────────────────────────
    dcard_hist = DATA_DIR / "history_dcard.json"
    if dcard_hist.exists():
        raw = json.loads(dcard_hist.read_text(encoding="utf-8"))
        for p in raw.get("posts", []):
            posts.append({
                "title":    p.get("title", ""),
                "text":     p.get("title", "") + " " + p.get("summary", ""),
                "platform": "dcard",
                "date":     (p.get("created_at") or "")[:10],
                "url":      p.get("url", ""),
            })

    # ── Dcard 最新週報 ───────────────────────────────────────
    dcard_w = latest_glob("dcard_????-??-??.json")
    if dcard_w:
        raw = json.loads(dcard_w.read_text(encoding="utf-8"))
        for p in raw.get("posts", []):
            posts.append({
                "title":    p.get("title", ""),
                "text":     p.get("title", "") + " " + p.get("summary", ""),
                "platform": "dcard",
                "date":     (p.get("created_at") or "")[:10],
                "url":      p.get("url", ""),
            })

    # ── Threads history ──────────────────────────────────────
    threads_hist = DATA_DIR / "history_threads.json"
    if threads_hist.exists():
        raw = json.loads(threads_hist.read_text(encoding="utf-8"))
        for p in raw.get("posts", []):
            text = p.get("text", "")
            posts.append({
                "title":    text[:60],
                "text":     text,
                "platform": "threads",
                "date":     (p.get("created_at") or "")[:10],
                "url":      p.get("url", ""),
            })

    # ── Social 最新週報（threads / facebook / instagram）────────
    social_w = latest_glob("social_????-??-??.json")
    if social_w:
        raw = json.loads(social_w.read_text(encoding="utf-8"))
        for plat_key in ("threads", "facebook", "instagram"):
            for p in raw.get(plat_key, []):
                text = p.get("text", "")
                posts.append({
                    "title":    text[:60],
                    "text":     text,
                    "platform": plat_key,
                    "date":     (p.get("created_at") or "")[:10],
                    "url":      p.get("url", ""),
                })

    # 去重（url 或 title）
    seen, result = set(), []
    for p in posts:
        key = p["url"] or p["title"]
        if key in seen:
            continue
        seen.add(key)
        result.append(p)

    return result


def load_news() -> list:
    """載入最新新聞 JSON"""
    nf = latest_glob("news_????-??-??.json")
    if not nf:
        return []
    return json.loads(nf.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# 分析功能
# ─────────────────────────────────────────────────────────────────────────────

def is_question(text: str) -> bool:
    return any(p in text for p in QUESTION_PATTERNS)


def mine_questions(posts: list) -> list:
    """從社群文章找出含問句的貼文"""
    result = []
    for p in posts:
        text = p["text"]
        if not is_question(text):
            continue
        snippet = text.strip()[:80].replace("\n", " ")
        result.append({
            "snippet":   snippet,
            "platform":  p["platform"],
            "date":      p["date"],
            "url":       p["url"],
            "full_text": text,
        })
    return result


def categorize_questions(questions: list):
    """將問句分入 6 大類（每則只歸入第一個命中的類別）"""
    categorized  = {cat: [] for cat in CATEGORIES}
    uncategorized = []
    for q in questions:
        text   = q["full_text"]
        matched = False
        for cat, keywords in CATEGORIES.items():
            if any(kw in text for kw in keywords):
                categorized[cat].append(q)
                matched = True
                break
        if not matched:
            uncategorized.append(q)
    return categorized, uncategorized


def mine_news_topics(news: list) -> dict:
    """統計近 30 天新聞中各話題出現次數，回傳 Top 10"""
    counts = Counter()
    for item in news:
        date_str = item.get("date", "")
        if date_str:
            try:
                if datetime.strptime(date_str, "%Y-%m-%d") < CUTOFF_30:
                    continue
            except ValueError:
                pass
        text = item.get("title", "") + " " + item.get("summary", "")
        for topic in NEWS_TOPICS:
            if topic in text:
                counts[topic] += 1
    return dict(counts.most_common(10))


def analyze_competitors(posts: list, news: list) -> dict:
    """分析各競品品牌的正/負面話題（各取 3 則）"""
    # 合併社群 + 新聞成統一格式
    all_items = list(posts)
    for n in news:
        all_items.append({
            "text":     n.get("title", "") + " " + n.get("summary", ""),
            "platform": n.get("platform", ""),
            "date":     n.get("date", ""),
            "url":      n.get("url", ""),
        })

    result = {}
    for brand in COMPETITOR_BRANDS:
        matched = [p for p in all_items if brand in p.get("text", "")]
        if not matched:
            continue
        positives, negatives = [], []
        for p in matched:
            text    = p.get("text", "")
            snippet = text.strip()[:70].replace("\n", " ")
            entry   = {
                "snippet":  snippet,
                "platform": p.get("platform", ""),
                "url":      p.get("url", ""),
            }
            has_pos = any(w in text for w in POSITIVE_WORDS)
            has_neg = any(w in text for w in NEGATIVE_WORDS)
            if has_neg:
                negatives.append(entry)
            elif has_pos:
                positives.append(entry)
        result[brand] = {
            "total":     len(matched),
            "positives": positives[:3],
            "negatives": negatives[:3],
        }
    return result


def generate_suggestions(topic_counts: dict, categorized: dict, competitor_analysis: dict) -> list:
    """根據分析結果產生 5 個具體內容主題建議"""
    suggestions = []

    # 1. 最熱門新聞話題
    if topic_counts:
        top_topic, top_cnt = list(topic_counts.items())[0]
        suggestions.append(
            f"製作「早餐品牌{top_topic}特輯」：本期新聞「{top_topic}」出現 {top_cnt} 次，"
            f"是市場最高關注話題，可製作比較型或品牌觀察文，搭上流量紅利。"
        )

    # 2. 費用類
    fee_n = len(categorized.get("💰 加盟費用類", []))
    if fee_n:
        suggestions.append(
            f"發布「早餐加盟費用完整攻略」：共有 {fee_n} 則受眾在問費用相關問題，"
            f"製作各品牌加盟金比較表（含隱藏成本），直接命中潛客最高頻痛點。"
        )

    # 3. 獲利類
    roi_n = len(categorized.get("📈 獲利評估類", []))
    if roi_n:
        suggestions.append(
            f"推出「加盟回本期實測」系列：有 {roi_n} 則受眾關心回本速度，"
            f"用加盟主訪談或試算表格呈現，建立真實信任感。"
        )

    # 4. 品牌比較
    cmp_items = categorized.get("🏪 品牌比較類", [])
    if cmp_items:
        brand_cnt = Counter()
        for q in cmp_items:
            for b in COMPETITOR_BRANDS:
                if b in q["full_text"]:
                    brand_cnt[b] += 1
        top_brands = [b for b, _ in brand_cnt.most_common(2) if b != "拉亞"]
        if top_brands:
            suggestions.append(
                f"製作「拉亞 vs {' vs '.join(top_brands[:2])}」品牌比較內容：受眾最常把這幾個品牌一起比較，"
                f"客觀比較有助吸引潛在加盟主做決策。"
            )
        else:
            suggestions.append(
                "製作「我為什麼選拉亞」品牌故事：受眾有選品牌困難，從真實加盟主視角切入，突顯差異化優勢。"
            )

    # 5. 競品負評機會
    neg_brands = [b for b, v in competitor_analysis.items() if v["negatives"]]
    exp_n = len(categorized.get("🍔 消費者體驗類", []))
    if neg_brands:
        suggestions.append(
            f"趁競品負評期間強打品質形象：{', '.join(neg_brands[:3])} 近期出現負評聲浪，"
            f"是強調拉亞品質與服務的好時機，可發「我們堅持 XX 的原因」品牌故事。"
        )
    elif exp_n:
        suggestions.append(
            f"整合消費者 UGC 口碑集錦：有 {exp_n} 則體驗相關討論，"
            f"匯整正評並鼓勵顧客打卡分享，擴大口碑傳播效果。"
        )

    # 補足到 5 則
    while len(suggestions) < 5:
        suggestions.append(
            "製作「早餐加盟新手完整指南」：整合流程、費用、選址、培訓資訊，"
            "做成可下載懶人包作為潛客磁鐵，增加名單蒐集。"
        )

    return suggestions[:5]


# ─────────────────────────────────────────────────────────────────────────────
# 輸出組裝
# ─────────────────────────────────────────────────────────────────────────────

def build_json(social_n, news_n, topic_counts, categorized, uncategorized, competitor_analysis, suggestions):
    return {
        "generated_at":           TODAY,
        "social_posts_analyzed":  social_n,
        "news_analyzed":          news_n,
        "news_topics":            topic_counts,
        "question_categories": {
            cat: [
                {"snippet": q["snippet"], "platform": q["platform"], "date": q["date"]}
                for q in items[:20]
            ]
            for cat, items in categorized.items()
        },
        "uncategorized_sample": [
            {"snippet": q["snippet"], "platform": q["platform"]}
            for q in uncategorized[:10]
        ],
        "competitor_analysis": {
            brand: {
                "total":     v["total"],
                "positives": v["positives"],
                "negatives": v["negatives"],
            }
            for brand, v in competitor_analysis.items()
        },
        "marketing_suggestions": suggestions,
    }


def build_md(social_n, news_n, topic_counts, categorized, competitor_analysis, suggestions):
    L = []

    L += [
        "# 受眾真實問題挖掘報告",
        "",
        f"日期：{TODAY}",
        f"分析文章：**{social_n} 篇社群** + **{news_n} 篇新聞**",
        "",
    ]

    # ── 市場熱門話題
    L += ["## 🔥 本期市場熱門話題（來自新聞）", ""]
    if topic_counts:
        L += ["| 排名 | 話題 | 出現次數 |", "|------|------|----------|"]
        for i, (topic, cnt) in enumerate(topic_counts.items(), 1):
            L.append(f"| {i} | {topic} | {cnt} 次 |")
    else:
        L.append("（本期無足夠新聞資料）")
    L.append("")

    # ── 6 大問句分類
    for cat, items in categorized.items():
        L.append(f"## {cat}（{len(items)} 則）")
        L.append("")
        if not items:
            L.append("（本期無相關問句）")
        else:
            for q in items[:10]:
                plat = PLATFORM_LABEL.get(q["platform"], q["platform"])
                L.append(f"- **[{plat}]** {q['snippet']}")
        L.append("")

    # ── 競品話題分析
    L += ["## 🏢 競品話題分析", ""]
    active = {b: v for b, v in competitor_analysis.items() if v["total"] > 0}
    if active:
        for brand, v in active.items():
            L.append(f"### {brand}（共 {v['total']} 則提及）")
            if v["positives"]:
                L.append("**✅ 正面話題：**")
                for p in v["positives"]:
                    plat = PLATFORM_LABEL.get(p["platform"], p["platform"])
                    L.append(f"- [{plat}] {p['snippet']}")
            if v["negatives"]:
                L.append("**❌ 負面話題：**")
                for p in v["negatives"]:
                    plat = PLATFORM_LABEL.get(p["platform"], p["platform"])
                    L.append(f"- [{plat}] {p['snippet']}")
            L.append("")
    else:
        L += ["（無競品相關討論）", ""]

    # ── 行銷建議
    L += ["## 📝 行銷建議", ""]
    for i, s in enumerate(suggestions, 1):
        L.append(f"{i}. {s}")
    L.append("")

    return "\n".join(L)


# ─────────────────────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═' * 60}")
    print(f"  真實問題挖掘 Agent  {TODAY}")
    print(f"{'═' * 60}")

    # 1. 載入
    print("\n  📂 載入資料...")
    social_posts = load_social_posts()
    news         = load_news()
    print(f"     社群文章：{len(social_posts)} 篇")
    print(f"     新聞：    {len(news)} 篇")

    # 2. 問句挖掘
    print("\n  🔍 問句挖掘...")
    questions = mine_questions(social_posts)
    print(f"     偵測到問句：{len(questions)} 則")

    # 3. 分類
    categorized, uncategorized = categorize_questions(questions)
    print("\n  📊 分類結果：")
    for cat, items in categorized.items():
        print(f"     {cat}：{len(items)} 則")
    print(f"     （未分類：{len(uncategorized)} 則）")

    # 4. 新聞話題
    print("\n  📰 新聞話題統計（近 30 天）...")
    topic_counts = mine_news_topics(news)
    if topic_counts:
        top5 = list(topic_counts.items())[:5]
        print(f"     Top 5：{', '.join(f'{k}({v})' for k, v in top5)}")
    else:
        print("     （無新聞資料）")

    # 5. 競品分析
    print("\n  🏢 競品話題分析...")
    competitor_analysis = analyze_competitors(social_posts, news)
    for brand, v in competitor_analysis.items():
        if v["total"] > 0:
            print(f"     {brand}：{v['total']} 則（正面 {len(v['positives'])} / 負面 {len(v['negatives'])}）")

    # 6. 行銷建議
    suggestions = generate_suggestions(topic_counts, categorized, competitor_analysis)

    # 7. 輸出
    print("\n  💾 輸出報告...")
    DATA_DIR.mkdir(exist_ok=True)

    json_data = build_json(
        len(social_posts), len(news),
        topic_counts, categorized, uncategorized,
        competitor_analysis, suggestions,
    )
    json_path = DATA_DIR / f"faq_report_{TODAY}.json"
    json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"     ✓ {json_path.name}")

    md_text  = build_md(
        len(social_posts), len(news),
        topic_counts, categorized,
        competitor_analysis, suggestions,
    )
    md_path  = DATA_DIR / f"faq_report_{TODAY}.md"
    md_path.write_text(md_text, encoding="utf-8")
    print(f"     ✓ {md_path.name}")

    # 8. 印出報告
    print(f"\n{'─' * 60}")
    print(md_text)
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
