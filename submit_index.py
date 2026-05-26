# -*- coding: utf-8 -*-
"""
submit_index.py — 새로 추가된 앱 URL을 검색엔진에 자동 색인 요청

지원:
  --bing   : Bing URL Submission API (공식, 안정적)
  --google : Google Indexing API (서비스 계정 필요)

환경변수:
  BING_API_KEY                : Bing 웹마스터 API 키
  GOOGLE_SERVICE_ACCOUNT_JSON : 구글 서비스 계정 JSON 전체 내용

사용:
  python submit_index.py --bing
  python submit_index.py --google
  python submit_index.py --bing --google
"""
import os
import sys
import json
import requests
from auto_collect import load_apps, log

SITE_URL = "https://innerapple.com"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index_state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {"submitted": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_new_urls(state: dict) -> list:
    """아직 색인 요청 안 한 새 URL만 반환."""
    apps = load_apps()
    submitted = set(state.get("submitted", []))
    urls = []
    for a in apps:
        slug = a.get("slug") or a["name"]
        url = f"{SITE_URL}/app/{slug}.html"
        if url not in submitted:
            urls.append(url)
    return urls


# ─────────────────────────────────────────────────────────────
# Bing URL Submission API
# ─────────────────────────────────────────────────────────────
def submit_bing(urls: list) -> list:
    """
    Bing 웹마스터 URL 제출 API
    공식 문서: https://docs.microsoft.com/en-us/bingwebmaster/getting-access
    하루 10,000개 제한
    """
    api_key = os.environ.get("BING_API_KEY", "")
    if not api_key:
        log("⚠️ BING_API_KEY 없음 — Secrets에 등록 필요")
        return []

    endpoint = f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey={api_key}"
    # 한 번에 최대 500개
    batch = urls[:500]
    payload = {
        "siteUrl": SITE_URL,
        "urlList": batch
    }
    try:
        r = requests.post(endpoint, json=payload,
                          headers={"Content-Type": "application/json"}, timeout=30)
        if r.status_code == 200:
            log(f"✅ Bing 색인 요청 성공: {len(batch)}개 URL")
            return batch
        else:
            log(f"❌ Bing 실패 {r.status_code}: {r.text[:200]}")
            return []
    except Exception as e:
        log(f"❌ Bing 오류: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# Google Indexing API
# ─────────────────────────────────────────────────────────────
def submit_google(urls: list) -> list:
    """
    Google Indexing API (서비스 계정 기반)
    하루 200개 제한
    """
    svc_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not svc_json_str:
        log("⚠️ GOOGLE_SERVICE_ACCOUNT_JSON 없음 — Secrets에 등록 필요")
        return []

    try:
        import google.oauth2.service_account as sa
        import google.auth.transport.requests as ga_req
        creds_info = json.loads(svc_json_str)
        creds = sa.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/indexing"]
        )
        auth_req = ga_req.Request()
        creds.refresh(auth_req)
        token = creds.token
    except Exception as e:
        log(f"❌ Google 인증 실패: {e}")
        log("   pip install google-auth 가 필요합니다")
        return []

    endpoint = "https://indexing.googleapis.com/v3/urlNotifications:publish"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    submitted = []
    # 하루 200개 제한 준수
    for url in urls[:200]:
        payload = {"url": url, "type": "URL_UPDATED"}
        try:
            r = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            if r.status_code == 200:
                submitted.append(url)
            else:
                log(f"  ⚠️ Google 실패({r.status_code}): {url}")
        except Exception as e:
            log(f"  ⚠️ Google 오류: {e}")

    if submitted:
        log(f"✅ Google 색인 요청 성공: {len(submitted)}개 URL")
    return submitted


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
def run():
    do_bing   = "--bing"   in sys.argv
    do_google = "--google" in sys.argv

    if not do_bing and not do_google:
        log("사용법: python submit_index.py --bing / --google")
        return

    state = load_state()
    new_urls = get_new_urls(state)

    if not new_urls:
        log("ℹ️ 새로 색인 요청할 URL 없음")
        return

    log(f"색인 요청 대상: {len(new_urls)}개")
    submitted_all = []

    if do_bing:
        done = submit_bing(new_urls)
        submitted_all.extend(done)

    if do_google:
        done = submit_google(new_urls)
        submitted_all.extend(done)

    # 중복 제거 후 상태 저장
    state["submitted"] = sorted(set(state.get("submitted", [])) | set(submitted_all))
    save_state(state)
    log(f"완료 — 누적 제출 URL: {len(state['submitted'])}개")


if __name__ == "__main__":
    run()
