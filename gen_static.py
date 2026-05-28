# -*- coding: utf-8 -*-
"""
gen_static.py — 앱별 정적 HTML 페이지 생성기 (SEO 핵심)

왜 필요한가:
  현재 사이트는 JavaScript SPA라 크롤러가 앱 내용을 못 읽음.
  이 스크립트는 앱마다 실제 HTML 파일을 생성해서
  "카카오톡 다운로드", "이환 PC 다운로드" 같은 키워드로
  구글·네이버에 직접 색인되게 함.

생성 결과:
  /app/카카오톡.html  →  innerapple.com/app/카카오톡.html
  /app/이환.html      →  innerapple.com/app/이환.html
  /category/game.html →  innerapple.com/category/game.html
  sitemap.xml 자동 업데이트

사용:
  python gen_static.py        # 전체 생성
  python gen_static.py --new  # 정적 파일 없는 앱만 생성
"""
import os
import sys
import json
import datetime

from auto_collect import load_apps, log
from gen_sitemap import SITE_URL

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
APP_DIR   = os.path.join(BASE_DIR, "app")
CAT_DIR   = os.path.join(BASE_DIR, "category")
COMPARE_DIR = os.path.join(BASE_DIR, "compare")
COMPARE_INDEX = os.path.join(BASE_DIR, "compare_index.json")
SITEMAP   = os.path.join(BASE_DIR, "sitemap.xml")

CAT_LABELS = {
    "sns":"소셜·커뮤니티", "entertainment":"엔터테인먼트", "shopping":"쇼핑",
    "food":"음식·배달", "finance":"금융·재테크", "game":"게임",
    "productivity":"생산성·도구", "life":"라이프스타일",
    "education":"교육", "health":"건강·운동", "travel":"여행·지도",
}

# ─────────────────────────────────────────────────────────────
# HTML 템플릿
# ─────────────────────────────────────────────────────────────
def _esc(s):
    """HTML 특수문자 이스케이프."""
    return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


import re as _re

def get_slug(app: dict) -> str:
    if app.get('slug'):
        return app['slug']
    s = app.get('name','').lower().strip()
    s = _re.sub(r'[^\w\s-]', '', s)
    s = _re.sub(r'[\s_]+', '-', s)
    s = _re.sub(r'-+', '-', s).strip('-')
    return s or f"app-{app.get('id','')}"




def _load_compare_posts():
    # compare_index.json -> list
    if not os.path.exists(COMPARE_INDEX):
        return []
    try:
        return json.load(open(COMPARE_INDEX, encoding="utf-8"))
    except Exception:
        return []


def _related_apps_html(app: dict, apps: list, max_count: int = 6) -> str:
    # 같은 카테고리 앱 내부링크
    if not apps:
        return ""
    slug = get_slug(app)
    related = [a for a in apps if a.get("cat") == app.get("cat") and get_slug(a) != slug][:max_count]
    if not related:
        return ""
    items = ""
    for a in related:
        items += f'''<a class="rel-card" href="{SITE_URL}/app/{get_slug(a)}.html">
  <img src="{_esc(a.get('icon',''))}" alt="{_esc(a.get('name',''))} 아이콘" loading="lazy">
  <span>{_esc(a.get('name',''))}</span>
</a>'''
    return f'''<div class="card"><h2>🔗 같은 카테고리 추천 앱</h2><div class="rel-grid">{items}</div></div>'''


def _compare_links_html(app: dict, max_count: int = 4) -> str:
    # 앱 상세 <-> compare 글 내부링크
    posts = _load_compare_posts()
    if not posts:
        return ""
    app_slug = get_slug(app)
    name = app.get("name", "")
    matched = []
    for p in posts:
        if app_slug in (p.get("apps") or []) or name in (p.get("appNames") or []):
            matched.append(p)
    if not matched:
        matched = [p for p in posts if p.get("cat") == app.get("cat")]
    matched = matched[:max_count]
    if not matched:
        return ""
    items = "".join(
        f'''<a class="compare-link" href="{SITE_URL}/compare/{_esc(p.get('slug',''))}.html">{_esc(p.get('title','앱 비교·분석'))}</a>'''
        for p in matched
    )
    return f'''<div class="card"><h2>🧠 관련 앱 비교·분석</h2><div class="compare-list">{items}</div></div>'''


