# -*- coding: utf-8 -*-
"""
scraper_core.py — 이너앱(InnerApp) 수집 엔진 코어
- iOS(iTunes Search API) + Google Play(google-play-scraper) 통합 수집
- 구글플레이 패키지명 자동 역추적 (하드코딩 패키지명 불일치 문제 해결)
- 게임 카테고리 포함 전 카테고리 지원
"""
import time
import json
import re
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

# ─────────────────────────────────────────────────────────────
# PC URL 자동 탐지
# ─────────────────────────────────────────────────────────────

# 알려진 앱 → (PC URL, pcType) 매핑
# type: 'download' = 설치 파일 다운로드, 'web' = 웹 브라우저로 바로 사용
KNOWN_PC = {
    # 메신저/소셜
    "카카오톡":   ("https://www.kakaocorp.com/page/service/service/KakaoTalk", "download"),
    "라인":       ("https://line.me/ko/download", "download"),
    "디스코드":   ("https://discord.com/download", "download"),
    "슬랙":       ("https://slack.com/intl/ko-kr/downloads", "download"),
    "텔레그램":   ("https://telegram.org/", "download"),
    "줌":         ("https://zoom.us/download", "download"),
    # 게임 런처/플랫폼
    "스팀":       ("https://store.steampowered.com/about/", "download"),
    "에픽게임즈": ("https://store.epicgames.com/ko/download", "download"),
    "배틀넷":     ("https://www.blizzard.com/ko-kr/apps/battle.net/desktop", "download"),
    # 게임 (PC 클라이언트)
    "이환":       ("https://nte.perfectworld.com/kr/", "download"),
    "원신":       ("https://genshin.hoyoverse.com/ko/download", "download"),
    "로블록스":   ("https://www.roblox.com/download", "download"),
    "마인크래프트":("https://www.minecraft.net/ko-kr/download", "download"),
    "리니지M":    ("", ""),   # 모바일 전용
    "브롤스타즈": ("", ""),   # 모바일 전용
    # 브라우저/도구
    "네이버 웨일":("https://whale.naver.com/", "download"),
    "카카오맵":   ("https://map.kakao.com/", "web"),
    "네이버지도": ("https://map.naver.com/", "web"),
    # 쇼핑/커머스 (웹형)
    "쿠팡":       ("https://www.coupang.com/", "web"),
    "네이버쇼핑": ("https://shopping.naver.com/", "web"),
}

# 패키지명 패턴으로 게임 여부 자동 판단
GAME_DEVELOPER_HINTS = [
    "games", "studio", "entertainment", "interactive",
    "supercell", "nexon", "ncsoft", "netmarble", "com2us",
    "hotta", "mihoyo", "hoYoverse", "devsisters",
]

def make_slug(name_kr: str, name_en: str = "") -> str:
    """앱 슬러그 자동 생성."""
    base = name_en if name_en else name_kr
    s = base.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s or 'app'


# 게임 PC 클라이언트 있는 앱 (모바일 전용 제외)
GAME_PC = {
    "원신":         ("https://genshin.hoyoverse.com/ko/download", "download"),
    "붕괴 스타레일": ("https://hsr.hoyoverse.com/ko-kr/", "download"),
    "젠레스 존 제로":("https://zenless.hoyoverse.com/ko-kr/", "download"),
    "이환":         ("https://nte.perfectworld.com/kr/", "download"),
    "로블록스":     ("https://www.roblox.com/download", "download"),
    "마인크래프트": ("https://www.minecraft.net/ko-kr/download", "download"),
    "포켓몬 GO":    ("", ""),   # 모바일 전용
    "브롤스타즈":   ("", ""),
    "클래시 오브 클랜": ("", ""),
    "쿠키런 킹덤":  ("", ""),
    "서머너즈 워":  ("", ""),
    "리니지M":      ("", ""),
    "메이플스토리M": ("", ""),
    "카트라이더 러쉬플러스": ("", ""),
    "검은사막 모바일": ("", ""),
}

