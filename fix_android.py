# -*- coding: utf-8 -*-
"""
fix_android.py — 기존 apps_data.js 의 안드로이드 누락분(절반) 일괄 복구

사용:
  python fix_android.py            # spec_and 가 '-' 인 앱만 재수집해 패치
  python fix_android.py --all      # 전체 앱 안드로이드 데이터 강제 갱신
"""
import os
import sys
import json
import time
import random

from scraper_core import fetch_android
from auto_collect import load_apps, save_apps, log

# 이름 → 영문명 매핑 (검색 폴백 정확도 향상용)
EN_NAME = {
    "카카오톡": "KakaoTalk", "네이버": "NAVER", "인스타그램": "Instagram",
    "유튜브": "YouTube", "넷플릭스": "Netflix", "티빙": "TVING",
    "왓챠": "Watcha", "쿠팡": "Coupang", "당근": "Karrot",
    "번개장터": "Bunjang", "무신사": "MUSINSA", "오늘의집": "Ohou",
    "29CM": "29CM", "에이블리": "ABLY", "올리브영": "Oliveyoung",
    "컬리": "Kurly", "배달의민족": "Baemin", "요기요": "Yogiyo",
    "쿠팡이츠": "Coupang Eats", "토스": "Toss", "카카오페이": "KakaoPay",
    "네이버페이": "Naver Pay",
}


def needs_fix(app):
    return app.get("spec_and", {}).get("ver", "-") == "-"


def main(force_all=False):
    apps = load_apps()
    targets = apps if force_all else [a for a in apps if needs_fix(a)]

    log(f"🔧 안드로이드 복구 시작 — 대상 {len(targets)}/{len(apps)}개")
    if not targets:
        log("✅ 복구할 항목 없음 (모든 앱 정상)")
        return

    fixed = 0
    for i, app in enumerate(targets, 1):
        name = app["name"]
        log(f"[{i}/{len(targets)}] {name}")

        # 기존 androidUrl 에서 패키지명 추출 시도
        known_pkg = ""
        url = app.get("androidUrl", "")
        if "id=" in url:
            known_pkg = url.split("id=")[1].split("&")[0]

        data, real_pkg = fetch_android(known_pkg, name, EN_NAME.get(name, ""))
        if data:
            app["spec_and"]   = data["spec_and"]
            app["androidUrl"] = data["androidUrl"]
            # 리뷰가 비어있으면 안드로이드 리뷰로 채움
            if not app.get("reviews") and data.get("reviews"):
                app["reviews"] = data["reviews"]
            # 아이콘/스크린샷 비어있으면 보강
            if not app.get("icon") and data.get("icon"):
                app["icon"] = data["icon"]
            if not app.get("screenshots") and data.get("screenshots"):
                app["screenshots"] = data["screenshots"]
            fixed += 1
            log(f"   ✓ 복구 성공 (pkg={real_pkg})")
        else:
            log(f"   ✗ 복구 실패 — 안드로이드 미지원이거나 검색 불가")

        time.sleep(random.uniform(5, 12))  # 차단 회피

    save_apps(apps)
    log(f"💾 완료 — {fixed}/{len(targets)}개 복구, apps_data.js 저장됨")
    try:
        from gen_sitemap import generate
        n = generate()
        log(f"🗺  sitemap.xml 재생성 — {n}개 URL")
    except Exception as e:
        log(f"⚠️ sitemap 생성 실패: {e}")


if __name__ == "__main__":
    main(force_all="--all" in sys.argv)
