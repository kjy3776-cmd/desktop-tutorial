# -*- coding: utf-8 -*-
"""
gen_compare_posts.py — 이너앱 비교·추천 글 자동 생성기

역할:
  - 하루 1개 앱 비교·추천 SEO 글 생성
  - /compare/*.html 정적 페이지 생성
  - /compare/index.html 목록 페이지 갱신
  - compare_index.json으로 중복 생성 방지
  - 생성 후 sitemap.xml 재생성

사용:
  ANTHROPIC_API_KEY=sk-... python gen_compare_posts.py
  python gen_compare_posts.py --force   # 오늘 생성 여부 무시하고 1개 생성
"""
import os
import re
import sys
import argparse
import json
import random
import datetime
import html
from pathlib import Path

import requests

from auto_collect import load_apps, log

try:
    from gen_sitemap import SITE_URL
except Exception:
    SITE_URL = "https://innerapple.com"

BASE_DIR = Path(__file__).resolve().parent
COMPARE_DIR = BASE_DIR / "compare"
INDEX_FILE = BASE_DIR / "compare_index.json"
STATE_FILE = BASE_DIR / "compare_state.json"
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"
DAILY_LIMIT = 1

CAT_LABELS = {
    "sns":"소셜·커뮤니티", "entertainment":"엔터테인먼트", "shopping":"쇼핑",
    "food":"음식·배달", "finance":"금융·재테크", "game":"게임",
    "productivity":"생산성·도구", "life":"라이프스타일",
    "education":"교육", "health":"건강·운동", "travel":"여행·지도",
}

TOPIC_TEMPLATES = [
    {"type":"category_top", "cat":"sns", "title":"무료 메신저·SNS 앱 추천 TOP5", "slug":"best-sns-messenger-apps", "intent":"메신저, SNS, 커뮤니티 앱을 고르는 사람"},
    {"type":"category_top", "cat":"entertainment", "title":"OTT·영상 스트리밍 앱 비교 추천", "slug":"ott-video-app-comparison", "intent":"영화, 드라마, 영상 시청 앱을 고르는 사람"},
    {"type":"category_top", "cat":"productivity", "title":"생산성 앱 추천 TOP5", "slug":"best-productivity-apps", "intent":"메모, 일정, 업무 도구 앱을 찾는 사람"},
    {"type":"category_top", "cat":"shopping", "title":"쇼핑 앱 비교 추천", "slug":"shopping-app-comparison", "intent":"온라인 쇼핑 앱을 비교하는 사람"},
    {"type":"category_top", "cat":"food", "title":"배달·맛집 앱 비교 추천", "slug":"food-delivery-app-comparison", "intent":"배달, 예약, 맛집 탐색 앱을 찾는 사람"},
    {"type":"category_top", "cat":"finance", "title":"금융·재테크 앱 추천 TOP5", "slug":"finance-investment-apps", "intent":"송금, 결제, 투자 앱을 고르는 사람"},
    {"type":"category_top", "cat":"game", "title":"인기 모바일 게임 앱 추천", "slug":"best-mobile-game-apps", "intent":"재미있는 모바일 게임을 찾는 사람"},
    {"type":"category_top", "cat":"education", "title":"공부·교육 앱 추천 TOP5", "slug":"best-education-apps", "intent":"학습, 영어, 강의 앱을 찾는 사람"},
    {"type":"category_top", "cat":"health", "title":"운동·건강관리 앱 추천 TOP5", "slug":"best-health-fitness-apps", "intent":"운동 기록과 건강관리 앱을 찾는 사람"},
    {"type":"category_top", "cat":"travel", "title":"여행·지도 앱 비교 추천", "slug":"travel-map-app-comparison", "intent":"여행 예약, 지도, 길찾기 앱을 찾는 사람"},
]

SYSTEM_PROMPT = """당신은 한국 앱 큐레이션 사이트 '이너앱'의 전문 에디터입니다.
앱 비교·추천 글을 작성합니다.

작성 규칙:
- 1200~1800자 분량
- 검색 사용자가 실제로 궁금해하는 기준으로 비교
- 앱별 장점, 아쉬운 점, 추천 대상을 분리해서 설명
- 과장 표현 금지: 최고, 압도적, 무조건, 완벽 같은 단어 지양
- 스토어 설명 복붙 금지
- 실제 사용자가 고르는 데 도움되는 문체
- 제목, 소제목, 목록을 자연스럽게 포함
- 결과는 본문 HTML 조각만 출력. html/head/body 태그는 쓰지 말 것
- h2, h3, p, ul, li 태그만 사용
"""