def app_html(app: dict, all_apps=None) -> str:
    slug     = get_slug(app)
    name     = _esc(app["name"])
    cat_label= _esc(CAT_LABELS.get(app.get("cat",""), app.get("cat","")))
    dev      = _esc(app.get("developer",""))
    desc     = _esc(app.get("desc",""))
    seo_desc = _esc(app.get("seoDesc","") or app.get("desc","")[:150])
    icon     = _esc(app.get("icon",""))
    ios_url  = _esc(app.get("iosUrl",""))
    and_url  = _esc(app.get("androidUrl",""))
    pc_url   = _esc(app.get("pcUrl",""))
    pc_type  = app.get("pcType","")
    url      = f"{SITE_URL}/app/{slug}.html"

    # 다운로드 버튼
    btns = ""
    if ios_url:
        btns += f'<a href="{ios_url}" class="btn btn-ios" rel="noopener" target="_blank">🍎 App Store 다운로드</a>\n'
    if and_url:
        btns += f'<a href="{and_url}" class="btn btn-and" rel="noopener" target="_blank">🤖 Google Play 다운로드</a>\n'

    # PC 다운로드 섹션
    pc_section = ""
    if pc_url and pc_type == "download":
        pc_section = f"""
    <div class="pc-box">
      <span class="pc-icon">⬇️</span>
      <div>
        <div class="pc-title">{name} PC 버전 다운로드</div>
        <div class="pc-sub">PC에 설치해서 더 편하게 이용할 수 있어요</div>
      </div>
      <a href="{pc_url}" class="btn btn-pc" rel="noopener" target="_blank">다운로드</a>
    </div>"""
    elif pc_url and pc_type == "web":
        pc_section = f"""
    <div class="pc-box">
      <span class="pc-icon">🌐</span>
      <div>
        <div class="pc-title">{name} PC 웹 버전</div>
        <div class="pc-sub">웹 브라우저에서 바로 이용할 수 있어요</div>
      </div>
      <a href="{pc_url}" class="btn btn-pc" rel="noopener" target="_blank">PC로 열기</a>
    </div>"""

    # 리뷰
    reviews_html = ""
    for r in (app.get("reviews") or [])[:5]:
        reviews_html += f"""
      <div class="review">
        <b>{_esc(r.get('user',''))}</b>
        <span class="stars">{'⭐' * int(r.get('rating',0))}</span>
        <p>{_esc(r.get('text',''))}</p>
      </div>"""

    # 스크린샷
    shots_html = ""
    for s in (app.get("screenshots") or [])[:3]:
        shots_html += f'<img src="{_esc(s)}" alt="{name} 스크린샷" loading="lazy">\n'

    # 구조화 데이터
    reviews_data = app.get("reviews") or []
    rating_json = ""
    if reviews_data:
        avg = sum(r.get("rating",0) for r in reviews_data) / len(reviews_data)
        rating_json = f''',
  "aggregateRating": {{
    "@type": "AggregateRating",
    "ratingValue": "{avg:.1f}",
    "reviewCount": "{len(reviews_data)}",
    "bestRating": "5"
  }}'''

    spec_ios = app.get("spec_ios", {})
    spec_and = app.get("spec_and", {})
    related_apps_section = _related_apps_html(app, all_apps or [])
    compare_links_section = _compare_links_html(app)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} 앱 다운로드 </title>