# 개발사 도메인 힌트 → PC URL 자동 추론용
DEV_DOMAIN_MAP = {
    "kakao":      ("https://www.kakao.com/", "web"),
    "naver":      ("https://www.naver.com/", "web"),
    "google":     ("https://www.google.com/", "web"),
    "meta":       ("https://www.facebook.com/", "web"),
    "instagram":  ("https://www.instagram.com/", "web"),
    "youtube":    ("https://www.youtube.com/", "web"),
    "netflix":    ("https://www.netflix.com/kr/", "web"),
    "spotify":    ("https://www.spotify.com/kr/", "web"),
    "coupang":    ("https://www.coupang.com/", "web"),
    "baemin":     ("https://www.baemin.com/", "web"),
    "toss":       ("https://toss.im/", "web"),
    "samsung":    ("https://www.samsung.com/kr/", "web"),
    "microsoft":  ("https://www.microsoft.com/ko-kr/", "web"),
    "adobe":      ("https://www.adobe.com/kr/", "web"),
    "zoom":       ("https://zoom.us/download", "download"),
    "slack":      ("https://slack.com/intl/ko-kr/downloads", "download"),
    "discord":    ("https://discord.com/download", "download"),
    "line":       ("https://line.me/ko/download", "download"),
    "telegram":   ("https://telegram.org/", "download"),
    "dropbox":    ("https://www.dropbox.com/install", "download"),
    "notion":     ("https://www.notion.so/ko-kr/desktop", "download"),
    "evernote":   ("https://evernote.com/download", "download"),
}


def resolve_pc_url(name_kr: str, cat: str, developer: str, android_url: str) -> tuple:
    """
    앱 정보로 PC URL과 타입을 자동 결정.
    우선순위:
      1. KNOWN_PC 테이블 (수동 등록)
      2. 게임 카테고리 → GAME_PC 테이블
      3. 개발사명/패키지명 기반 자동 추론
      4. 웹형 앱은 공식 홈페이지 추론 시도
      5. 정보 부족 시 빈값 (PC 버전 없음)
    """
    # 1. 알려진 앱 테이블
    if name_kr in KNOWN_PC:
        return KNOWN_PC[name_kr]

    # 2. 게임 카테고리
    if cat == "game":
        if name_kr in GAME_PC:
            return GAME_PC[name_kr]
        # 알려지지 않은 게임 — 모바일 전용 가능성 높으므로 빈값
        return ("", "")

    # 3. 개발사명 기반 추론
    dev_lower = (developer or "").lower()
    for hint, pc_info in DEV_DOMAIN_MAP.items():
        if hint in dev_lower:
            return pc_info

    # 4. 패키지명 기반 추론 (android_url에서 추출)
    pkg = ""
    if "id=" in android_url:
        pkg = android_url.split("id=")[1].split("&")[0].lower()
    for hint, pc_info in DEV_DOMAIN_MAP.items():
        if hint in pkg:
            return pc_info

    # 5. 웹형 앱 카테고리는 웹으로 접근 가능하다고 가정
    # iOS의 sellerUrl을 활용 (향후 개선)
    web_cats = {"sns", "entertainment", "shopping", "food",
                "finance", "productivity", "life", "education", "health", "travel"}
    if cat in web_cats:
        # 개발사 공식 사이트를 iOS 앱 정보에서 추출 시도는 build_app에서 처리
        return ("__auto__", "web")  # build_app에서 실제 URL로 교체

    return ("", "")


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
        "sellerUrl": res.get("sellerUrl", ""),   # ★ 개발사 공식 웹사이트
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

    # ★ iOS URL — 수집 실패해도 iTunes ID로 직접 구성
    ios_url = base.get("iosUrl", "")
    if not ios_url and itunes_id:
        ios_url = f"https://apps.apple.com/kr/app/id{itunes_id}"
    if not ios_url and android:
        # Android만 있을 때 bundle ID로 iTunes 검색 재시도
        retry = fetch_ios_by_term(name_en or name_kr)
        if retry:
            ios_url = retry.get("iosUrl", "")
            if not base.get("icon"):
                base = retry  # icon 등 iOS 데이터 활용

    record = {
        "id":          app_id,
        "name":        name_kr,
        "slug":        make_slug(name_kr, name_en),
        "cat":         cat,
        "icon":        (ios or android or {}).get("icon", ""),
        "developer":   base.get("developer") or (android or {}).get("developer", ""),
        "desc":        base.get("desc") or (android or {}).get("desc", ""),
        "iosUrl":      ios_url,
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

    # PC URL 자동 결정
    pc_url, pc_type = resolve_pc_url(
        name_kr, cat,
        record.get("developer", ""),
        record.get("androidUrl", "")
    )
    # __auto__ → iOS sellerUrl(개발사 공식 사이트) 활용
    if pc_url == "__auto__":
        seller_url = (ios or {}).get("sellerUrl", "")
        if seller_url and seller_url.startswith("http"):
            pc_url  = seller_url
            pc_type = "web"
        else:
            pc_url  = ""
            pc_type = ""
    record["pcUrl"]  = pc_url
    record["pcType"] = pc_type

    print(f"   ✓ {name_kr}: iOS={'O' if ok_ios else 'X'} "
          f"Android={'O' if ok_and else 'X'} pkg={real_pkg} "
          f"PC={'O' if pc_url else 'X'}")
    return record
