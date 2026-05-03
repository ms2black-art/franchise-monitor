#!/usr/bin/env python3
"""
社群平台爬蟲（bycrawl API）
整合 Threads、Facebook、Instagram，抓最近 7 天的關鍵字相關內容。

注意：端點根據 bycrawl 官方文件（2026-03）確認如下
  Threads   → GET /threads/posts/search?q=xxx&search_type=recent（3 credits/次）
  Facebook  → GET /facebook/posts/search?q=xxx（2 credits/次，每次最多 10 筆）
  Instagram → GET /instagram/tags/search?q=xxx（2 credits/次）
             ⚠ Instagram 無關鍵字貼文搜尋端點；此端點回傳 hashtag 統計（名稱、貼文數），
               可用於趨勢分析，不包含個別貼文內容。

執行前置作業：
  pip3 install requests
  export BYCRAWL_API_KEY='sk_byc_...'

執行方式：
  python3 research-db/social_scraper.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("錯誤：找不到必要套件。")
    print("請先執行：pip3 install requests")
    sys.exit(1)

# ── 路徑 ─────────────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR.parent / "data"

# ── API 設定 ─────────────────────────────────────────────────────────────────

API_BASE        = "https://api.bycrawl.com"
API_TIMEOUT     = 60     # 秒
PLATFORM_DELAY  = 3.0    # 平台之間的等待秒數

# ── 搜尋關鍵字設定 ────────────────────────────────────────────────────────────

THREADS_KEYWORDS = [
    "拉亞", "麥味登", "Q Burger", "弘爺", "加盟", "早餐加盟", "創業加盟",
    "KITKAT貝果", "杜拜貝果", "拉亞杜拜", "拉亞KITKAT",
]

# 直接爬取品牌粉絲專頁
# 端點：GET https://api.bycrawl.com/facebook/users/{username}/posts
# Header：Authorization: Bearer {BYCRAWL_API_KEY}
FACEBOOK_PAGES = [
    {"username": "layaburger2002", "name": "拉亞漢堡"},   # 確認有效
    {"username": "MWD.tw",        "name": "麥味登"},      # 備用（目前 0 篇）
    {"username": "qburger2013",   "name": "Q Burger"},    # 備用（目前 0 篇）
]

POSTS_PER_PAGE = 10   # 每個粉專最多取幾篇貼文

# Instagram tags/search 用的查詢詞（回傳 hashtag 統計，不是個別貼文）
INSTAGRAM_TAGS = [
    # 品牌專屬 hashtag
    "拉亞漢堡", "麥味登", "QBurger",
    # 通用早餐 / 加盟 hashtag
    "早餐加盟", "台灣早餐",
    # 既有 hashtag
    "創業加盟", "餐飲加盟", "手搖飲加盟",
]


# ── 工具函式 ─────────────────────────────────────────────────────────────────

def make_headers(api_key: str) -> dict:
    return {"x-api-key": api_key}


def make_bearer_headers(api_key: str) -> dict:
    """部分端點（如 Facebook users）使用 Bearer Token 格式。"""
    return {"Authorization": f"Bearer {api_key}"}


def is_within_days(iso_str: str, days: int = 7) -> bool:
    """判斷 ISO 8601 時間字串是否在最近 N 天內。"""
    if not iso_str:
        return False
    try:
        dt     = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return dt >= cutoff
    except (ValueError, AttributeError):
        return False


def api_get(url: str, headers: dict, params: Optional[dict] = None) -> Optional[dict]:
    """
    發送 GET 請求，回傳 JSON dict 或 list（包在 dict 裡）。
    失敗時印出錯誤並回傳 None。
    """
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # 統一回傳 dict（list 包成 {"items": [...]}）
        if isinstance(data, list):
            return {"items": data}
        return data
    except requests.Timeout:
        print(f"    ✗  逾時（>{API_TIMEOUT}s）：{url}")
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response else ""
        print(f"    ✗  HTTP {e.response.status_code}：{body}")
    except requests.RequestException as e:
        print(f"    ✗  網路錯誤：{e}")
    return None


# ── Threads ──────────────────────────────────────────────────────────────────

def scrape_threads(api_key: str) -> list[dict]:
    """
    端點：GET /threads/posts/search?q=xxx&search_type=recent
    回傳欄位：text、author、url、created_at、likes
    """
    headers  = make_headers(api_key)
    results  = []
    seen_ids: set = set()

    print(f"\n  ── [Threads] 搜尋 {len(THREADS_KEYWORDS)} 個關鍵字 ──")

    for keyword in THREADS_KEYWORDS:
        print(f"    「{keyword}」...", end=" ", flush=True)
        data = api_get(
            f"{API_BASE}/threads/posts/search",
            headers,
            params={"q": keyword, "search_type": "recent"},
        )
        if not data:
            print("失敗")
            continue

        posts     = data.get("posts", [])
        new_count = 0
        for post in posts:
            if not is_within_days(post.get("createdAt", "")):
                continue
            post_id = post.get("id")
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            code     = post.get("code", "")
            user     = post.get("user", {})
            username = user.get("username", "")
            stats    = post.get("stats", {})

            results.append({
                "platform":   "threads",
                "keyword":    keyword,
                "text":       (post.get("text") or "")[:300],
                "author":     username,
                "url":        f"https://www.threads.net/@{username}/post/{code}" if code else "",
                "created_at": post.get("createdAt", ""),
                "likes":      stats.get("likes", 0),
                "replies":    stats.get("replies", 0),
            })
            new_count += 1

        print(f"找到 {new_count} 篇")

    print(f"  [Threads] 共 {len(results)} 篇（7天內，去重後）")
    return results


# ── Facebook 粉專 ─────────────────────────────────────────────────────────────

def scrape_facebook(api_key: str) -> list[dict]:
    """
    端點：GET https://api.bycrawl.com/facebook/users/{username}/posts
    Header：Authorization: Bearer {api_key}
    直接爬取品牌粉絲專頁公開貼文，每個粉專取最新 POSTS_PER_PAGE 篇。
    0 篇時靜默跳過；API 失敗時同樣跳過，不中斷流程。
    """
    headers = make_bearer_headers(api_key)
    results: list[dict] = []

    print(f"\n  ── [Facebook 粉專] 抓取 {len(FACEBOOK_PAGES)} 個品牌粉專 ──")

    for page in FACEBOOK_PAGES:
        username = page["username"]
        name     = page["name"]
        try:
            resp = requests.get(
                f"{API_BASE}/facebook/users/{username}/posts",
                headers=headers,
                timeout=API_TIMEOUT,
            )
            print(f"    [{name}] @{username} ... HTTP {resp.status_code}", end=" ", flush=True)
            data  = resp.json()
            posts = data.get("posts", data.get("items", data.get("data", [])))

            if not posts:
                print("→ 0 篇，跳過")
                continue

            new_count = 0
            for p in posts[:POSTS_PER_PAGE]:
                post_id  = p.get("id", "")
                text     = (p.get("text") or p.get("message") or "").strip()
                raw_date = p.get("created_time", p.get("createdAt", p.get("created_at", "")))
                results.append({
                    # 標準欄位（用戶要求格式）
                    "title":         text[:60],
                    "content":       text,
                    "platform":      "Facebook",
                    "source":        "Facebook粉專",
                    "brand":         name,
                    "date":          raw_date[:10] if raw_date else "",
                    "url":           (
                        p.get("url")
                        or p.get("permalinkUrl")
                        or (f"https://www.facebook.com/{username}/posts/{post_id}" if post_id else "")
                    ),
                    "likes":         p.get("likes_count",    p.get("likeCount",    p.get("likes",    0))),
                    "comment_count": p.get("comments_count", p.get("commentCount", p.get("comments", 0))),
                    # build.py 相容欄位（不要移除）
                    "text":          text,
                    "created_at":    raw_date,
                    "comments":      p.get("comments_count", p.get("commentCount", p.get("comments", 0))),
                })
                new_count += 1

            latest_title = results[-new_count]["title"] if new_count else ""
            print(f"→ {new_count} 篇")
            if latest_title:
                print(f"      最新：{latest_title}")

        except Exception as e:
            print(f"    [{name}] 失敗：{e}")

        time.sleep(1.5)   # 每個粉專間隔，避免觸發速率限制

    print(f"  [Facebook 粉專] 共 {len(results)} 篇")
    return results


# ── Instagram ─────────────────────────────────────────────────────────────────

def scrape_instagram(api_key: str) -> list[dict]:
    """
    端點：GET /instagram/tags/search?q=xxx
    ⚠ 回傳 hashtag 統計資料（名稱、貼文總數），非個別貼文。
      bycrawl 目前不提供以 hashtag 搜尋個別貼文的端點。
    """
    headers = make_headers(api_key)
    results = []

    print(f"\n  ── [Instagram] 搜尋 {len(INSTAGRAM_TAGS)} 個 hashtag ──")
    print("    ※ 回傳 hashtag 統計資料（非個別貼文）")

    for tag in INSTAGRAM_TAGS:
        print(f"    #{tag}...", end=" ", flush=True)
        data = api_get(
            f"{API_BASE}/instagram/tags/search",
            headers,
            params={"q": tag},
        )
        if not data:
            print("失敗")
            continue

        tags      = data.get("tags", [])
        new_count = 0
        for t in tags:
            name = t.get("name", "")
            results.append({
                "platform":             "instagram",
                "searched_keyword":     tag,
                "tag_name":             name,
                "media_count":          t.get("mediaCount", 0),
                "formatted_media_count": t.get("formattedMediaCount", ""),
                "url":                  f"https://www.instagram.com/explore/tags/{name}/",
            })
            new_count += 1

        print(f"找到 {new_count} 個相關 hashtag")

    print(f"  [Instagram] 共 {len(results)} 筆 hashtag 資料")
    return results


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.environ.get("BYCRAWL_API_KEY", "").strip()
    if not api_key:
        print("錯誤：未偵測到 BYCRAWL_API_KEY 環境變數。")
        print("請先執行：export BYCRAWL_API_KEY='sk_byc_...'")
        sys.exit(1)

    today       = datetime.now().strftime("%Y-%m-%d")
    output_file = DATA_DIR / f"social_{today}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═' * 62}")
    print(f"  社群平台爬蟲（bycrawl API）·  日期：{today}")
    print(f"  平台：Threads / Facebook粉專（{len(FACEBOOK_PAGES)} 個）/ Instagram")
    print(f"  輸出：{output_file}")
    print(f"{'═' * 62}")

    # Threads
    threads_posts = scrape_threads(api_key)

    print(f"\n  等待 {PLATFORM_DELAY:.0f} 秒...")
    time.sleep(PLATFORM_DELAY)

    # Facebook
    fb_posts = scrape_facebook(api_key)

    print(f"\n  等待 {PLATFORM_DELAY:.0f} 秒...")
    time.sleep(PLATFORM_DELAY)

    # Instagram
    ig_tags = scrape_instagram(api_key)

    # 整合輸出
    output = {
        "meta": {
            "date":                    today,
            "generated_at":            datetime.now().isoformat(timespec="seconds"),
            "threads_count":           len(threads_posts),
            "facebook_page_count":     len(fb_posts),
            "facebook_pages_scraped":  [p["username"] for p in FACEBOOK_PAGES],
            "instagram_hashtag_count": len(ig_tags),
        },
        "threads":   threads_posts,
        "facebook":  fb_posts,
        "instagram": ig_tags,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = len(threads_posts) + len(fb_posts)
    page_labels = "、".join(p["brand"] for p in FACEBOOK_PAGES)
    print(f"\n{'═' * 62}")
    print(f"  完成！Threads {len(threads_posts)} 篇 ／ Facebook粉專 {len(fb_posts)} 篇 ／ Instagram {len(ig_tags)} 個 hashtag")
    print(f"  抓取粉專：{page_labels}")
    print(f"  貼文總計：{total} 篇")
    print(f"  結果存於：{output_file}")
    print(f"{'═' * 62}\n")


if __name__ == "__main__":
    main()