<meta name="description" content="{name} 앱 다운로드 정보와 iOS, 안드로이드, PC 버전 링크를 확인하세요. {seo_desc[:90]}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{name} 앱 다운로드">
<meta property="og:description" content="{seo_desc[:150]}">
<meta property="og:image" content="{icon}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="website">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "{name}",
  "applicationCategory": "{cat_label}",
  "operatingSystem": "iOS, Android{'，Windows' if pc_url else ''}",
  "author": {{"@type": "Organization", "name": "{dev}"}},
  "description": "{seo_desc[:200]}",
  "url": "{url}",
  "image": "{icon}"{rating_json}
}}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--blue:#1B64DA;--green:#00C471;--gray-50:#F9FAFB;--gray-200:#E5E7EB;--gray-600:#4B5563;--gray-900:#111827}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Pretendard',sans-serif;background:var(--gray-50);color:var(--gray-900);line-height:1.6}}
nav{{background:#fff;border-bottom:1px solid var(--gray-200);padding:0 20px;height:56px;display:flex;align-items:center}}
nav a{{font-size:20px;font-weight:700;color:var(--blue);text-decoration:none}}
.page{{max-width:800px;margin:0 auto;padding:24px 20px}}
.back{{color:var(--blue);text-decoration:none;font-weight:600;display:block;margin-bottom:20px}}
.card{{background:#fff;border-radius:20px;padding:24px;border:1px solid var(--gray-200);margin-bottom:20px}}
.header{{display:flex;gap:20px;align-items:center;margin-bottom:20px}}
.icon{{width:88px;height:88px;border-radius:20px;object-fit:cover;background:#eee}}
.app-name{{font-size:26px;font-weight:700}}
.app-page-title{{
  font-size:14px;
  font-weight:700;
  color:#111827;
  margin-top:4px;
}}
.app-dev{{color:var(--blue);font-size:14px;margin-top:4px}}
.btn{{display:inline-flex;align-items:center;gap:8px;padding:14px 20px;border-radius:12px;font-weight:700;color:#fff;text-decoration:none;font-size:15px;transition:opacity .2s}}
.btn:hover{{opacity:.85}}
.btn-ios{{background:#000}}
.btn-and{{background:var(--green)}}
.btn-pc{{background:var(--blue);white-space:nowrap}}
.btns{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
.pc-box{{display:flex;align-items:center;gap:14px;padding:16px;background:#EBF1FD;border-radius:12px;margin-bottom:16px}}
.pc-icon{{font-size:28px}}
.pc-title{{font-size:14px;font-weight:700}}
.pc-sub{{font-size:12px;color:var(--gray-600)}}
.desc{{color:var(--gray-600);font-size:15px;line-height:1.7;white-space:pre-wrap}}
.seo-desc{{margin-top:14px;padding:14px;background:var(--gray-50);border-left:3px solid var(--blue);border-radius:8px;font-size:14px;color:#374151;line-height:1.7}}
h2{{font-size:17px;margin-bottom:14px}}
.shots{{display:flex;gap:12px;overflow-x:auto;padding-bottom:8px}}
.shots img{{height:300px;border-radius:12px;border:1px solid var(--gray-200)}}
.spec table{{width:100%;border-collapse:collapse;font-size:14px}}
.spec th,.spec td{{padding:10px;border-bottom:1px solid var(--gray-50);text-align:left}}
.spec th{{background:var(--gray-50);color:var(--gray-600);width:90px}}
.review{{padding:14px 0;border-bottom:1px solid var(--gray-50)}}
.review b{{font-size:13px}}
.review p{{font-size:14px;color:var(--gray-600);margin-top:4px}}
.stars{{color:#FFB800;font-size:12px;margin-left:6px}}
footer{{max-width:800px;margin:32px auto 0;padding:20px;border-top:1px solid var(--gray-200);font-size:13px;color:var(--gray-600)}}
footer a{{color:var(--blue)}}
.rel-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:12px}}
.rel-card{{display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center;text-decoration:none;color:var(--gray-900);background:var(--gray-50);border:1px solid var(--gray-200);border-radius:14px;padding:12px;font-size:13px;font-weight:700}}
.rel-card img{{width:52px;height:52px;border-radius:12px;object-fit:cover}}
.compare-list{{display:flex;flex-direction:column;gap:8px}}
.compare-link{{display:block;padding:12px 14px;background:#EBF1FD;border-radius:12px;color:var(--blue);font-weight:700;text-decoration:none;font-size:14px}}
</style>
</head>
<body>
<nav><a href="{SITE_URL}/">이너앱<span style="color:var(--green)">.</span></a></nav>
<div class="page">
  <a class="back" href="{SITE_URL}/">← 목록으로 돌아가기</a>

  <div class="card">
    <div class="header">
      <img class="icon" src="{icon}" alt="{name} 아이콘">
      <div>
        <div class="app-name">{name}</div>
        <div class="app-page-title">{name} 앱 다운로드</div>
        <div class="app-dev">{dev}</div>
        <div style="font-size:13px;color:#9CA3AF;margin-top:2px">{cat_label}</div>
      </div>
    </div>

    <div class="btns">{btns}</div>
    {pc_section}

    <p class="desc">{desc}</p>
    {"<p class='seo-desc'>" + seo_desc + "</p>" if app.get("seoDesc") else ""}
  </div>

  {"<div class='card'><h2>📸 미리보기</h2><div class='shots'>" + shots_html + "</div></div>" if shots_html else ""}

  <div class="card spec">
    <h2>⚙️ 상세 사양</h2>
    <table>
      <tr><th>구분</th><td><b>iOS</b></td><td><b>Android</b></td></tr>
      <tr><th>버전</th><td>{_esc(spec_ios.get('ver','-'))}</td><td>{_esc(spec_and.get('ver','-'))}</td></tr>
      <tr><th>최소 OS</th><td>{_esc(spec_ios.get('os','-'))}</td><td>{_esc(spec_and.get('os','-'))}</td></tr>
      <tr><th>용량</th><td>{_esc(spec_ios.get('size','-'))}</td><td>{_esc(spec_and.get('size','-'))}</td></tr>
    </table>
  </div>

  {"<div class='card'><h2>💬 사용자 리뷰</h2>" + reviews_html + "</div>" if reviews_html else ""}
  {compare_links_section}
  {related_apps_section}
</div>

<footer>
  <a href="{SITE_URL}/">이너앱 홈</a> · {cat_label} 앱 ·
  {name} iOS 다운로드 / {name} 안드로이드 다운로드{' / ' + name + ' PC 다운로드' if pc_url else ''}
</footer>
</body>
</html>"""


def category_html(cat: str, apps: list) -> str:
    label = CAT_LABELS.get(cat, cat)
    url   = f"{SITE_URL}/category/{cat}.html"
    items = ""
    for a in apps:
        items += f"""<a href="{SITE_URL}/app/{get_slug(a)}.html" class="app-item">
  <img src="{_esc(a.get('icon',''))}" alt="{_esc(a['name'])} 아이콘" loading="lazy">
  <div class="app-name">{_esc(a['name'])}</div>
</a>\n"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{label} 앱 추천 - 다운로드·리뷰 | 이너앱</title>
<meta name="description" content="이너앱이 직접 써보고 추천하는 {label} 앱 {len(apps)}개. iOS·안드로이드 다운로드, 상세 사양, 실사용자 리뷰를 확인하세요.">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{label} 앱 추천 | 이너앱">
<meta property="og:url" content="{url}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Pretendard',sans-serif;background:#F9FAFB;color:#111827}}
nav{{background:#fff;border-bottom:1px solid #E5E7EB;padding:0 20px;height:56px;display:flex;align-items:center}}
nav a{{font-size:20px;font-weight:700;color:#1B64DA;text-decoration:none}}
.page{{max-width:800px;margin:0 auto;padding:24px 20px}}
h1{{font-size:24px;font-weight:700;margin-bottom:6px}}
.sub{{color:#9CA3AF;font-size:14px;margin-bottom:24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px}}
.app-item{{background:#fff;border-radius:16px;padding:16px;text-decoration:none;color:#111827;text-align:center;border:1px solid #E5E7EB;transition:all .2s}}
.app-item:hover{{transform:translateY(-3px);box-shadow:0 4px 16px rgba(0,0,0,.08)}}
.app-item img{{width:60px;height:60px;border-radius:14px;margin-bottom:8px;object-fit:cover}}
.app-name{{font-size:13px;font-weight:600}}
footer{{max-width:800px;margin:32px auto 0;padding:20px;border-top:1px solid #E5E7EB;font-size:13px;color:#6B7280}}
</style>
</head>
<body>
<nav><a href="{SITE_URL}/">이너앱<span style="color:#00C471">.</span></a></nav>
<div class="page">
  <h1>{label} 앱 추천</h1>
  <p class="sub">직접 써보고 추천하는 {label} 앱 {len(apps)}개 · iOS·안드로이드 다운로드</p>
  <div class="grid">{items}</div>
</div>
<footer>이너앱 · {label} 카테고리 · {' / '.join(a['name'] for a in apps[:8])} 외</footer>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# 사이트맵 갱신 (정적 파일 URL 포함)
# ─────────────────────────────────────────────────────────────
def update_sitemap(apps: list):
    today = datetime.date.today().isoformat()
    cats  = sorted(set(a["cat"] for a in apps))

    def u(loc, pri, freq="weekly"):
        return (f"  <url>\n    <loc>{loc}</loc>\n"
                f"    <lastmod>{today}</lastmod>\n"
                f"    <changefreq>{freq}</changefreq>\n"
                f"    <priority>{pri}</priority>\n  </url>")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             u(f"{SITE_URL}/", "1.0", "daily")]

    # 카테고리 정적 페이지
    for c in cats:
        lines.append(u(f"{SITE_URL}/category/{c}.html", "0.8"))

    # compare 인덱스 + 비교·추천 정적 페이지
    compare_posts = _load_compare_posts()
    lines.append(u(f"{SITE_URL}/compare/", "0.85", "daily"))
    for p in compare_posts:
        if p.get("slug"):
            lines.append(u(f"{SITE_URL}/compare/{p['slug']}.html", "0.75", "weekly"))

    # 앱 정적 페이지 + SPA slug URL
    for a in apps:
        slug = get_slug(a)
        lines.append(u(f"{SITE_URL}/app/{slug}.html", "0.7"))
        lines.append(u(f"{SITE_URL}/?app={slug}", "0.5"))

    lines.append("</urlset>")
    with open(SITEMAP, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(lines)


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
def run(new_only=False):
    log("=" * 50)
    log("정적 HTML 생성 시작")

    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(CAT_DIR, exist_ok=True)
    os.makedirs(COMPARE_DIR, exist_ok=True)

    apps = load_apps()
    cats = {}
    created = 0

    for app in apps:
        slug = get_slug(app)
        path = os.path.join(APP_DIR, f"{slug}.html")
        if new_only and os.path.exists(path):
            cats.setdefault(app["cat"], []).append(app)
            continue
        html = app_html(app, apps)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        cats.setdefault(app["cat"], []).append(app)
        created += 1

    # 카테고리 페이지
    for cat, cat_apps in cats.items():
        path = os.path.join(CAT_DIR, f"{cat}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(category_html(cat, cat_apps))

    # compare index 보장
    try:
        from gen_compare_posts import write_compare_index, load_json, INDEX_FILE
        write_compare_index(load_json(INDEX_FILE, []))
    except Exception as e:
        log(f"⚠️ compare index 생성 스킵: {e}")

    # 사이트맵 갱신
    n = update_sitemap(apps)
    log(f"✅ 앱 HTML {created}개 / 카테고리 {len(cats)}개 생성 / 사이트맵 {n}줄")
    log("=" * 50)
    return created


if __name__ == "__main__":
    new_only = "--new" in sys.argv
    run(new_only=new_only)
