#!/usr/bin/env python3
"""
競品新聞爬蟲 - 台灣 & 日本
搜尋各品牌最新新聞，雙重過濾確保品質。
存入 data/news_YYYY-MM-DD.json

執行方式：
  python3 research-db/news_scraper.py

平台說明：
  台灣：Yahoo 奇摩新聞（tw.news.yahoo.com）
        LINE Today（today.line.me）
  日本：Yahoo Japan 新聞（news.yahoo.co.jp）

  以上平台均為 JS 渲染，本腳本改用 Google News RSS + site: 運算子抓取，
  效果等同直接搜尋各平台，免費且無需 API key。
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

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
TODAY    = datetime.now().strftime("%Y-%m-%d")
CUTOFF   = datetime.now() - timedelta(days=7)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
}

MAX_PER_KEYWORD = 10
MAX_PER_SOURCE  = 25   # 每個直接 RSS 來源最多取幾篇（過濾後）

# ── 平台設定 ──────────────────────────────────────────────────────────────────
# 說明：各平台真實 URL（供文件記錄），實際抓取使用 Google News RSS + site:

# 台灣平台
# Yahoo 奇摩新聞：https://tw.news.yahoo.com/search?p=關鍵字
# LINE Today    ：https://today.line.me/tw/v2/search?q=關鍵字
TW_PLATFORMS = {
    "yahoo_news": "tw.news.yahoo.com",
    "line_today":  "today.line.me",
}
TW_RSS = "https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"

# 台灣直接 RSS 來源（直接抓全文，再用品牌關鍵字過濾）
TW_DIRECT_RSS = {
    "東森新聞":  "https://news.ebc.net.tw/rss",
    "年代新聞":  "https://www.nexttv.com.tw/rss",
    "民視新聞":  "https://www.ftvnews.com.tw/rss/rss.aspx",
    "三立新聞":  "https://www.setn.com/rss.aspx",
    "TVBS新聞":  "https://news.tvbs.com.tw/rss/news",
    "中時新聞":  "https://www.chinatimes.com/rss/realtime.xml",
    "自由時報":  "https://news.ltn.com.tw/rss/all.xml",
    "ETtoday":   "https://feeds.feedburner.com/ettoday/realtime",
    "聯合新聞網": "https://udn.com/rssfeed/news/2/0?ch=news",
}

# 日本平台
# Yahoo Japan 新聞：https://news.yahoo.co.jp/search?p=關鍵字
JP_PLATFORMS = {
    "yahoo_jp": "news.yahoo.co.jp",
}
JP_RSS = "https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"

# ── 品牌關鍵字（只搜品牌名）────────────────────────────────────────────────────

TW_BRAND_KEYWORDS = [
    # 速食／便利商店大型品牌
    "麥當勞", "肯德基", "摩斯漢堡", "MOS Burger",
    "7-ELEVEN", "7-11", "全家", "FamilyMart",
    # 拉亞系列
    "拉亞", "拉亞漢堡", "拉雅", "Laya", "Laya Burger",
    # 拉亞聯名產品（每次有新聯名在此新增）
    "拉亞KITKAT", "KitKat貝果", "杜拜開心果巧克力早餐",
    # 早餐連鎖
    "麥味登", "Q Burger", "QBurger", "弘爺", "晨間廚房",
    "美而美", "美芝城", "萬佳香", "早安公雞", "呷尚寶", "JSP", "蕃茄村",
    # 飲料連鎖
    "50嵐", "清心福全", "CoCo都可", "天仁茗茶", "大苑子",
    "迷客夏", "茶湯會", "珍煮丹", "鮮芋仙", "麻古茶坊",
]

JP_BRAND_KEYWORDS = [
    "マクドナルド", "ケンタッキー", "モスバーガー",
    "セブンイレブン", "ファミリーマート", "ローソン",
    "すき家", "吉野家", "松屋", "サイゼリヤ", "ガスト",
]

# ── 第一層過濾：標題必須含品牌名 ─────────────────────────────────────────────

# 台灣品牌識別詞（標題中只要出現其一即視為品牌相關）
TW_BRAND_IDENTIFIERS = [
    "麥當勞", "肯德基", "摩斯", "MOS", "7-ELEVEN", "7-11", "全家", "FamilyMart",
    "拉亞", "Laya", "拉亞KITKAT", "KitKat貝果", "杜拜開心果巧克力早餐",
    "麥味登", "Q Burger", "QBurger", "q burger", "qburger",
    "弘爺", "晨間廚房", "美而美", "美芝城", "萬佳香",
    "早安公雞", "呷尚寶", "JSP", "蕃茄村",
    "50嵐", "清心福全", "CoCo", "大苑子", "迷客夏",
    "茶湯會", "珍煮丹", "鮮芋仙", "麻古",
]

# 日本品牌識別詞
JP_BRAND_IDENTIFIERS = [
    "マクドナルド", "ケンタッキー", "モスバーガー",
    "セブンイレブン", "ファミリーマート", "ローソン",
    "すき家", "吉野家", "松屋", "サイゼリヤ", "ガスト",
]

# ── 日文專屬過濾 ──────────────────────────────────────────────────────────────

# 日文黑名單：含以下詞彙直接排除（體育賽事 / 犯罪）
JP_BLACKLIST = [
    # 體育
    "テニス", "競馬", "ダービー", "騎手", "レース", "スポーツ",
    "サッカー", "野球", "バスケ", "ゴルフ", "水泳", "陸上",
    "選手", "監督", "コーチ", "チーム", "リーグ", "試合", "得点",
    # 犯罪 / 社會
    "事件", "逮捕", "詐欺", "裁判", "警察", "死亡", "火災",
]

# 日文必須包含詞：標題需含以下至少一個詞（確保為餐飲 / 零售新聞）
JP_REQUIRED = [
    "メニュー", "新商品", "キャンペーン", "限定", "販売", "発売",
    "コラボ", "新発売", "期間限定", "セール", "割引", "クーポン",
    "店舗", "加盟", "フランチャイズ", "新店", "オープン",
]

# ── 第二層過濾：標題黑名單 ────────────────────────────────────────────────────

BLACKLIST = [
    # 事故 / 暴力 / 犯罪
    "死亡", "傷亡", "車禍", "事故", "火災", "槍擊", "爆炸", "颱風", "地震",
    "逮捕", "詐騙", "犯罪", "警察", "急診", "手術", "病逝",
    "性侵", "性暴力", "不起訴",
    # 司法 / 政治
    "檢察", "法院", "司法", "選舉", "政治", "融資", "股票", "股價", "IPO",
    # 公衛 / 防疫
    "腸病毒", "洗手", "公衛", "衛生局", "防疫", "疾管", "校園宣導",
    # 公益 / 非餐飲促銷
    "慈善", "公益", "歸零", "點數清零", "好市多", "逾期",
]

# 標題末尾「 - 來源名稱」去除
SOURCE_SUFFIX_RE = re.compile(r"\s*[-–]\s*[^-–]{2,40}\s*$")


# ── 特殊關鍵字額外驗證 ───────────────────────────────────────────────────────
# 「全家」本身含義廣泛（全家人、全家福），搜尋命中後需確認標題也包含便利商店相關詞

KEYWORD_EXTRA_RULES = {
    "全家": ["FamilyMart", "便利商店", "集點", "新品", "優惠", "門市", "限定"],
}


def passes_extra_rule(keyword: str, title: str) -> bool:
    """若該關鍵字有額外驗證規則，標題需另外包含至少一個輔助詞。"""
    extra = KEYWORD_EXTRA_RULES.get(keyword)
    if extra is None:
        return True
    return any(w in title for w in extra)


# ── 過濾函式 ──────────────────────────────────────────────────────────────────

def has_brand(title: str, identifiers: list) -> bool:
    """第一層：標題必須含至少一個品牌識別詞。"""
    return any(ident in title for ident in identifiers)


def not_blacklisted(title: str) -> bool:
    """第二層：標題不含黑名單詞。"""
    if title.startswith("討論牆 |"):   # LINE Today 討論牆功能，排除
        return False
    return not any(kw in title for kw in BLACKLIST)


# ── 日期處理 ──────────────────────────────────────────────────────────────────

def parse_rss_date(pub_date: str) -> str:
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y-%m-%d")
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
        print(f"    ⚠  RSS 失敗（{query[:30]}）：{e}")
        return []


def clean_title(raw: str) -> str:
    return SOURCE_SUFFIX_RE.sub("", raw).strip()


def parse_items(
    items: list,
    platform: str,
    keyword: str,
    market: str,
    brand_identifiers: list,
    limit: int = MAX_PER_KEYWORD,
    extra_blacklist: list = None,
    required_words: list = None,
) -> tuple[list, int, int]:
    """
    解析 RSS item，套用雙層過濾。
    extra_blacklist : 額外黑名單（如日文體育 / 犯罪詞）
    required_words  : 標題必須含至少一個詞才收錄（如日文餐飲相關詞）
    回傳 (通過的文章列表, 黑名單排除數, 無品牌排除數)
    """
    if extra_blacklist is None:
        extra_blacklist = []
    if required_words is None:
        required_words = []

    results       = []
    blacklisted_n = 0
    no_brand_n    = 0

    for item in items:
        if len(results) >= limit:
            break

        pub_date = item.findtext("pubDate", "")
        date_str = parse_rss_date(pub_date)
        if not is_within_7_days(date_str):
            continue

        raw_title = item.findtext("title", "")
        title     = clean_title(raw_title)
        if not title:
            continue

        url = item.findtext("link", "")
        if not url or "news.google.com" not in url:
            url = item.findtext("guid", "") or url
        summary = re.sub(
            r"<[^>]+>", "",
            (item.findtext("description") or "")
        )[:200].strip()

        # 第二層：主黑名單 + 額外黑名單
        if not not_blacklisted(title):
            blacklisted_n += 1
            continue
        if extra_blacklist and any(w in title for w in extra_blacklist):
            blacklisted_n += 1
            continue

        # 第一層：標題必須含品牌名
        if not has_brand(title, brand_identifiers):
            no_brand_n += 1
            continue

        # 必須包含詞驗證（日文餐飲相關詞）
        if required_words and not any(w in title for w in required_words):
            no_brand_n += 1
            continue

        # 特殊關鍵字額外驗證（如「全家」需同時包含便利商店相關詞）
        if not passes_extra_rule(keyword, title):
            no_brand_n += 1
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

    return results, blacklisted_n, no_brand_n


# ── 直接 RSS 抓取與過濾 ────────────────────────────────────────────────────────

def fetch_direct_rss_items(url: str, source_name: str) -> list:
    """直接抓取 RSS 來源（不帶查詢參數），回傳所有 item。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        return root.findall(".//item")
    except Exception as e:
        print(f"    ⚠  RSS 失敗（{source_name}）：{e}")
        return []