def _slug_text(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9가-힣\s-]", "", (text or "").lower()).strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "compare-post"


def get_slug(app: dict) -> str:
    if app.get("slug"):
        return app["slug"]
    return _slug_text(app.get("name", "")) or f"app-{app.get('id','')}"


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def today() -> str:
    return datetime.date.today().isoformat()


def pick_topic(apps, state):
    generated = set(state.get("generated_slugs", []))
    candidates = []
    for topic in TOPIC_TEMPLATES:
        cat_apps = [a for a in apps if a.get("cat") == topic["cat"]]
        if len(cat_apps) >= 2 and topic["slug"] not in generated:
            candidates.append((topic, cat_apps))
    if not candidates:
        # 주제가 모두 소진되면 누적 기록은 유지하되 주제 순환 가능하게 오늘만 새로 고름
        candidates = []
        for topic in TOPIC_TEMPLATES:
            cat_apps = [a for a in apps if a.get("cat") == topic["cat"]]
            if len(cat_apps) >= 2:
                candidates.append((topic, cat_apps))
    if not candidates:
        pool = apps[:5]
        return {
            "type":"all_top", "cat":"all", "title":"인기 앱 추천 TOP5", "slug":"best-popular-apps", "intent":"요즘 많이 쓰는 앱을 찾는 사람"
        }, pool
    topic, cat_apps = random.choice(candidates)
    # 리뷰가 있거나 seoDesc가 있는 앱 우선
    ranked = sorted(cat_apps, key=lambda a: (len(a.get("reviews") or []), bool(a.get("seoDesc")), a.get("id",0)), reverse=True)
    return topic, ranked[:5]


def pick_custom_topic(apps, title=None, cat=None, app_names=None, slug=None):
    """수동 워크플로우에서 입력한 제목/카테고리/앱명으로 compare 글 생성."""
    selected = []

    if app_names:
        wanted = [x.strip().lower() for x in app_names.split(",") if x.strip()]
        for w in wanted:
            for a in apps:
                if w in a.get("name", "").lower() or w in get_slug(a).lower():
                    if a not in selected:
                        selected.append(a)
                    break

    if not selected and cat:
        cat_pool = [a for a in apps if a.get("cat") == cat]
        selected = sorted(cat_pool, key=lambda a: (len(a.get("reviews") or []), bool(a.get("seoDesc")), a.get("id", 0)), reverse=True)[:5]

    if not selected:
        selected = sorted(apps, key=lambda a: (len(a.get("reviews") or []), bool(a.get("seoDesc")), a.get("id", 0)), reverse=True)[:5]

    if len(selected) < 2:
        return None, []

    title = title or f"{CAT_LABELS.get(cat, '인기')} 앱 비교 추천"
    post_slug = slug or _slug_text(title)
    topic = {
        "type": "manual",
        "cat": cat or selected[0].get("cat", "all"),
        "title": title,
        "slug": post_slug,
        "intent": f"{title} 정보를 찾는 사람"
    }
    return topic, selected[:5]


def fallback_content(title, apps, topic):
    lis = []
    for a in apps:
        desc = html.escape((a.get("seoDesc") or a.get("desc") or "").strip()[:220])
        lis.append(f"<li><strong>{html.escape(a.get('name',''))}</strong> — {desc}</li>")
    names = ", ".join(a.get("name", "") for a in apps)
    return f"""
<h2>{html.escape(title)} 한눈에 보기</h2>
<p>{html.escape(names)}를 중심으로 사용 목적, 주요 기능, 설치 환경을 비교했습니다. 이 글은 앱을 고르기 전 빠르게 차이를 확인할 수 있도록 정리한 추천 가이드입니다.</p>
<h2>추천 앱 요약</h2>
<ul>{''.join(lis)}</ul>
<h2>어떤 기준으로 고르면 좋을까?</h2>
<p>자주 쓰는 기능, 사용 기기, PC 버전 필요 여부, 리뷰에서 반복되는 장단점을 함께 확인하는 것이 좋습니다. 단순 다운로드보다 실제 사용 목적에 맞는 앱을 고르는 것이 중요합니다.</p>
<h2>추천 대상</h2>
<p>{html.escape(topic.get('intent','앱을 비교하려는 사용자'))}라면 위 앱들을 먼저 비교해보세요. 각 앱 상세 페이지에서 iOS, Android, PC 지원 여부와 리뷰를 함께 확인할 수 있습니다.</p>
""".strip()


