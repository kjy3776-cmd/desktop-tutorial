# -*- coding: utf-8 -*-
"""
update_candidates.py — 앱스토어 인기 차트에서 후보 자동 수집

매주 실행해서 candidates.json을 자동으로 채운다.
이미 등록됐거나 이미 후보에 있는 앱은 제외.

수집 방법:
  1. iTunes RSS API — 카테고리별 인기 앱 TOP 100
  2. Google Play 검색 — 카테고리별 인기 앱 검색
  3. Claude API — 큐레이션 추천 (ANTHROPIC_API_KEY 있을 때)
"""
import os
import json
import time
import random
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATES_FILE = os.path.join(BASE_DIR, "candidates.json")
APPS_DATA_FILE  = os.path.join(BASE_DIR, "apps_data.js")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
}

# iTunes 카테고리 ID → 이너앱 카테고리
ITUNES_CATS = {
    "6014": "game",
    "6007": "productivity",
    "6005": "sns",
    "6016": "entertainment",
    "6024": "shopping",
    "6015": "finance",
    "6013": "health",
    "6017": "education",
    "6003": "life",
    "6006": "travel",
}

# Google Play 카테고리 → 이너앱 카테고리
GP_CATS = {
    "GAME":              "game",
    "PRODUCTIVITY":      "productivity",
    "SOCIAL":            "sns",
    "ENTERTAINMENT":     "entertainment",
    "SHOPPING":          "shopping",
    "FINANCE":           "finance",
    "HEALTH_AND_FITNESS":"health",
    "EDUCATION":         "education",
    "LIFESTYLE":         "life",
    "TRAVEL_AND_LOCAL":  "travel",
}


def load_existing():
    """이미 등록된 앱 이름 + 이미 후보인 앱 이름 세트 반환."""
    existing = set()

    # apps_data.js에서 등록된 앱
    if os.path.exists(APPS_DATA_FILE):
        raw = open(APPS_DATA_FILE, encoding="utf-8").read()
        raw = raw.split("=", 1)[1].strip().rstrip(";")
        apps = json.loads(raw)
        for a in apps:
            existing.add(a["name"].lower())

    # candidates.json에서 후보
    if os.path.exists(CANDIDATES_FILE):
        cands = json.load(open(CANDIDATES_FILE, encoding="utf-8"))
        for c in cands:
            existing.add(c[0].lower())

    return existing


def load_candidates():
    if os.path.exists(CANDIDATES_FILE):
        return json.load(open(CANDIDATES_FILE, encoding="utf-8"))
    return []


def save_candidates(cands):
    with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
        json.dump(cands, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
# 1. iTunes RSS API (가장 안정적)
# ─────────────────────────────────────────────────────────────
def fetch_itunes_chart(cat_id: str, cat_name: str, limit: int = 100) -> list:
    """iTunes 인기 차트에서 앱 목록 가져오기."""
    url = (f"https://itunes.apple.com/kr/rss/topfreeapplications/"
           f"genre={cat_id}/limit={limit}/json")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        entries = r.json().get("feed", {}).get("entry", [])
        results = []
        for e in entries:
            name    = e.get("im:name", {}).get("label", "")
            itunes_id = e.get("id", {}).get("attributes", {}).get("im:id", "")
            # 번들 ID는 없으니 빈값 — 수집 시 자동 탐색
            if name and itunes_id:
                results.append((name, "", itunes_id, "", cat_name))
        return results
    except Exception as e:
        print(f"  iTunes 오류({cat_name}): {e}")
        return []


# ─────────────────────────────────────────────────────────────
# 2. Google Play Scraper
# ─────────────────────────────────────────────────────────────
def fetch_gplay_chart(gp_cat: str, cat_name: str, limit: int = 50) -> list:
    """구글플레이 카테고리 인기 앱 가져오기."""
    try:
        from google_play_scraper import search
        # 카테고리명으로 검색
        results = search(gp_cat.lower().replace("_", " "),
                         lang="ko", country="kr", n_hits=limit)
        return [
            (r["title"], "", "", r["appId"], cat_name)
            for r in results if r.get("title") and r.get("appId")
        ]
    except Exception as e:
        print(f"  Google Play 오류({cat_name}): {e}")
        return []


# ─────────────────────────────────────────────────────────────
# 3. Claude API 큐레이션 (보조)
# ─────────────────────────────────────────────────────────────
def fetch_claude_recommendations(existing_names: set) -> list:
    """Claude API로 이너앱에 없는 인기 앱 추천 받기."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return []

    existing_list = ", ".join(sorted(existing_names)[:30])
    prompt = f"""이너앱(innerapple.com)은 한국에서 인기 있는 앱을 소개하는 사이트입니다.

현재 등록된 앱(일부): {existing_list}

위에 없는 한국에서 인기 있는 앱 20개를 추천해주세요.
카테고리: game, productivity, sns, entertainment, shopping, finance, health, education, life, travel

반드시 JSON 배열만 출력하세요. 다른 텍스트 없이:
[
  {{"name": "앱한글명", "name_en": "AppEnglishName", "itunes_id": "숫자ID", "android_pkg": "com.example.app", "cat": "카테고리"}},
  ...
]

itunes_id와 android_pkg를 정확히 알면 입력하고, 모르면 빈 문자열로."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30
        )
        if r.status_code != 200:
            return []
        text = r.json()["content"][0]["text"].strip()
        # JSON 파싱
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        results = []
        for item in data:
            results.append((
                item.get("name", ""),
                item.get("name_en", ""),
                item.get("itunes_id", ""),
                item.get("android_pkg", ""),
                item.get("cat", "life"),
            ))
        print(f"  Claude 추천: {len(results)}개")
        return results
    except Exception as e:
        print(f"  Claude 오류: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
def run():
    print("=" * 50)
    print("후보 자동 수집 시작")

    existing  = load_existing()
    cands     = load_candidates()
    new_count = 0

    # 1. iTunes 차트
    print("\n[1] iTunes 인기 차트 수집...")
    for cat_id, cat_name in ITUNES_CATS.items():
        apps = fetch_itunes_chart(cat_id, cat_name, limit=100)
        for app in apps:
            name = app[0]
            if name.lower() not in existing and len(name) > 0:
                cands.append(list(app))
                existing.add(name.lower())
                new_count += 1
        time.sleep(random.uniform(0.5, 1.5))

    # 2. Google Play
    print("\n[2] Google Play 차트 수집...")
    for gp_cat, cat_name in GP_CATS.items():
        apps = fetch_gplay_chart(gp_cat, cat_name, limit=30)
        for app in apps:
            name = app[0]
            if name.lower() not in existing and len(name) > 0:
                cands.append(list(app))
                existing.add(name.lower())
                new_count += 1
        time.sleep(random.uniform(1.0, 2.0))

    # 3. Claude 큐레이션
    print("\n[3] Claude 큐레이션...")
    claude_apps = fetch_claude_recommendations(existing)
    for app in claude_apps:
        name = app[0]
        if name and name.lower() not in existing:
            cands.append(list(app))
            existing.add(name.lower())
            new_count += 1

    save_candidates(cands)
    print(f"\n✅ 완료 — 신규 후보 {new_count}개 추가 (총 {len(cands)}개)")
    print("=" * 50)


if __name__ == "__main__":
    run()
