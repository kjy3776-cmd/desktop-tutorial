# -*- coding: utf-8 -*-
"""
request_app.py — 사용자가 요청한 앱을 즉시 등록

GitHub Actions에서 입력받은 환경변수:
  REQUEST_NAME_KR : 앱 한글명 (필수)
  REQUEST_NAME_EN : 앱 영문명 (선택)
  REQUEST_CAT     : 카테고리 (필수)
  REQUEST_ITUNES  : iTunes ID (선택)
  REQUEST_PKG     : 안드로이드 패키지명 (선택)

처리 순서:
  1. 중복 체크 (이름·iTunes ID·패키지명 모두 비교)
  2. 중복이면 거부 + 사유 출력 후 종료 (exit 2)
  3. 신규면 build_app() 호출해서 데이터 수집
  4. 검수 → 소개글 생성 → apps_data.js 저장
"""
import os
import sys
import json
import time
import random
import requests as req_lib


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


import scraper_core

# scraper_core.py 내부 함수가 HEADERS 전역변수를 참조하는 경우가 있어
# request_app.py에만 HEADERS를 정의하면 GitHub Actions에서 NameError가 날 수 있습니다.
# 그래서 scraper_core 모듈 전역에도 강제로 주입합니다.
scraper_core.HEADERS = HEADERS

build_app = scraper_core.build_app
CATEGORIES = scraper_core.CATEGORIES

from auto_collect import load_apps, save_apps, log
from gen_sitemap import generate as gen_sitemap

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-20250514"

CAT_LABELS = {
    "sns":"소셜·커뮤니티","entertainment":"엔터테인먼트","shopping":"쇼핑",
    "food":"음식·배달","finance":"금융·재테크","game":"게임",
    "productivity":"생산성·도구","life":"라이프스타일",
    "education":"교육","health":"건강·운동","travel":"여행·지도",
}

SYSTEM_PROMPT = """당신은 한국 앱 큐레이션 사이트 '이너앱'의 콘텐츠 에디터입니다.
앱 정보를 받으면, 네이버·구글 검색 상위 노출에 최적화된 앱 소개글을 작성합니다.
규칙: 150~200자, 스토어 설명 복사 금지, 직접 사용 경험 말투, 핵심 기능 2~3가지 자연스럽게 포함.
결과는 소개글 텍스트만, 따옴표나 설명 없이 바로 출력."""


def generate_seo(app):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    cat = CAT_LABELS.get(app.get("cat",""), app.get("cat",""))
    prompt = f"앱명: {app['name']}\n카테고리: {cat}\n개발사: {app.get('developer','')}\n스토어 설명: {(app.get('desc') or '')[:200]}\n\n이 앱의 이너앱 소개글을 작성해주세요."
    try:
        r = req_lib.post(API_URL, headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": MODEL, "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "messages": [{"role":"user","content":prompt}],
        }, timeout=30)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
    except Exception as e:
        log(f"   SEO 생성 실패: {e}")
    return None


def is_duplicate(apps, name_kr, itunes_id, pkg):
    """이미 등록된 앱인지 확인."""
    name_norm = "".join(name_kr.lower().split())
    for a in apps:
        # 1) 이름 정확 일치
        if a["name"] == name_kr:
            return f"이름 '{name_kr}'이 이미 등록됨 (ID {a['id']})"
        # 2) 이름 공백/대소문자 무시 일치
        if "".join(a["name"].lower().split()) == name_norm:
            return f"유사 이름 '{a['name']}'이 이미 등록됨 (ID {a['id']})"
        # 3) iTunes ID 일치
        if itunes_id and itunes_id in a.get("iosUrl", ""):
            return f"iTunes ID '{itunes_id}'가 '{a['name']}'에 이미 사용됨"
        # 4) 패키지명 일치
        if pkg and pkg in a.get("androidUrl", ""):
            return f"패키지명 '{pkg}'가 '{a['name']}'에 이미 사용됨"
    return None


def run():
    name_kr   = os.environ.get("REQUEST_NAME_KR", "").strip()
    name_en   = os.environ.get("REQUEST_NAME_EN", "").strip()
    cat       = os.environ.get("REQUEST_CAT", "life").strip()
    itunes_id = os.environ.get("REQUEST_ITUNES", "").strip()
    pkg       = os.environ.get("REQUEST_PKG", "").strip()

    if not name_kr:
        log("❌ 앱 한글명이 비어있습니다.")
        sys.exit(1)
    if cat not in CATEGORIES:
        log(f"❌ 알 수 없는 카테고리: {cat}")
        sys.exit(1)

    log("=" * 50)
    log(f"수동 등록 요청: {name_kr} ({cat})")

    apps = load_apps()

    # ★ 중복 체크
    dup_reason = is_duplicate(apps, name_kr, itunes_id, pkg)
    if dup_reason:
        log(f"⚠️ 중복 등록 거부 — {dup_reason}")
        log("이미 등록된 앱입니다. 기존 데이터를 확인하세요.")
        sys.exit(2)   # 중복 종료 코드

    # 신규 등록
    next_id = max([a["id"] for a in apps], default=0) + 1
    rec = build_app(next_id, name_kr, name_en, itunes_id, pkg, cat)

    if not rec:
        log(f"❌ '{name_kr}' 수집 실패 — iOS/Android 모두 찾지 못함")
        log("   힌트: 앱 이름만으로 안 잡히면 REQUEST_ITUNES 또는 REQUEST_PKG를 직접 넣어주세요.")
        log("   예: 여기어때 iOS ID는 앱스토어 URL의 id 뒤 숫자, Android 패키지는 play.google.com URL의 id= 값입니다.")
        sys.exit(3)

    apps.append(rec)

    # ★ SEO 소개글 즉시 생성 (별도 스크립트 없이 한 번에 저장)
    if not rec.get("seoDesc"):
        log(f"   SEO 소개글 생성 중...")
        seo = generate_seo(rec)
        if seo:
            rec["seoDesc"] = seo
            log(f"   ✓ 소개글 생성 ({len(seo)}자)")

    save_apps(apps)
    gen_sitemap()
    # 정적 HTML 생성 (SEO — 검색엔진이 직접 읽는 페이지)
    try:
        from gen_static import run as gen_static
        gen_static(new_only=True)
        log("📄 정적 HTML 생성 완료")
    except Exception as e:
        log(f"⚠️ 정적 HTML 생성 실패: {e}")
    log(f"✅ '{name_kr}' 등록 완료 (ID {rec['id']}, 총 {len(apps)}개)")
    log("=" * 50)


if __name__ == "__main__":
    run()