def generate_content(title, apps, topic):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return fallback_content(title, apps, topic)

    app_lines = []
    for a in apps:
        app_lines.append(
            f"- 앱명: {a.get('name','')}\n"
            f"  카테고리: {CAT_LABELS.get(a.get('cat',''), a.get('cat',''))}\n"
            f"  개발사: {a.get('developer','')}\n"
            f"  소개: {(a.get('seoDesc') or a.get('desc') or '')[:350]}\n"
            f"  iOS 사양: {a.get('spec_ios',{})}\n"
            f"  Android 사양: {a.get('spec_and',{})}"
        )

    prompt = f"""주제: {title}
검색 의도: {topic.get('intent','앱 비교')}
비교 대상 앱:
{chr(10).join(app_lines)}

위 정보를 바탕으로 앱 비교·추천 SEO 글을 작성해주세요.
"""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": 2400,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        r = requests.post(API_URL, headers=headers, json=body, timeout=60)
        if r.status_code == 200:
            return r.json()["content"][0]["text"].strip()
        log(f"⚠️ Claude compare 오류 {r.status_code}: {r.text[:120]}")
    except Exception as e:
        log(f"⚠️ Claude compare 요청 실패: {e}")
    return fallback_content(title, apps, topic)


def app_cards(apps):
    cards = []
    for a in apps:
        name = html.escape(a.get("name", ""))
        dev = html.escape(a.get("developer", ""))
        icon = html.escape(a.get("icon", ""))
        cards.append(f"""
<a class="app-card" href="{SITE_URL}/app/{get_slug(a)}.html">
  <img src="{icon}" alt="{name} 아이콘" loading="lazy">
  <strong>{name}</strong>
  <span>{dev}</span>
</a>""")
    return "\n".join(cards)


