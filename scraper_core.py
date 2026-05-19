# -*- coding: utf-8 -*-
"""
scraper_core.py — 이너앱(InnerApp) 수집 엔진 코어
- iOS(iTunes Search API) + Google Play(google-play-scraper) 통합 수집
- 구글플레이 패키지명 자동 역추적 (하드코딩 패키지명 불일치 문제 해결)
- 게임 카테고리 포함 전 카테고리 지원
"""
import time
import json
import random
import requests
from urllib.parse import quote

try:
    from google_play_scraper import app as gp_app, reviews as gp_reviews, search as gp_search, Sort
except ImportError:
    raise SystemExit("google-play-scraper 미설치: pip install google-play-scraper")

# ─────────────────────────────────────────────────────────────
# 카테고리 정의 (게임 추가됨)
# ─────────────────────────────────────────────────────────────
CATEGORIES = {
    "sns":           "소셜·커뮤니티",
    "entertainment": "엔터테인먼트",
    "shopping":      "쇼핑",
    "food":          "음식·배달",
    "finance":       "금융·재테크",
    "game":          "게임",
    "productivity":  "생산성·도구",
    "life":          "라이프스타일",
    "education":     "교육",
    "health":        "건강·운동",
    "travel":        "여행·지도",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


# ─────────────────────────────────────────────────────────────
# iOS 수집 (iTunes Search API)
# ─────────────────────────────────────────────────────────────
def fetch_ios_by_id(itunes_id):
    """iTunes ID로 iOS 앱 정보 조회."""
    url = f"https://itunes.apple.com/lookup?id={itunes_id}&country=kr"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        if data.get("resultCount", 0) == 0:
            return None
        return _parse_ios(data["results"][0])
    except Exception as e:
        print(f"   ⚠️ iOS ID 조회 실패({itunes_id}): {e}")
        return None


def fetch_ios_by_term(term):
    """이름으로 iOS 앱 검색 (신규 앱 자동 수집용)."""
    url = (f"https://itunes.apple.com/search?term={quote(term)}"
           f"&country=kr&entity=software&limit=1")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json()
        if data.get("resultCount", 0) == 0:
            return None
        return _parse_ios(data["results"][0])
    except Exception as e:
        print(f"   ⚠️ iOS 검색 실패({term}): {e}")
        return None


def _parse_ios(res):
    """iTunes 응답 → 표준 dict. bundleId를 같이 반환해 안드로이드 역추적에 활용."""
    return {
        "icon":       res.get("artworkUrl512") or res.get("artworkUrl100", ""),
        "desc":       (res.get("description", "") or "").replace("\n", " ")[:300],
        "developer":  res.get("sellerName", ""),
        "screenshots": (res.get("screenshotUrls", []) or [])[:3],
        "iosUrl":     res.get("trackViewUrl", ""),
        "bundleId":   res.get("bundleId", ""),   # ★ 안드로이드 패키지 추론 단서
        "trackName":  res.get("trackName", ""),
        "spec_ios": {
            "ver":  res.get("version", "-"),
            "os":   f"iOS {res.get('minimumOsVersion','-')} 이상",
            "size": _human_size(res.get("fileSizeBytes")),
        },
    }


def _human_size(b):
    try:
        mb = int(b) / (1024 * 1024)
        return f"{mb:.1f}MB"
    except (TypeError, ValueError):
        return "-"


# ─────────────────────────────────────────────────────────────
# Google Play 수집 — 핵심 개선부
# ─────────────────────────────────────────────────────────────
def _name_similar(a, b):
    """앱 이름 느슨한 일치 검사 (검색 첫 결과 맹신 방지)."""
    if not a or not b:
        return False
    a = "".join(a.lower().split())
    b = "".join(b.lower().split())
    return a in b or b in a or a[:4] == b[:4]


def resolve_android_package(known_pkg, name_kr, name_en, bundle_id=""):
    """
    안드로이드 '진짜' 패키지명을 다단계로 확정한다.
    1) 하드코딩 패키지명 시도
    2) iOS bundleId 시도 (보통 동일 — com.kakao.talk 등)
    3) 한글명 / 영문명 검색 후 이름 유사도 검증
    실패 시 None.
    """
    # 1단계: 알려진 패키지명
    for pkg in [known_pkg, bundle_id]:
        if pkg and _try_gp_app(pkg):
            return pkg

    # 2단계: 이름 검색 + 유사도 검증
    for term in [name_kr, name_en]:
        if not term:
            continue
        try:
            hits = gp_search(term, lang="ko", country="kr", n_hits=5)
        except Exception:
            time.sleep(1)
            continue
        for h in hits:
            title = h.get("title", "")
            if _name_similar(term, title) or _name_similar(name_kr, title):
                return h["appId"]
        # 유사한 게 없으면 그래도 1순위는 후보로
        if hits:
            return hits[0]["appId"]
    return None


def _try_gp_app(pkg):
    """패키지 존재 여부만 가볍게 확인."""
    try:
        gp_app(pkg, lang="ko", country="kr")
        return True
    except Exception:
        return False


def _gp_app_retry(pkg, max_try=3):
    """
    클라우드(GitHub Actions 등) 데이터센터 IP는 차단/지연이 잦다.
    지수 백오프로 재시도한다. 실패 시 마지막 예외를 올린다.
    """
    last = None
    for attempt in range(max_try):
        try:
            return gp_app(pkg, lang="ko", country="kr")
        except Exception as e:
            last = e
            wait = (2 ** attempt) * 3 + random.uniform(0, 3)
            print(f"   ↻ 재시도 {attempt+1}/{max_try} — {wait:.0f}초 대기")
            time.sleep(wait)
    raise last


def fetch_android(known_pkg, name_kr, name_en, bundle_id=""):
    """
    안드로이드 앱 정보 수집. 리뷰 수집이 실패해도 본문은 살린다.
    (기존 parse_android는 reviews 실패 시 전체 None → 절반 누락의 주범)
    """
    pkg = resolve_android_package(known_pkg, name_kr, name_en, bundle_id)
    if not pkg:
        return None, None

    try:
        res = _gp_app_retry(pkg)
    except Exception as e:
        print(f"   ⚠️ 안드로이드 본문 조회 실패({pkg}): {e}")
        return None, pkg

    # 리뷰는 별도 try — 실패해도 앱 데이터는 유지
    review_list = []
    try:
        rv, _ = gp_reviews(pkg, lang="ko", country="kr",
                           sort=Sort.MOST_RELEVANT, count=10)
        review_list = [
            {"user": r["userName"], "text": r["content"], "rating": r["score"]}
            for r in rv if r.get("content")
        ]
    except Exception:
        print(f"   ℹ️ 리뷰 수집 생략({pkg}) — 본문은 정상 수집")

    data = {
        "icon":       res.get("icon", ""),
        "desc":       (res.get("description", "") or "").replace("\n", " ")[:300],
        "developer":  res.get("developer", ""),
        "screenshots": (res.get("screenshots", []) or [])[:3],
        "androidUrl": f"https://play.google.com/store/apps/details?id={pkg}",
        "reviews":    review_list,
        "spec_and": {
            "ver":  res.get("version", "-") or "-",
            "os":   _android_min_os(res),
            "size": res.get("size", "-") or "-",
        },
    }
    return data, pkg


def _android_min_os(res):
    txt = res.get("androidVersionText") or res.get("androidVersion") or "-"
    if txt and txt != "-" and "이상" not in str(txt):
        return f"Android {txt} 이상"
    return txt if txt else "-"


# ─────────────────────────────────────────────────────────────
# 통합: 앱 1개 완전체 수집
# ─────────────────────────────────────────────────────────────
def build_app(app_id, name_kr, name_en, itunes_id, known_pkg, cat):
    """한 앱의 iOS+Android 통합 레코드 생성."""
    print(f"   • {name_kr} 수집 중...")

    ios = fetch_ios_by_id(itunes_id) if itunes_id else fetch_ios_by_term(name_kr)
    time.sleep(0.4)

    bundle_id = ios.get("bundleId", "") if ios else ""
    android, real_pkg = fetch_android(known_pkg, name_kr, name_en, bundle_id)
    time.sleep(0.4)

    if not ios and not android:
        print(f"   ✗ {name_kr}: iOS/Android 모두 실패 — 스킵")
        return None

    # iOS 우선, 없으면 Android 값으로 채움
    base = ios or {}
    record = {
        "id":          app_id,
        "name":        name_kr,
        "cat":         cat,
        "icon":        (ios or android or {}).get("icon", ""),
        "developer":   base.get("developer") or (android or {}).get("developer", ""),
        "desc":        base.get("desc") or (android or {}).get("desc", ""),
        "iosUrl":      base.get("iosUrl", ""),
        "androidUrl":  (android or {}).get("androidUrl", ""),
        "pcUrl":       "",
        "screenshots": base.get("screenshots") or (android or {}).get("screenshots", []),
        "reviews":     (android or {}).get("reviews", []),
        "spec_ios":    base.get("spec_ios", {"ver": "-", "os": "-", "size": "-"}),
        "spec_and":    (android or {}).get("spec_and", {"ver": "-", "os": "-", "size": "-"}),
        "installSteps": [
            f"앱스토어/플레이스토어에서 '{name_kr}' 검색",
            "설치 버튼을 눌러 다운로드",
            "앱 실행 후 안내에 따라 이용 시작",
        ],
        "bg": "#F9FAFB",
        "fallback": "📱",
    }
    ok_ios = record["spec_ios"]["ver"] != "-"
    ok_and = record["spec_and"]["ver"] != "-"
    print(f"   ✓ {name_kr}: iOS={'O' if ok_ios else 'X'} "
          f"Android={'O' if ok_and else 'X'} pkg={real_pkg}")
    return record
