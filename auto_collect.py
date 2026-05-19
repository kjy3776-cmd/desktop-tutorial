# -*- coding: utf-8 -*-
"""
auto_collect.py — 이너앱 신규 앱 자동 수집·등록 (하루 N개 제한)

차단(스팸) 회피 설계:
  - 하루 등록 개수 상한 (DAILY_LIMIT)
  - 요청 사이 랜덤 지연 (사람처럼 — 일정 간격 X)
  - 이미 등록된 앱 / 처리 시도한 앱 영구 기록 → 중복·재시도 폭주 방지
  - 후보 풀에서 매일 조금씩만 소진

사용:
  python auto_collect.py            # 하루 분량 수집 후 apps_data.js 갱신
  python auto_collect.py --dry-run  # 수집만, 파일 미수정
"""
import os
import sys
import json
import time
import random
import datetime

from scraper_core import build_app, CATEGORIES

# ─────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_JS      = os.path.join(BASE_DIR, "apps_data.js")
CANDIDATES   = os.path.join(BASE_DIR, "candidates.json")   # 수집 대기 후보 풀
STATE_FILE   = os.path.join(BASE_DIR, "collect_state.json")  # 처리 이력
LOG_FILE     = os.path.join(BASE_DIR, "collect.log")

DAILY_LIMIT  = 5          # ★ 하루 등록 상한 (질문 답변에 맞춰 조정)
MIN_DELAY    = 15         # 앱 사이 최소 대기(초) — 클라우드 IP는 넉넉히
MAX_DELAY    = 40         # 앱 사이 최대 대기(초)


def log(msg):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ─────────────────────────────────────────────────────────────
# 파일 입출력
# ─────────────────────────────────────────────────────────────
def load_apps():
    """apps_data.js → list."""
    if not os.path.exists(DATA_JS):
        return []
    raw = open(DATA_JS, encoding="utf-8").read()
    raw = raw.split("=", 1)[1].strip().rstrip(";").strip()
    return json.loads(raw)


def save_apps(apps):
    """list → apps_data.js (사이트가 읽는 형식 유지)."""
    body = json.dumps(apps, ensure_ascii=False, indent=2)
    with open(DATA_JS, "w", encoding="utf-8") as f:
        f.write("const APPS = " + body + ";")


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
# 메인 수집 루틴
# ─────────────────────────────────────────────────────────────
def run(dry_run=False):
    log("=" * 50)
    log(f"자동 수집 시작 (하루 상한 {DAILY_LIMIT}개, dry_run={dry_run})")

    apps   = load_apps()
    state  = load_json(STATE_FILE, {"processed": [], "last_run": "", "next_id": 0})
    cands  = load_json(CANDIDATES, [])

    if not cands:
        log("⚠️ candidates.json 비어있음 — 수집할 후보가 없습니다.")
        log("   candidates.json 형식: [[\"한글명\",\"영문명\",\"iTunesID\",\"패키지명\",\"카테고리\"], ...]")
        return

    # 하루 1회만 실행되도록 가드 (cron 중복 방지)
    today = datetime.date.today().isoformat()
    if state.get("last_run") == today and not dry_run:
        log(f"ℹ️ 오늘({today}) 이미 실행됨 — 스팸 방지를 위해 종료")
        return

    existing_names = {a["name"] for a in apps}
    processed      = set(state.get("processed", []))
    next_id        = max([a["id"] for a in apps], default=0) + 1

    # 미처리 + 미등록 후보만 추림
    queue = [c for c in cands
             if c[0] not in existing_names and c[0] not in processed]

    if not queue:
        log("✅ 등록할 신규 앱이 없습니다 (후보 풀 소진).")
        return

    # 후보 순서를 살짝 섞어 패턴화 방지
    random.shuffle(queue)
    target = queue[:DAILY_LIMIT]
    log(f"오늘 처리 대상 {len(target)}개: {[t[0] for t in target]}")

    added, valid_cats = [], set(CATEGORIES.keys())
    for idx, cand in enumerate(target, 1):
        name_kr, name_en, itunes_id, pkg, cat = (cand + ["", "", "", "", "life"])[:5]
        if cat not in valid_cats:
            log(f"   ⚠️ '{name_kr}' 알 수 없는 카테고리 '{cat}' → 'life'로 대체")
            cat = "life"

        log(f"[{idx}/{len(target)}] {name_kr}")
        rec = build_app(next_id, name_kr, name_en, itunes_id, pkg, cat)
        processed.add(name_kr)   # 성공/실패 무관 — 재시도 폭주 방지

        if rec:
            added.append(rec)
            next_id += 1

        # ★ 스팸 회피: 사람처럼 불규칙하게 쉰다
        if idx < len(target):
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            log(f"   ⏳ {delay:.0f}초 대기...")
            time.sleep(delay)

    # 결과 반영
    if added and not dry_run:
        apps.extend(added)
        save_apps(apps)
        log(f"💾 apps_data.js 갱신 — {len(added)}개 추가 (총 {len(apps)}개)")
        try:
            from gen_sitemap import generate
            n = generate()
            log(f"🗺  sitemap.xml 재생성 — {n}개 URL")
        except Exception as e:
            log(f"⚠️ sitemap 생성 실패: {e}")
    elif dry_run:
        log(f"🔍 [dry-run] {len(added)}개 수집 성공 (파일 미저장)")

    state["processed"] = sorted(processed)
    state["last_run"]  = today
    if not dry_run:
        save_json(STATE_FILE, state)

    log(f"완료: 성공 {len(added)} / 시도 {len(target)}")
    log("=" * 50)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    try:
        run(dry_run=dry)
    except KeyboardInterrupt:
        log("사용자 중단")
    except Exception as e:
        log(f"💥 예외 발생: {type(e).__name__}: {e}")
        raise
