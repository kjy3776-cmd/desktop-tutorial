# -*- coding: utf-8 -*-
"""
gen_compare_posts.py - compare 글 페이지 생성용 수정본 핵심:
- 모든 compare 페이지 왼쪽 위 로고는 innerapple.com 홈("/")으로 연결
- 오른쪽 위 검색창 포함
- /apps_data.js 검색 연동
"""
import os, json, random, datetime, requests

from auto_collect import load_apps, log
from gen_static import get_slug

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMPARE_DIR = os.path.join(BASE_DIR, "compare")
STATE_FILE = os.path.join(BASE_DIR, "compare_state.json")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"
SITE_URL = "https://innerapple.com"

os.makedirs(COMPARE_DIR, exist_ok=True)

TOPICS = [
    {"slug":"best-sns-messenger-apps","title":"무료 메신저 앱 추천","keywords":["카카오톡","네이버","인스타그램"]},
    {"slug":"ott-video-app-comparison","title":"OTT 앱 비교 추천","keywords":["넷플릭스","티빙","왓챠"]},
    {"slug":"shopping-app-comparison","title":"쇼핑 앱 비교 추천","keywords":["쿠팡","무신사","컬리"]},
]

SYSTEM_PROMPT = """
당신은 한국 앱 추천 미디어 '이너앱'의 에디터입니다.
앱 비교·추천 SEO 글을 작성하세요.
규칙:
- 1200~2000자
- 실제 사용자가 비교하는 느낌
- 과장 금지
- 앱별 장단점, 추천 대상, 선택 기준 포함
- 검색 키워드를 자연스럽게 포함
"""

STYLE_AND_NAV = """
<style>
:root{--blue:#1B64DA;--gray-50:#F9FAFB;--gray-200:#E5E7EB;--gray-400:#9CA3AF;--gray-600:#4B5563;--gray-900:#111827}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:var(--gray-50);color:var(--gray-900);line-height:1.75}
nav{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.92);backdrop-filter:blur(20px);border-bottom:1px solid var(--gray-200)}
.nav-inner{max-width:1100px;margin:0 auto;display:flex;align-items:center;height:56px;padding:0 20px;gap:12px}
.nav-logo{font-size:20px;font-weight:800;color:var(--blue);text-decoration:none;flex-shrink:0}
.nav-search{flex:1;max-width:360px;position:relative;margin-left:auto}
.nav-search input{width:100%;padding:8px 36px 8px 14px;border:1.5px solid var(--gray-200);border-radius:999px;font-size:14px;outline:none;background:var(--gray-50)}
.search-icon{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:var(--gray-400);font-size:15px}
.search-results{position:absolute;top:calc(100% + 8px);left:0;right:0;background:#fff;border:1px solid var(--gray-200);border-radius:14px;box-shadow:0 8px 24px rgba(0,0,0,.1);z-index:200;max-height:320px;overflow-y:auto;display:none}
.search-results.show{display:block}
.search-item{display:flex;align-items:center;gap:12px;padding:10px 14px;cursor:pointer}
.search-item:hover{background:var(--gray-50)}
.search-item img{width:36px;height:36px;border-radius:9px;object-fit:cover;background:#eee}
.search-item-name{font-size:14px;font-weight:700}.search-item-cat{font-size:11px;color:var(--gray-400)}
.search-empty{padding:20px;text-align:center;color:var(--gray-400);font-size:14px}
.wrap{max-width:900px;margin:0 auto;padding:36px 20px}
.back{display:inline-block;margin-bottom:24px;color:var(--blue);font-weight:700;text-decoration:none}
.hero,.content{background:#fff;border:1px solid var(--gray-200);border-radius:24px;padding:28px;margin-bottom:20px}
h1{font-size:30px;margin-bottom:10px}.sub{color:var(--gray-600)}
.app-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:14px;margin-top:22px}
.app-card{text-decoration:none;color:inherit;border:1px solid var(--gray-200);border-radius:18px;padding:16px;text-align:center;background:#fff}
.app-card img{width:64px;height:64px;border-radius:16px;object-fit:cover;margin-bottom:8px}
article{font-size:16px;white-space:normal}
@media(max-width:600px){.nav-inner{height:52px;padding:0 14px}.nav-logo{font-size:17px}.nav-search{max-width:none}.wrap{padding:24px 14px}.hero,.content{padding:20px}}
</style>
"""

NAV_HTML = """
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="/">이너앱.</a>
    <div class="nav-search">
      <input id="searchInput" type="search" placeholder="앱 검색...">
      <span class="search-icon">🔍</span>
      <div id="searchResults" class="search-results"></div>
    </div>
  </div>
</nav>
"""

