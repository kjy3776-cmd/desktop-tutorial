# GitHub Actions 자동 수집 설정 가이드

GitHub Actions로 **매일 새벽 4시(KST), 신규 앱 5개를 무료로 자동 수집**합니다.
PC를 켜둘 필요도, 서버 비용도 없습니다.

---

## 사전 준비

GitHub 계정과 저장소가 필요합니다. 공개(public) 저장소면 Actions가 완전 무제한 무료입니다.
이 작업은 하루 2~3분이라 비공개(private) 저장소의 월 2,000분 무료 한도로도 충분합니다.

---

## 1단계 — 저장소에 파일 올리기

이 폴더의 파일을 GitHub 저장소 **루트**에 그대로 올립니다.
`.github/workflows/auto-collect.yml` 폴더 구조를 꼭 유지하세요.

```
저장소 루트/
├── .github/workflows/auto-collect.yml   ← 자동화 설정
├── index.html
├── apps_data.js
├── sitemap.xml
├── robots.txt
├── ads.txt
├── scraper_core.py
├── auto_collect.py
├── fix_android.py
├── gen_sitemap.py
└── candidates.json
```

GitHub 웹사이트에서 "Add file → Upload files"로 끌어다 놓으면 됩니다.

---

## 2단계 — Actions 권한 켜기 (1회)

저장소 → **Settings → Actions → General** →
맨 아래 **Workflow permissions**에서
**"Read and write permissions"** 선택 후 저장.

> 이걸 안 하면 수집은 되지만 `apps_data.js` 자동 커밋이 실패합니다.

---

## 3단계 — 첫 실행 (수동)

저장소 → **Actions 탭 → "이너앱 자동 수집" → "Run workflow"** 버튼 클릭.

2~3분 뒤 초록 체크가 뜨면 성공. `apps_data.js`에 새 앱이 커밋된 게 보입니다.
이후로는 매일 새벽 4시에 알아서 돕니다.

---

## 4단계 — 사이트 자동 반영

### Netlify를 쓰는 경우 (이너앱 기본)
Netlify에서 이 GitHub 저장소를 연결만 해두면, Actions가 `apps_data.js`를
커밋할 때마다 Netlify가 자동으로 재배포합니다. **추가 설정 불필요.**

연결 방법: Netlify → Add new site → Import an existing project → GitHub 저장소 선택.

### GitHub Pages를 쓰는 경우
`auto-collect.yml` 맨 아래 "GitHub Pages 배포" 단계의 주석(`#`)을 풀어주세요.
그리고 저장소 Settings → Pages에서 소스를 `gh-pages` 브랜치로 지정합니다.

---

## 스팸(봇) 차단 회피 — 클라우드 IP 대응

GitHub Actions는 데이터센터 IP라 스토어가 봇으로 의심할 여지가 큽니다.
그래서 다음 안전장치를 넣었습니다:

| 장치 | 설명 |
|---|---|
| 랜덤 시작 지연 | 매일 정각이 아니라 4:00~4:30 사이 무작위 시각에 시작 |
| 앱 사이 15~40초 랜덤 대기 | 일정 간격이면 봇 패턴 — 불규칙하게 |
| 지수 백오프 재시도 | 일시 차단 시 3·6·12초 늘려가며 3회 재시도 |
| 하루 5개 상한 | 한 번에 몰아 받지 않음 |
| 동시 실행 방지 | 이전 작업 미완료 시 새 작업 차단 |

문제가 생기면 `auto_collect.py`의 `DAILY_LIMIT`을 3으로 낮추세요.

---

## 후보 앱 추가

`candidates.json`에 줄을 추가하고 커밋하면 다음 수집 주기에 자동 등록됩니다.

```json
["앱한글명", "AppEnglishName", "아이튠즈ID", "안드로이드패키지명", "카테고리"]
```

ID·패키지명을 모르면 `""`로 둬도 이름 검색으로 수집됩니다.
현재 후보 풀 30개(게임 10개 포함)가 들어있어 약 6일치 분량입니다.

---

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| Actions 실패: 푸시 권한 오류 | 2단계 "Read and write permissions" 확인 |
| 수집은 됐는데 사이트 그대로 | Netlify 연결 확인 / GitHub Pages 단계 주석 해제 확인 |
| 안드로이드 데이터 자꾸 누락 | `DAILY_LIMIT` 낮추고, 첫 세팅 때 `fix_android.py` 1회 실행 |
| 하루에 여러 번 돌리고 싶음 | 권장 안 함 — `collect_state.json`이 하루 1회로 막음 |
