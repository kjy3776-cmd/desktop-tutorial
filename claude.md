# claude.md — 이너앱(InnerApp) 프로젝트 규칙

## 프로젝트 개요
앱 큐레이션 사이트. 정적 HTML + `apps_data.js` 데이터 + Python 수집 자동화.
AdSense 수익 목적. Vultr Seoul 서버 운영.

## 기술 스택
- 프론트: 단일 `index.html` (Vanilla JS, Pretendard 폰트)
- 데이터: `apps_data.js` (`const APPS = [...]` 형식)
- 수집: Python 3 + `google-play-scraper` + iTunes Search API

## 규칙 (실수 방지)

- [규칙] Google Play 수집 시 패키지명을 하드코딩에만 의존하지 말 것.
  - [이유] 하드코딩 패키지명(`com.sampleapp.baemin` 등)이 실제와 달라 22개 중 9개 안드로이드 데이터 누락 발생.
  - [조치] `resolve_android_package()`로 4단계 역추적: 하드코딩 → iOS bundleId → 한글명 검색 → 영문명 검색 + 이름 유사도 검증.

- [규칙] 리뷰 수집 실패가 앱 본문 수집 실패로 번지지 않게 할 것.
  - [이유] 기존 `parse_android`는 `reviews()` 예외 시 전체 `None` 반환 → 멀쩡한 앱도 누락.
  - [조치] 리뷰는 별도 try 블록. 실패해도 본문·사양은 보존.

- [규칙] 자동 수집은 하루 1회·랜덤 지연·개수 상한을 반드시 지킬 것.
  - [이유] 스토어 측 봇 차단 회피. 일정 간격 요청은 봇으로 탐지됨.
  - [조치] `collect_state.json`의 `last_run` 가드 + 앱 사이 8~22초 랜덤 지연 + `DAILY_LIMIT`.

- [규칙] `apps_data.js` 저장 시 `const APPS = [...];` 형식을 정확히 유지할 것.
  - [이유] 사이트 `index.html`이 이 전역 변수를 직접 읽음. 형식 깨지면 사이트 전체 백지.
  - [조치] `save_apps()`가 형식 보존. 수정 후 `load_apps()` 라운드트립 검증.

- [규칙] 앱 데이터·사이트맵 변경 시 `sitemap.xml`을 항상 재생성할 것.
  - [이유] 검색엔진 색인 누락 방지.
  - [조치] `auto_collect.py`·`fix_android.py`가 수집 후 `gen_sitemap.generate()` 자동 호출.

- [규칙] 클라우드(GitHub Actions 등) 데이터센터 IP에서 수집 시 추가 차단 회피를 적용할 것.
  - [이유] 데이터센터 IP는 가정용 IP보다 스토어 봇 탐지에 더 취약. 차단 시 수집 실패율 급증.
  - [조치] 워크플로우 시작 시 0~30분 랜덤 지연 + 앱 사이 15~40초 지연 + `_gp_app_retry()` 지수 백오프 3회.

## 실행 환경
- 자동 수집: GitHub Actions (무료, 매일 KST 04:00). `.github/workflows/auto-collect.yml`.
- 사이트 반영: GitHub push → Netlify 자동 재배포.

## 알려진 한계
- SPA 구조라 네이버 크롤러(Yeti)의 JS 미실행으로 개별 앱 페이지 색인이 약함.
  → 다음 단계: 정적 HTML 페이지 생성기 도입 검토.

## 가드레일
- 수집 스크립트는 읽기 전용 API만 사용. 파일 쓰기는 프로젝트 폴더 내로 한정.
- `candidates.json`의 카테고리는 `scraper_core.CATEGORIES` 키만 허용. 그 외는 'life'로 대체.
