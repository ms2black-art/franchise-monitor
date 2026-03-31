#!/usr/bin/env python3
"""
新聞搜尋爬蟲 - Yahoo 奇摩新聞 & LINE Today
讀取 research-db/config.json 關鍵字，抓取最近 7 天新聞。
存入 data/news_YYYY-MM-DD.json

執行方式：
  python3 research-db/news_scraper.py

技術說明：
  Yahoo 奇摩新聞與 LINE Today 均為 JavaScript 渲染頁面，requests 無法
  直接解析搜尋結果。本腳本改用 Google News RSS（免費、無需 API key），
  以 site: 運算子過濾各平台文章：
    - site:tw.news.yahoo.com → platform: yahoo_news
    - site:today.line.me     → platform: line_today
"""

import json
import time
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote
from email.utils import parsedate_to_datetime

import requests

BASE_DIR    = Path(__file__).parent.parent
CONFIG_PATH = Path(__file__).parent / "config.json"
DATA_DIR    = BASE_DIR / "data"
TODAY       = datetime.now().strftime("%Y-%m-%d")
CUTOFF      = datetime.now() - timedelta(days=7)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
)

# 各平台的 Google News site: 篩選條件
PLATFORMS = {
    "yahoo_news": "tw.news.yahoo.com",
    "line_today":  "today.line.me",
}

# 標題末尾「 - 來源名稱」去除
SOURCE_SUFFIX_RE = re.compile(r"\s*-\s*[^-]{2,30}\s*$")

# ── 相關性過濾 ────────────────────────────────────────────────────────────────

# 標題或摘要需包含至少一個，才視為相關
RELEVANT_KEYWORDS = [
    "早餐", "漢堡", "加盟", "餐飲", "早午餐", "連鎖", "菜單", "新品", "門市",
    "食物", "美食", "飲料", "咖啡", "手搖", "品牌", "創業", "展店",
]

# 標題含任一個，直接排除
BLACKLIST_KEYWORDS = [
    "死亡", "傷亡", "車禍", "衝撞", "槍擊", "爆炸", "颱風", "地震", "股票", "政治", "選舉",
]


def is_relevant(title: str, summary: str) -> bool:
    """標題或摘要需包含至少一個相關詞，且標題不含黑名單詞。"""
    text = title + summary
    if any(kw in title for kw in BLACKLIST_KEYWORDS):
        return False
    return any(kw in text for kw in RELEVANT_KEYWORDS)


# ── 設定讀取 ──────────────────────────────────────────────────────────────────

def load_keywords() -> list:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    kws = set()
    kws.update(config.get("dcard", {}).get("keywords", []))
    kws.update(config.get("ptt",   {}).get("keywords", []))
    # 也納入 topics 的 keyword
    for t in config.get("topics", []):
        kws.add(t["keyword"])
    return sorted(kws)


# ── 日期處理 ──────────────────────────────────────────────────────────────────

def parse_rss_date(pub_date: str) -> str:
    """RSS RFC-2822 日期 → YYYY-MM-DD，失敗回傳空字串。"""
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def is_within_7_days(date_str: str) -> bool:
    if not date_str:
        return True  # 無法判斷時保留
    try:
        return datetime.strptime(date_str, "%Y-%m-%d") >= CUTOFF
    except ValueError:
        return True


# ── RSS 抓取與解析 ────────────────────────────────────────────────────────────

def fetch_rss(query: str) -> list:
    """向 Google News RSS 發出請求，回傳 <item> 清單（ET Element）。"""
    url = GOOGLE_NEWS_RSS.format(query=quote(query))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        return root.findall(".//item")
    except Exception as e:
        print(f"    ⚠  RSS 請求失敗（{query[:30]}）：{e}")
        return []


def clean_title(raw: str) -> str:
    """移除標題末尾的「 - 來源名稱」。"""
    return SOURCE_SUFFIX_RE.sub("", raw).strip()


def parse_items(items: list, platform: str, keyword: str) -> list:
    """將 RSS <item> 轉為統一格式，過濾 7 天外的文章。"""
    results = []
    for item in items:
        pub_date = item.findtext("pubDate", "")
        date_str = parse_rss_date(pub_date)
        if not is_within_7_days(date_str):
            continue

        raw_title = item.findtext("title", "")
        title     = clean_title(raw_title)
        url       = item.findtext("link", "")
        # Google RSS 有時把 link 放在 <link> 之後（text tail），改用 guid
        if not url or "news.google.com" not in url:
            url = item.findtext("guid", "") or url
        summary = (item.findtext("description") or "")[:150]
        # description 有時是 HTML，去掉標籤
        summary = re.sub(r"<[^>]+>", "", summary).strip()

        if not title:
            continue
        if not is_relevant(title, summary):
            continue

        results.append({
            "title":    title,
            "url":      url,
            "platform": platform,
            "date":     date_str,
            "summary":  summary,
            "keyword":  keyword,
        })
    return results


# ── 去重 ─────────────────────────────────────────────────────────────────────

def dedup(posts: list) -> list:
    seen = set()
    result = []
    for p in posts:
        key = p.get("url") or p.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        result.append(p)
    return result


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    keywords = load_keywords()
    print(f"\n{'═' * 56}")
    print(f"  新聞爬蟲  {TODAY}")
    print(f"  關鍵字：{len(keywords)} 個  |  過濾：最近 7 天")
    print(f"  平台：Yahoo 奇摩新聞 / LINE Today")
    print(f"{'═' * 56}")

    all_results   = []
    yahoo_total   = 0
    line_total    = 0
    raw_total     = 0   # 過濾前總篇數（含重複）
    total_queries = len(keywords) * len(PLATFORMS)
    done          = 0

    for kw in keywords:
        for platform, site_domain in PLATFORMS.items():
            done += 1
            query = f"{kw} site:{site_domain}"
            items = fetch_rss(query)
            raw_total += len(items)
            parsed = parse_items(items, platform, kw)

            if platform == "yahoo_news":
                yahoo_total += len(parsed)
            else:
                line_total  += len(parsed)

            all_results.extend(parsed)

            label = "Yahoo" if platform == "yahoo_news" else "LINE "
            print(f"  [{done:>3}/{total_queries}] {label} ｜ {kw:<12} → {len(parsed):>3} 篇")

            if done < total_queries:
                time.sleep(2)

    # 去重 + 日期排序
    before_dedup = len(all_results)
    all_results = dedup(all_results)
    all_results.sort(key=lambda p: p.get("date", ""), reverse=True)

    # 輸出
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"news_{TODAY}.json"
    out_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    filtered_out = raw_total - (yahoo_total + line_total)
    print(f"\n{'─' * 56}")
    print(f"  過濾前（RSS 原始）   ：{raw_total} 篇")
    print(f"  相關性過濾排除       ：{filtered_out} 篇")
    print(f"  通過過濾             ：{yahoo_total + line_total} 篇（Yahoo {yahoo_total} / LINE {line_total}）")
    print(f"  去重排除             ：{before_dedup - len(all_results)} 篇")
    print(f"  → 最終存檔           ：{len(all_results)} 篇")
    print(f"  → 輸出：{out_path}")
    print(f"{'═' * 56}\n")


if __name__ == "__main__":
    main()
