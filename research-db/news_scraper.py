#!/usr/bin/env python3
"""
新聞搜尋爬蟲 - 台灣 & 日本 競品同業活動新聞
存入 data/news_YYYY-MM-DD.json

執行方式：
  python3 research-db/news_scraper.py

技術說明：
  使用 Google News RSS + site: 運算子，免費、無需 API key。
  台灣：site:tw.news.yahoo.com / site:today.line.me
  日本：site:news.yahoo.co.jp
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
DATA_DIR    = BASE_DIR / "data"
TODAY       = datetime.now().strftime("%Y-%m-%d")
CUTOFF      = datetime.now() - timedelta(days=7)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
}

MAX_PER_KEYWORD = 10   # 每個關鍵字最多取幾篇

# ── 關鍵字設定 ────────────────────────────────────────────────────────────────

TW_BRAND_KEYWORDS = [
    # 速食／早餐大型品牌
    "麥當勞", "肯德基", "摩斯漢堡", "MOS Burger", "7-ELEVEN", "7-11", "全家", "FamilyMart",
    # 拉亞系列
    "拉亞", "拉亞漢堡", "拉雅", "Laya", "Laya Burger",
    # 早餐連鎖
    "麥味登", "Q Burger", "QBurger", "q burger", "qburger",
    "弘爺", "晨間廚房", "美而美", "美芝城", "萬佳香",
    "早安公雞", "呷尚寶", "JSP", "蕃茄村",
    # 飲料連鎖
    "50嵐", "清心福全", "CoCo都可", "天仁茗茶", "大苑子",
    "迷客夏", "茶湯會", "珍煮丹", "鮮芋仙", "麻古茶坊",
]

TW_ACTIVITY_KEYWORDS = [
    "新品", "限定", "優惠", "活動", "聯名", "上市", "促銷",
]

JP_BRAND_KEYWORDS = [
    "マクドナルド", "ケンタッキー", "モスバーガー",
    "セブンイレブン", "ファミリーマート", "ローソン",
    "すき家", "吉野家", "松屋", "サイゼリヤ", "ガスト",
]

# ── 平台設定 ──────────────────────────────────────────────────────────────────

# 台灣：Google News RSS（繁中）
TW_PLATFORMS = {
    "yahoo_news": "tw.news.yahoo.com",
    "line_today": "today.line.me",
}
TW_RSS_BASE = "https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

# 日本：Google News RSS（日文）
JP_PLATFORM  = {"yahoo_jp": "news.yahoo.co.jp"}
JP_RSS_BASE  = "https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"

# ── 相關性過濾 ────────────────────────────────────────────────────────────────

TW_RELEVANT = [
    "早餐", "漢堡", "加盟", "餐飲", "早午餐", "連鎖", "菜單", "新品", "門市",
    "食物", "美食", "飲料", "咖啡", "手搖", "品牌", "創業", "展店",
    "限定", "優惠", "活動", "聯名", "上市", "促銷",
]

JP_RELEVANT = [
    "メニュー", "新商品", "限定", "キャンペーン", "グルメ", "飲食",
    "コーヒー", "ハンバーガー", "ランチ", "朝食", "フード", "料理",
    "店舗", "開店", "閉店", "値上げ", "コラボ", "発売",
]

BLACKLIST = [
    "死亡", "傷亡", "車禍", "衝撞", "槍擊", "爆炸", "颱風", "地震",
    "股票", "政治", "選舉", "死者", "事故",
]

# 標題末尾「 - 來源名稱」去除
SOURCE_SUFFIX_RE = re.compile(r"\s*[-–]\s*[^-–]{2,40}\s*$")


def is_relevant(title: str, summary: str, relevant_kws: list) -> bool:
    if any(kw in title for kw in BLACKLIST):
        return False
    text = title + summary
    return any(kw in text for kw in relevant_kws)


def clean_title(raw: str) -> str:
    return SOURCE_SUFFIX_RE.sub("", raw).strip()


# ── 日期處理 ──────────────────────────────────────────────────────────────────

def parse_rss_date(pub_date: str) -> str:
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def is_within_7_days(date_str: str) -> bool:
    if not date_str:
        return True
    try:
        return datetime.strptime(date_str, "%Y-%m-%d") >= CUTOFF
    except ValueError:
        return True


# ── RSS 抓取 ──────────────────────────────────────────────────────────────────

def fetch_rss(rss_base: str, query: str) -> list:
    url = rss_base.format(query=quote(query))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        return root.findall(".//item")
    except Exception as e:
        print(f"    ⚠  RSS 失敗（{query[:25]}）：{e}")
        return []


def parse_items(
    items: list,
    platform: str,
    keyword: str,
    market: str,
    relevant_kws: list,
    limit: int = MAX_PER_KEYWORD,
) -> list:
    results = []
    for item in items:
        if len(results) >= limit:
            break
        pub_date = item.findtext("pubDate", "")
        date_str = parse_rss_date(pub_date)
        if not is_within_7_days(date_str):
            continue

        raw_title = item.findtext("title", "")
        title     = clean_title(raw_title)
        url       = item.findtext("link", "")
        if not url or "news.google.com" not in url:
            url = item.findtext("guid", "") or url
        summary = re.sub(r"<[^>]+>", "", (item.findtext("description") or ""))[:200].strip()

        if not title:
            continue
        if not is_relevant(title, summary, relevant_kws):
            continue

        results.append({
            "title":    title,
            "url":      url,
            "platform": platform,
            "date":     date_str,
            "summary":  summary,
            "keyword":  keyword,
            "market":   market,
        })
    return results


# ── 去重 ─────────────────────────────────────────────────────────────────────

def dedup(posts: list) -> list:
    seen, result = set(), []
    for p in posts:
        key = p.get("url") or p.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        result.append(p)
    return result


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═' * 60}")
    print(f"  競品新聞爬蟲  {TODAY}  |  最近 7 天  |  每關鍵字上限 {MAX_PER_KEYWORD} 篇")
    print(f"{'═' * 60}")

    all_results = []
    raw_total   = 0
    tw_count    = 0
    jp_count    = 0

    # ── 台灣品牌 × Yahoo TW + LINE Today ─────────────────────────────────────
    tw_keywords = TW_BRAND_KEYWORDS + TW_ACTIVITY_KEYWORDS
    total_tw_q  = len(tw_keywords) * len(TW_PLATFORMS)
    done        = 0

    print(f"\n  【台灣市場】品牌 {len(TW_BRAND_KEYWORDS)} 個 + 活動詞 {len(TW_ACTIVITY_KEYWORDS)} 個")
    print(f"  平台：Yahoo 奇摩新聞、LINE Today（共 {total_tw_q} 次查詢）")
    print(f"  {'─' * 56}")

    for kw in tw_keywords:
        for platform, site_domain in TW_PLATFORMS.items():
            done += 1
            query = f"{kw} site:{site_domain}"
            items = fetch_rss(TW_RSS_BASE, query)
            raw_total += len(items)
            parsed = parse_items(items, platform, kw, "台灣", TW_RELEVANT)
            tw_count += len(parsed)
            all_results.extend(parsed)

            label = "Yahoo" if platform == "yahoo_news" else "LINE "
            print(f"  [{done:>3}/{total_tw_q}] {label} ｜ {kw:<14} → {len(parsed):>2} 篇")

            if done < total_tw_q:
                time.sleep(2)

    # ── 日本品牌 × Yahoo Japan ────────────────────────────────────────────────
    total_jp_q = len(JP_BRAND_KEYWORDS)
    done_jp    = 0

    print(f"\n  【日本市場】品牌 {len(JP_BRAND_KEYWORDS)} 個")
    print(f"  平台：Yahoo Japan 新聞（共 {total_jp_q} 次查詢）")
    print(f"  {'─' * 56}")

    for kw in JP_BRAND_KEYWORDS:
        done_jp += 1
        query = f"{kw} site:news.yahoo.co.jp"
        items = fetch_rss(JP_RSS_BASE, query)
        raw_total += len(items)
        parsed = parse_items(items, "yahoo_jp", kw, "日本", JP_RELEVANT)
        jp_count += len(parsed)
        all_results.extend(parsed)

        print(f"  [{done_jp:>2}/{total_jp_q}] Yahoo JP ｜ {kw:<14} → {len(parsed):>2} 篇")

        if done_jp < total_jp_q:
            time.sleep(2)

    # ── 彙整輸出 ─────────────────────────────────────────────────────────────
    before_dedup = len(all_results)
    all_results  = dedup(all_results)
    all_results.sort(key=lambda p: p.get("date", ""), reverse=True)

    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"news_{TODAY}.json"
    out_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'─' * 60}")
    print(f"  RSS 原始總篇數  ：{raw_total} 篇")
    print(f"  相關性過濾後    ：{before_dedup} 篇（台灣 {tw_count} / 日本 {jp_count}）")
    print(f"  去重排除        ：{before_dedup - len(all_results)} 篇")
    print(f"  → 台灣          ：{sum(1 for p in all_results if p['market']=='台灣')} 篇")
    print(f"  → 日本          ：{sum(1 for p in all_results if p['market']=='日本')} 篇")
    print(f"  → 總計          ：{len(all_results)} 篇")
    print(f"  → 輸出：{out_path}")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
