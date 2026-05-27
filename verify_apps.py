# -*- coding: utf-8 -*-
"""
verify_apps.py — 이너앱 자동 검수 봇

검수 항목:
  1. 구글플레이 URL 유효성 (패키지명 존재 여부)
  2. iOS URL 유효성
  3. 아이콘 이미지 로드 여부
  4. 설명글 길이 (50자 미만이면 재수집)
  5. 리뷰 0개 → 재수집 시도
  6. 안드로이드 사양 누락(-) → 재수집

사용:
  python verify_apps.py           # 전체 검수 + 자동 수정
  python verify_apps.py --dry-run # 문제 목록만 출력, 수정 안 함
"""
import os
import sys
import json
import time
import random
import requests

from scraper_core import fetch_android, fetch_ios_by_term, fetch_ios_by_id
from auto_collect import load_apps, save_apps, log
from gen_sitemap import generate as gen_sitemap

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT   = os.path.join(BASE_DIR, "verify_report.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

EN_NAME = {
    "카카오톡":"KakaoTalk","네이버":"NAVER","인스타그램":"Instagram",
    "유튜브":"YouTube","넷플릭스":"Netflix","티빙":"TVING",
    "왓챠":"Watcha","쿠팡":"Coupang","당근":"Karrot",
    "번개장터":"Bunjang","무신사":"MUSINSA","오늘의집":"Ohou",
    "29CM":"29CM","에이블리":"ABLY","올리브영":"Oliveyoung",
    "컬리":"Kurly","배달의민족":"Baemin","요기요":"Yogiyo",
    "쿠팡이츠":"Coupang Eats","토스":"Toss","카카오페이":"KakaoPay",
    "네이버페이":"Naver Pay",
}


# ─────────────────────────────────────────────────────────────
# 개별 검수 함수
# ─────────────────────────────────────────────────────────────
def check_url(url, label):
    """URL이 실제로 열리는지 확인. 구글플레이는 브라우저 UA 필요."""
    if not url or not url.startswith("http"):
        return False, "URL 없음"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        # 구글플레이는 200 or 301 정상, 404는 앱 없음
        if r.status_code == 404:
            return False, f"404 앱 없음"
        if r.status_code >= 400:
            # 403은 봇 차단일 수 있어서 일단 통과
            return True, f"{r.status_code} (봇차단 가능성, URL은 유효)"
        return True, f"{r.status_code} OK"
    except Exception as e:
        return False, f"접속 실패: {type(e).__name__}"


def check_image(url):
    """이미지 URL이 실제로 로드되는지 확인."""
    if not url or not url.startswith("http"):
        return False
    try:
        r = requests.head(url, headers=HEADERS, timeout=8)
        return r.status_code < 400
    except Exception:
        return False


def diagnose(app):
    """
    앱 하나를 검수해서 문제 목록 반환.
    반환: list of str (문제 없으면 빈 리스트)
    """
    issues = []

    # 1. 구글플레이 URL
    and_url = app.get("androidUrl", "")
    ok, msg = check_url(and_url, "구글플레이")
    if not ok:
        issues.append(f"구글플레이 URL 불량: {msg}")

    # 2. iOS URL
    ios_url = app.get("iosUrl", "")
    ok, msg = check_url(ios_url, "iOS")
    if not ok:
        issues.append(f"iOS URL 불량: {msg}")

    # 3. 아이콘
    if not check_image(app.get("icon", "")):
        issues.append("아이콘 이미지 로드 실패")

    # 4. 설명글
    desc = app.get("desc", "") or ""
    if len(desc) < 50:
        issues.append(f"설명글 너무 짧음 ({len(desc)}자)")

    # 5. 안드로이드 사양 누락
    sa = app.get("spec_and", {})
    if sa.get("ver", "-") == "-":
        issues.append("안드로이드 사양 누락")

    # 6. 리뷰 없음
    if not app.get("reviews"):
        issues.append("리뷰 없음")

    return issues


# ─────────────────────────────────────────────────────────────
# 자동 수정
# ─────────────────────────────────────────────────────────────
def fix_app(app, issues):
    """문제가 있는 앱을 재수집해서 데이터를 보강한다."""
    name = app["name"]
    fixed = False

    # 구글플레이 또는 안드로이드 사양 문제 → 안드로이드 재수집
    need_android = any(
        "구글플레이" in i or "안드로이드 사양" in i or "리뷰" in i
        for i in issues
    )
    if need_android:
        known_pkg = ""
        if "id=" in app.get("androidUrl", ""):
            known_pkg = app["androidUrl"].split("id=")[1].split("&")[0]

        data, real_pkg = fetch_android(
            known_pkg, name, EN_NAME.get(name, ""),
            bundle_id=app.get("iosUrl", "").split("id=")[0]  # 힌트용
        )
        if data:
            app["spec_and"]   = data["spec_and"]
            app["androidUrl"] = data["androidUrl"]
            if not app.get("reviews") and data.get("reviews"):
                app["reviews"] = data["reviews"]
            if not app.get("icon") and data.get("icon"):
                app["icon"] = data["icon"]
            if not app.get("screenshots") and data.get("screenshots"):
                app["screenshots"] = data["screenshots"]
            fixed = True
            log(f"   ✓ 안드로이드 재수집 성공 (pkg={real_pkg})")
        else:
            log(f"   ✗ 안드로이드 재수집 실패")
        time.sleep(random.uniform(8, 20))

    # iOS URL 문제 → iOS 재수집 또는 iTunes ID로 직접 구성
    if any("iOS URL" in i for i in issues):
        # iTunes ID가 iosUrl에 포함돼 있으면 직접 구성
        itunes_id = ""
        ios_url = app.get("iosUrl", "")
        if "/id" in ios_url:
            itunes_id = ios_url.split("/id")[-1].split("?")[0]
        if itunes_id and itunes_id.isdigit():
            app["iosUrl"] = f"https://apps.apple.com/kr/app/id{itunes_id}"
            fixed = True
            log(f"   ✓ iTunes ID로 iOS URL 복구: {app['iosUrl']}")
        else:
            ios_data = fetch_ios_by_term(name)
            if ios_data and ios_data.get("iosUrl"):
                app["iosUrl"]   = ios_data.get("iosUrl", app["iosUrl"])
                app["spec_ios"] = ios_data.get("spec_ios", app["spec_ios"])
                if not app.get("icon") and ios_data.get("icon"):
                    app["icon"] = ios_data["icon"]
                fixed = True
                log(f"   ✓ iOS 재수집 성공")
        time.sleep(random.uniform(3, 8))

    # 설명글 부족 → iOS에서 보강 시도
    if any("설명글" in i for i in issues) and not need_android:
        ios_data = fetch_ios_by_term(name)
        if ios_data and len(ios_data.get("desc", "")) > len(app.get("desc", "")):
            app["desc"] = ios_data["desc"]
            fixed = True
            log(f"   ✓ 설명글 보강")
        time.sleep(random.uniform(3, 8))

    return fixed


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
def run(dry_run=False):
    log("=" * 50)
    log(f"검수 시작 (dry_run={dry_run})")

    apps = load_apps()
    report = {"date": __import__("datetime").date.today().isoformat(), "results": []}

    total_issues = 0
    fixed_count  = 0

    for i, app in enumerate(apps, 1):
        name = app["name"]
        log(f"[{i}/{len(apps)}] {name} 검수 중...")
        issues = diagnose(app)

        if issues:
            total_issues += len(issues)
            log(f"   ⚠️ 문제 {len(issues)}개: {', '.join(issues)}")
            report["results"].append({"name": name, "issues": issues})

            if not dry_run:
                fixed = fix_app(app, issues)
                if fixed:
                    fixed_count += 1
        else:
            log(f"   ✅ 이상 없음")
            report["results"].append({"name": name, "issues": []})

        # URL 체크 사이 짧은 대기 (차단 방지)
        time.sleep(random.uniform(2, 5))

    # 결과 저장
    report["summary"] = {
        "total": len(apps),
        "has_issues": sum(1 for r in report["results"] if r["issues"]),
        "total_issues": total_issues,
        "fixed": fixed_count,
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if not dry_run and fixed_count > 0:
        save_apps(apps)
        gen_sitemap()
        log(f"💾 apps_data.js 갱신 — {fixed_count}개 수정")

    log(f"검수 완료: 총 {len(apps)}개, 문제 {total_issues}건, 수정 {fixed_count}개")
    log("=" * 50)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    try:
        run(dry_run=dry)
    except KeyboardInterrupt:
        log("사용자 중단")
    except Exception as e:
        log(f"💥 예외: {type(e).__name__}: {e}")
        raise