SEARCH_SCRIPT = """
<script src="/apps_data.js"></script>
<script>
const input=document.getElementById('searchInput');
const results=document.getElementById('searchResults');
function getSlug(app){return app.slug || String(app.name||'').toLowerCase().replace(/[^\\w\\s-]/g,'').replace(/[\\s_]+/g,'-').replace(/-+/g,'-').replace(/^-|-$/g,'');}
function renderSearch(q){
  const apps=(window.APPS||APPS||[]);
  const query=q.trim().toLowerCase();
  if(!query){results.classList.remove('show');results.innerHTML='';return;}
  const matched=apps.filter(a=>(a.name||'').toLowerCase().includes(query)||(a.developer||'').toLowerCase().includes(query)).slice(0,8);
  results.classList.add('show');
  if(!matched.length){results.innerHTML='<div class="search-empty">검색 결과가 없어요</div>';return;}
  results.innerHTML=matched.map(a=>`
    <div class="search-item" onclick="location.href='/app/${getSlug(a)}.html'">
      <img src="${a.icon||''}" alt="${a.name}">
      <div><div class="search-item-name">${a.name}</div><div class="search-item-cat">${a.cat||''}</div></div>
    </div>`).join('');
}
input.addEventListener('input',e=>renderSearch(e.target.value));
document.addEventListener('click',e=>{if(!e.target.closest('.nav-search'))results.classList.remove('show')});
</script>
"""

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"generated": [], "last_date": ""}

def save_state(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_compare_content(title, apps):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    prompt = f"주제: {title}\n대상 앱: {', '.join([a['name'] for a in apps])}\n비교·추천 SEO 글 작성."
    r = requests.post(API_URL, headers={
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }, json={
        "model": MODEL,
        "max_tokens": 2200,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }, timeout=60)
    if r.status_code == 200:
        return r.json()["content"][0]["text"].strip()
    log(f"Claude compare 오류 {r.status_code}: {r.text[:100]}")
    return None

def build_html(title, content, apps, slug):
    cards = ""
    for app in apps:
        cards += f"""
        <a class="app-card" href="/app/{get_slug(app)}.html">
            <img src="{app.get('icon','')}" alt="{app['name']}">
            <div>{app['name']}</div>
        </a>"""
    article = content.replace("\n", "<br><br>")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | 이너앱</title>
<meta name="description" content="{title} 정보를 이너앱에서 비교해보세요.">
<link rel="canonical" href="{SITE_URL}/compare/{slug}.html">
{STYLE_AND_NAV}
</head>
<body>
{NAV_HTML}
<main class="wrap">
<a class="back" href="/compare/">← 앱 비교·분석으로 돌아가기</a>
<section class="hero">
<h1>{title}</h1>
<p class="sub">앱별 특징과 추천 대상을 비교해 정리했습니다.</p>
<div class="app-grid">{cards}</div>
</section>
<section class="content">
<article>{article}</article>
</section>
</main>
{SEARCH_SCRIPT}
</body>
</html>"""

def run(force=False, title=None, slug=None, app_names=None):
    apps = load_apps()
    state = load_state()
    today = datetime.date.today().isoformat()
    if not force and state.get("last_date") == today:
        log("오늘 compare 글 이미 생성됨")
        return

    if title and slug and app_names:
        topic = {"title": title, "slug": slug, "keywords": [x.strip() for x in app_names.split(",") if x.strip()]}
    else:
        unused = [t for t in TOPICS if t["slug"] not in state.get("generated", [])]
        if not unused:
            state["generated"] = []
            unused = TOPICS
        topic = random.choice(unused)

    selected = []
    for keyword in topic["keywords"]:
        for app in apps:
            if keyword.lower() in app.get("name","").lower():
                selected.append(app); break

    if not selected:
        log("compare 앱 매칭 실패")
        return

    content = generate_compare_content(topic["title"], selected)
    if not content:
        content = f"{topic['title']} 비교 글입니다. " + ", ".join([a["name"] for a in selected]) + "의 특징과 다운로드 정보를 확인해보세요."

    html = build_html(topic["title"], content, selected, topic["slug"])
    out = os.path.join(COMPARE_DIR, f"{topic['slug']}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    if topic["slug"] not in state.get("generated", []):
        state.setdefault("generated", []).append(topic["slug"])
    state["last_date"] = today
    save_state(state)
    log(f"compare 글 생성 완료: {topic['title']}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    p.add_argument("--title")
    p.add_argument("--slug")
    p.add_argument("--apps")
    args = p.parse_args()
    run(force=args.force, title=args.title, slug=args.slug, app_names=args.apps)
