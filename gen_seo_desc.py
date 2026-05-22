# -*- coding: utf-8 -*-
"""
gen_seo_desc.py — Claude API로 앱별 SEO 최적화 소개글 자동 생성

스토어에서 긁어온 설명(desc)을 그대로 쓰면 중복 콘텐츠로 불이익.
이 스크립트는 앱 이름·카테고리·기존 설명을 바탕으로
네이버/구글 검색에 최적화된 고유 소개글(seoDesc)을 자동 생성해
apps_data.js에 저장한다.

사용:
  ANTHROPIC_API_KEY=sk-... python gen_seo_desc.py         # 전체 생성
  ANTHROPIC_API_KEY=sk-... python gen_seo_desc.py --missing # seoDesc 없는 것만
"""
import os
import sys
import json
import time
import random
import requests

from auto_collect import load_apps, save_apps, log

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-sonnet-4-20250514"

CAT_LABELS = {
    "sns":"소셜·커뮤니티", "entertainment":"엔터테인먼트", "shopping":"쇼핑",
    "food":"음식·배달", "finance":"금융·재테크", "game":"게임",
    "productivity":"생산성·도구", "life":"라이프스타일",
    "education":"교육", "health":"건강·운동", "travel":"여행·지도",
}

SYSTEM_PROMPT = """당신은 한국 앱 큐레이션 사이트 '이너앱'의 콘텐츠 에디터입니다.
앱 정보를 받으면, 네이버·구글 검색 상위 노출에 최적화된 앱 소개글을 작성합니다.

규칙:
- 150~200자 사이 (너무 짧거나 길면 안 됨)
- 스토어 설명을 그대로 복사하지 말 것 (검색엔진 중복 패널티)
- 실제로 써본 사람이 추천하는 말투 (직접 사용 경험 느낌)
- 핵심 기능 2~3가지를 자연스럽게 녹여낼 것
- 마케팅 과장 표현 금지 ("최고", "넘버원", "독보적" 등)
- 검색 키워드를 자연스럽게 포함 (예: "카카오톡 다운로드", "무료 메신저")
- 결과는 소개글 텍스트만, 따옴표나 설명 없이 바로 출력"""


def generate_seo_desc(app):
    """Claude API로 앱 소개글 생성."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log("⚠️ ANTHROPIC_API_KEY 환경변수 없음 — GitHub Secret 확인")
        return None

    cat = CAT_LABELS.get(app.get("cat", ""), app.get("cat", ""))
    prompt = f"""앱명: {app['name']}
카테고리: {cat}
개발사: {app.get('developer', '')}
스토어 설명 (참고용): {(app.get('desc') or '')[:200]}

위 앱의 이너앱 소개글을 작성해주세요."""

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": 300,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=body, timeout=30)
            if r.status_code == 200:
                data = r.json()
                text = data["content"][0]["text"].strip()
                return text
            elif r.status_code == 429:
                wait = (2 ** attempt) * 10
                log(f"   ↻ API 속도제한 — {wait}초 대기")
                time.sleep(wait)
            else:
                log(f"   ✗ API 오류 {r.status_code}: {r.text[:100]}")
                return None
        except Exception as e:
            log(f"   ✗ 요청 실패: {e}")
            time.sleep(5)

    return None


def run(missing_only=False):
    log("=" * 50)
    log("SEO 소개글 생성 시작")

    apps = load_apps()
    targets = [a for a in apps if not a.get("seoDesc")] if missing_only else apps
    log(f"대상: {len(targets)}/{len(apps)}개")

    updated = 0
    for i, app in enumerate(targets, 1):
        log(f"[{i}/{len(targets)}] {app['name']} 소개글 생성 중...")
        desc = generate_seo_desc(app)
        if desc:
            app["seoDesc"] = desc
            log(f"   ✓ 생성 완료 ({len(desc)}자): {desc[:50]}...")
            updated += 1
        else:
            log(f"   ✗ 생성 실패 — 기존 desc 유지")

        # API 요청 간격 (과금 절약 + 속도제한 회피)
        if i < len(targets):
            time.sleep(random.uniform(1.5, 3.0))

    if updated > 0:
        # ★ 저장 직전 파일을 다시 읽어서 merge — 다른 스크립트가 중간에 저장해도 안전
        fresh_apps = load_apps()
        seo_map = {a["name"]: a.get("seoDesc") for a in apps if a.get("seoDesc")}
        for a in fresh_apps:
            if a["name"] in seo_map:
                a["seoDesc"] = seo_map[a["name"]]
        save_apps(fresh_apps)
        log(f"💾 apps_data.js 저장 — {updated}개 소개글 추가")
    log("완료")
    log("=" * 50)


if __name__ == "__main__":
    missing = "--missing" in sys.argv
    run(missing_only=missing)
