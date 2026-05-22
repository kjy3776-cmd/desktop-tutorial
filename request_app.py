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

from scraper_core import build_app, CATEGORIES
from auto_collect import load_apps, save_apps, log
from gen_sitemap import generate as gen_sitemap


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
        log("   힌트: 영문명·iTunes ID·패키지명을 더 정확히 입력해보세요")
        sys.exit(3)

    apps.append(rec)
    save_apps(apps)
    gen_sitemap()
    log(f"✅ '{name_kr}' 등록 완료 (ID {rec['id']}, 총 {len(apps)}개)")
    log("=" * 50)


if __name__ == "__main__":
    run()