def parse_items_direct(
    items: list,
    source_name: str,
    market: str = "台灣",
    limit: int = MAX_PER_SOURCE,
) -> tuple[list, int, int]:
    """
    直接 RSS 過濾：
    ① 標題不含黑名單詞
    ② 標題含至少一個台灣品牌識別詞
    與 Google News 流程邏輯一致，但 URL 直接使用 <link>，
    platform 統一為 "tw_rss"，keyword 取命中的第一個品牌識別詞。
    """
    results       = []
    blacklisted_n = 0
    no_brand_n    = 0

    for item in items:
        if len(results) >= limit:
            break

        pub_date = item.findtext("pubDate", "")
        date_str = parse_rss_date(pub_date)
        if not is_within_7_days(date_str):
            continue

        raw_title = item.findtext("title", "")
        title     = clean_title(raw_title)
        if not title:
            continue

        # 直接 RSS 的 <link> 就是真實 URL
        url = (item.findtext("link") or "").strip()
        if not url:
            url = (item.findtext("guid") or "").strip()
        summary = re.sub(
            r"<[^>]+>",
            "",
            (item.findtext("description") or ""),
        )[:200].strip()

        # ① 黑名單過濾
        if not not_blacklisted(title):
            blacklisted_n += 1
            continue

        # ② 必須含品牌名
        if not has_brand(title, TW_BRAND_IDENTIFIERS):
            no_brand_n += 1
            continue

        matched_brand = next(
            (b for b in TW_BRAND_IDENTIFIERS if b in title), ""
        )
        results.append({
            "title":    title,
            "url":      url,
            "platform": "tw_rss",
            "source":   source_name,
            "date":     date_str,
            "summary":  summary,
            "keyword":  matched_brand,
            "market":   market,
        })

    return results, blacklisted_n, no_brand_n


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
    print(f"  過濾策略：① 標題含品牌名  ② 標題不含黑名單詞")
    print(f"{'═' * 60}")

    all_results   = []
    tw_yahoo_n    = 0
    tw_line_n     = 0
    tw_rss_n      = 0
    jp_n          = 0
    raw_total     = 0
    total_bl      = 0
    total_nobrand = 0

    # ── 台灣 ─────────────────────────────────────────────────────────────────
    total_tw_q = len(TW_BRAND_KEYWORDS) * len(TW_PLATFORMS)
    done = 0

    print(f"\n  【台灣】{len(TW_BRAND_KEYWORDS)} 個品牌 × {len(TW_PLATFORMS)} 平台 = {total_tw_q} 次查詢")
    print(f"  {'─' * 56}")

    for kw in TW_BRAND_KEYWORDS:
        for platform, site_domain in TW_PLATFORMS.items():
            done += 1
            query = f"{kw} site:{site_domain}"
            items = fetch_rss(TW_RSS, query)
            raw_total += len(items)

            parsed, bl_n, nb_n = parse_items(
                items, platform, kw, "台灣", TW_BRAND_IDENTIFIERS
            )
            total_bl      += bl_n
            total_nobrand += nb_n

            if platform == "yahoo_news":
                tw_yahoo_n += len(parsed)
            else:
                tw_line_n  += len(parsed)
            all_results.extend(parsed)

            label = "Yahoo" if platform == "yahoo_news" else "LINE "
            print(f"  [{done:>3}/{total_tw_q}] {label} ｜ {kw:<14} → {len(parsed):>2} 篇")

            if done < total_tw_q:
                time.sleep(2)

    # ── 日本 ─────────────────────────────────────────────────────────────────
    total_jp_q = len(JP_BRAND_KEYWORDS)
    done_jp    = 0

    print(f"\n  【日本】{len(JP_BRAND_KEYWORDS)} 個品牌 × 1 平台 = {total_jp_q} 次查詢")
    print(f"  {'─' * 56}")

    for kw in JP_BRAND_KEYWORDS:
        done_jp += 1
        query = f"{kw} site:news.yahoo.co.jp"
        items = fetch_rss(JP_RSS, query)
        raw_total += len(items)

        parsed, bl_n, nb_n = parse_items(
            items, "yahoo_jp", kw, "日本", JP_BRAND_IDENTIFIERS,
            extra_blacklist=JP_BLACKLIST,
            required_words=JP_REQUIRED,
        )
        total_bl      += bl_n
        total_nobrand += nb_n
        jp_n          += len(parsed)
        all_results.extend(parsed)

        print(f"  [{done_jp:>2}/{total_jp_q}] Yahoo JP ｜ {kw:<14} → {len(parsed):>2} 篇")

        if done_jp < total_jp_q:
            time.sleep(2)

    # ── 台灣直接 RSS（東森 / 年代 / 民視 / 三立 / TVBS / 中時 / 自由 / ET / 聯合）────
    tw_rss_n = 0
    print(f"\n  【台灣直接 RSS】{len(TW_DIRECT_RSS)} 個來源")
    print(f"  {'─' * 56}")

    for source_name, rss_url in TW_DIRECT_RSS.items():
        print(f"  {source_name:<12} ...", end=" ", flush=True)
        items = fetch_direct_rss_items(rss_url, source_name)
        if not items:
            print("（無資料）")
            continue

        parsed, bl_n, nb_n = parse_items_direct(items, source_name)
        total_bl      += bl_n
        total_nobrand += nb_n
        tw_rss_n      += len(parsed)
        all_results.extend(parsed)

        print(f"原始 {len(items):>4} 篇 → 通過 {len(parsed):>2} 篇")
        time.sleep(1)   # 對各站台禮貌性延遲

    # ── 去重 + 排序 ───────────────────────────────────────────────────────────
    before_dedup = len(all_results)
    all_results  = dedup(all_results)
    all_results.sort(key=lambda p: p.get("date", ""), reverse=True)

    # ── 輸出 ─────────────────────────────────────────────────────────────────
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"news_{TODAY}.json"
    out_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tw_final = sum(1 for p in all_results if p["market"] == "台灣")
    jp_final = sum(1 for p in all_results if p["market"] == "日本")
    tw_rss_final = sum(1 for p in all_results if p.get("platform") == "tw_rss")

    print(f"\n{'─' * 60}")
    print(f"  RSS 原始         ：{raw_total} 篇")
    print(f"  黑名單排除       ：{total_bl} 篇")
    print(f"  無品牌名排除     ：{total_nobrand} 篇")
    print(f"  去重排除         ：{before_dedup - len(all_results)} 篇")
    print(f"  ─────────────────────────────────────────────────")
    print(f"  台灣新聞         ：{tw_final} 篇（Yahoo {tw_yahoo_n} / LINE {tw_line_n} / 直接RSS {tw_rss_final}）")
    print(f"  日本新聞         ：{jp_final} 篇")
    print(f"  總計             ：{len(all_results)} 篇")
    print(f"  輸出             ：{out_path}")

    # 前 10 篇標題確認品質（全部）
    print(f"\n  【前 10 篇標題確認（全部）】")
    print(f"  {'─' * 56}")
    for i, p in enumerate(all_results[:10], 1):
        market_tag = f"[{p['market']}]"
        plat_map   = {
            "yahoo_news": "Yahoo TW ",
            "line_today":  "LINE Today",
            "yahoo_jp":   "Yahoo JP ",
        }
        plat_tag = plat_map.get(p["platform"], p["platform"])
        print(f"  {i:>2}. [{plat_tag}]{market_tag} {p['title'][:45]}")
        print(f"      {p['date']}  keyword={p['keyword']}")

    # 前 10 篇日文標題確認（過濾後品質確認）
    jp_results = [p for p in all_results if p["market"] == "日本"]
    print(f"\n  【前 10 篇日文新聞標題確認（過濾後）】")
    print(f"  {'─' * 56}")
    if jp_results:
        for i, p in enumerate(jp_results[:10], 1):
            print(f"  {i:>2}. {p['title'][:50]}")
            print(f"      {p['date']}  keyword={p['keyword']}")
    else:
        print("  （無日文新聞）")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