def build_compare_html(title, slug, content, apps, topic):
    url = f"{SITE_URL}/compare/{slug}.html"
    desc = f"{title} 기준으로 주요 앱의 장점, 아쉬운 점, 추천 대상을 비교했습니다."
    faq_json = {
        "@context":"https://schema.org",
        "@type":"FAQPage",
        "mainEntity":[
            {"@type":"Question", "name":f"{title}에서 어떤 기준을 보면 좋나요?", "acceptedAnswer":{"@type":"Answer", "text":"사용 목적, 지원 플랫폼, PC 버전 여부, 실제 리뷰에서 반복되는 장단점을 함께 확인하는 것이 좋습니다."}},
            {"@type":"Question", "name":"앱 다운로드는 어디에서 하나요?", "acceptedAnswer":{"@type":"Answer", "text":"각 앱 상세 페이지에서 App Store, Google Play, PC 버전 링크를 확인할 수 있습니다."}}
        ]
    }
    breadcrumb = {
        "@context":"https://schema.org",
        "@type":"BreadcrumbList",
        "itemListElement":[
            {"@type":"ListItem","position":1,"name":"이너앱","item":SITE_URL + "/"},
            {"@type":"ListItem","position":2,"name":"앱 비교·분석","item":SITE_URL + "/compare/"},
            {"@type":"ListItem","position":3,"name":title,"item":url}
        ]
    }
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} | 이너앱</title>
<meta name="description" content="{html.escape(desc)}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="이너앱 InnerApp">
<meta property="og:title" content="{html.escape(title)} | 이너앱">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{url}">
<script type="application/ld+json">{json.dumps(faq_json, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--blue:#1B64DA;--green:#00C471;--gray-50:#F9FAFB;--gray-100:#F3F4F6;--gray-200:#E5E7EB;--gray-500:#6B7280;--gray-900:#111827}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Pretendard',sans-serif;background:var(--gray-50);color:var(--gray-900);line-height:1.75}}
nav{{height:56px;background:#fff;border-bottom:1px solid var(--gray-200);display:flex;align-items:center;padding:0 20px}}
nav a{{font-weight:700;color:var(--blue);text-decoration:none;font-size:20px}}
.page{{max-width:920px;margin:0 auto;padding:28px 20px 60px}}
.breadcrumb{{font-size:13px;margin-bottom:18px;color:var(--gray-500)}}
.breadcrumb a{{color:var(--blue);text-decoration:none}}
.hero{{background:#fff;border:1px solid var(--gray-200);border-radius:24px;padding:28px;margin-bottom:20px}}
h1{{font-size:30px;letter-spacing:-.5px;margin-bottom:10px}}
.lead{{color:var(--gray-500);font-size:15px}}
.app-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin:22px 0}}
.app-card{{background:#fff;border:1px solid var(--gray-200);border-radius:18px;padding:16px;text-decoration:none;color:var(--gray-900);display:flex;flex-direction:column;align-items:center;text-align:center;gap:7px;transition:all .18s}}
.app-card:hover{{transform:translateY(-3px);box-shadow:0 8px 20px rgba(0,0,0,.07)}}
.app-card img{{width:64px;height:64px;border-radius:16px;object-fit:cover;background:#eee}}
.app-card span{{font-size:12px;color:var(--gray-500)}}
article{{background:#fff;border:1px solid var(--gray-200);border-radius:24px;padding:28px}}
article h2{{font-size:22px;margin:28px 0 10px}}
article h2:first-child{{margin-top:0}}
article h3{{font-size:18px;margin:22px 0 8px}}
article p{{margin:10px 0;color:#374151}}
article ul{{padding-left:22px;margin:12px 0}}
article li{{margin:8px 0}}
.cta{{margin-top:22px;padding:18px;border-radius:18px;background:#EBF1FD}}
.cta a{{color:var(--blue);font-weight:700;text-decoration:none}}
footer{{max-width:920px;margin:0 auto;padding:22px 20px;border-top:1px solid var(--gray-200);font-size:13px;color:var(--gray-500)}}
</style>
</head>
<body>
<nav><a href="{SITE_URL}/">이너앱<span style="color:var(--green)">.</span></a></nav>
<div class="page">
  <div class="breadcrumb"><a href="{SITE_URL}/">홈</a> › <a href="{SITE_URL}/compare/">앱 비교·분석</a> › {html.escape(title)}</div>
  <section class="hero">
    <h1>{html.escape(title)}</h1>
    <p class="lead">{html.escape(desc)}</p>
  </section>
  <section class="app-grid">{app_cards(apps)}</section>
  <article>{content}</article>
  <div class="cta">앱별 다운로드 링크와 상세 사양은 위 앱 카드 또는 <a href="{SITE_URL}/">이너앱 홈</a>에서 확인할 수 있습니다.</div>
</div>
<footer>이너앱 · 앱 비교·분석 · {html.escape(', '.join(a.get('name','') for a in apps))}</footer>
</body>
</html>"""


def write_compare_index(items):
    COMPARE_DIR.mkdir(exist_ok=True)
    sorted_items = sorted(items, key=lambda x: x.get("created", ""), reverse=True)
    cards = []
    for item in sorted_items:
        cards.append(f"""
<a class="card" href="{SITE_URL}/compare/{html.escape(item['slug'])}.html">
  <span>{html.escape(CAT_LABELS.get(item.get('cat',''), item.get('cat','앱')))}</span>
  <h2>{html.escape(item['title'])}</h2>
  <p>{html.escape(item.get('description',''))}</p>
</a>""")
    body_cards = "\n".join(cards) or "<p>아직 생성된 비교·분석 글이 없습니다.</p>"
    index_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>앱 비교·분석 | 이너앱</title>
<meta name="description" content="인기 앱 추천, 앱 비교, 카테고리별 앱 분석 글을 모아 확인하세요.">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{SITE_URL}/compare/">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--blue:#1B64DA;--green:#00C471;--gray-50:#F9FAFB;--gray-200:#E5E7EB;--gray-500:#6B7280;--gray-900:#111827}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Pretendard',sans-serif;background:var(--gray-50);color:var(--gray-900);line-height:1.65}}
nav{{height:56px;background:#fff;border-bottom:1px solid var(--gray-200);display:flex;align-items:center;padding:0 20px}}
nav a{{font-weight:700;color:var(--blue);text-decoration:none;font-size:20px}}
.page{{max-width:1000px;margin:0 auto;padding:34px 20px}}
h1{{font-size:32px;letter-spacing:-.6px;margin-bottom:8px}}
.sub{{color:var(--gray-500);margin-bottom:26px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
.card{{display:block;background:#fff;border:1px solid var(--gray-200);border-radius:22px;padding:22px;text-decoration:none;color:var(--gray-900);transition:all .18s}}
.card:hover{{transform:translateY(-3px);box-shadow:0 8px 20px rgba(0,0,0,.07)}}
.card span{{font-size:12px;font-weight:700;color:var(--blue)}}
.card h2{{font-size:19px;margin:8px 0}}
.card p{{font-size:14px;color:var(--gray-500)}}
</style>
</head>
<body>
<nav><a href="{SITE_URL}/">이너앱<span style="color:var(--green)">.</span></a></nav>
<main class="page">
  <h1>앱 비교·분석</h1>
  <p class="sub">인기 앱 추천, 카테고리별 비교, 다운로드 전 확인할 내용을 모았습니다.</p>
  <div class="grid">{body_cards}</div>
</main>
</body>
</html>"""
    (COMPARE_DIR / "index.html").write_text(index_html, encoding="utf-8")


def run(force=False, title=None, cat=None, app_names=None, slug=None):
    COMPARE_DIR.mkdir(exist_ok=True)
    state = load_json(STATE_FILE, {"generated_slugs": [], "daily_count": {}})
    index = load_json(INDEX_FILE, [])

    current_count = state.get("daily_count", {}).get(today(), 0)
    if current_count >= DAILY_LIMIT and not force:
        log(f"ℹ️ 오늘 compare 글 이미 {current_count}개 생성됨 — 하루 상한({DAILY_LIMIT}) 유지")
        write_compare_index(index)
        return 0

    apps = load_apps()
    if len(apps) < 2:
        log("⚠️ compare 생성에는 앱이 최소 2개 필요합니다.")
        write_compare_index(index)
        return 0

    if title or cat or app_names or slug:
        topic, selected = pick_custom_topic(apps, title=title, cat=cat, app_names=app_names, slug=slug)
        if not topic:
            log("⚠️ 수동 compare 생성에는 매칭되는 앱이 최소 2개 필요합니다.")
            write_compare_index(index)
            return 0
    else:
        topic, selected = pick_topic(apps, state)
    post_slug = topic["slug"]
    # 같은 slug가 이미 있으면 날짜 suffix로 중복 회피
    existing_slugs = {i.get("slug") for i in index}
    if post_slug in existing_slugs:
        post_slug = f"{post_slug}-{today()}"

    title = topic["title"]
    content = generate_content(title, selected, topic)
    html_text = build_compare_html(title, post_slug, content, selected, topic)
    out = COMPARE_DIR / f"{post_slug}.html"
    out.write_text(html_text, encoding="utf-8")

    item = {
        "slug": post_slug,
        "title": title,
        "cat": topic.get("cat", "all"),
        "description": f"{title} 기준으로 주요 앱의 장점, 아쉬운 점, 추천 대상을 비교했습니다.",
        "apps": [get_slug(a) for a in selected],
        "appNames": [a.get("name", "") for a in selected],
        "created": today(),
        "url": f"{SITE_URL}/compare/{post_slug}.html"
    }
    index.append(item)
    save_json(INDEX_FILE, index)
    write_compare_index(index)

    state.setdefault("generated_slugs", []).append(topic["slug"])
    state.setdefault("daily_count", {})[today()] = current_count + 1
    state["last_generated"] = today()
    save_json(STATE_FILE, state)

    # sitemap 재생성: gen_static의 update_sitemap은 compare_index.json까지 포함하도록 패치됨
    try:
        from gen_static import update_sitemap
        n = update_sitemap(apps)
        log(f"🗺 compare 포함 sitemap.xml 재생성 — {n}개 URL")
    except Exception as e:
        log(f"⚠️ compare sitemap 반영 실패: {e}")

    log(f"🧠 compare 글 생성 완료: {title} → /compare/{post_slug}.html")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InnerApp compare post generator")
    parser.add_argument("--force", action="store_true", help="오늘 1개 제한을 무시하고 생성")
    parser.add_argument("--title", default="", help="수동 생성할 compare 글 제목")
    parser.add_argument("--cat", default="", help="카테고리 코드 예: sns, entertainment, productivity")
    parser.add_argument("--apps", default="", help="비교할 앱명 또는 slug를 콤마로 입력 예: 카카오톡,텔레그램,디스코드")
    parser.add_argument("--slug", default="", help="생성 파일 slug 예: kakaotalk-vs-telegram")
    args = parser.parse_args()
    run(force=args.force, title=args.title.strip() or None, cat=args.cat.strip() or None, app_names=args.apps.strip() or None, slug=args.slug.strip() or None)
