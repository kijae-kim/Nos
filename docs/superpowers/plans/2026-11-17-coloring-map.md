# 다녀온 곳 색칠 지도 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 추억 › 기록에 경계만 그린 SVG 색칠 지도(전국 시·군·구 → 서울 구 → 구의 동)를 더하고, 장소·사진 위치로 자동 칠하며 직접 칠하기/지우기를 저장한다.

**Architecture:** 서버는 점(장소·사진 좌표)과 직접 표시(`RegionMark`)만 준다. 브라우저(`static/js/coloring-map.js`)가 경계 파일을 받아 점을 지역에 나누고, 칠함을 계산해 SVG 로 그린다. 직접 표시는 JSON POST 로 저장.

**Tech Stack:** Django 5.2, 바닐라 JS + SVG, topojson-client 3.1.0(jsdelivr), 경계: `kr-municipalities-2018.topo.json`(있음) + `seoul-dongs-2013.topo.json`(새로).

**Spec:** `docs/superpowers/specs/2026-11-17-coloring-map-design.md`

## Global Constraints

- 문구 존댓말, 주석 한국어, 색은 토큰. 375px·라이트/다크·배/여정 확인.
- `RegionMark.level ∈ {"sigungu","dong"}`, `state ∈ {"on","off"}`, `code` 숫자 4~10자리, `(couple, level, code)` 유일. `state="auto"` 요청은 행 삭제.
- 칠함 = `on` 이거나 (`off` 아님 이고 점 ≥1). 서울 구: 위 + "칠해진 동이 있으면" 도 칠함. 구 표시는 동에 영향 없음.
- 점: 위치 있는 장소 글(분류 "장소")과 위치 있는 사진, 각자 좌표. 해외·바다 점은 버림.
- 외부 지도·API 호출 없음 (topojson-client 만 CDN). 경계 파일은 색칠 지도를 열 때만, 동 파일은 서울 단계를 처음 열 때만.
- 마이그레이션 `couples.0012_region_mark` → Neon 확인 숫자 **50**, 배포보다 먼저.
- 테스트 `cd web && ../.venv/bin/python manage.py test`. 브랜치 `feat/coloring-map`.

## Review Focus

1. 직접 지운(`off`) 지역은 새 사진·장소가 그 안에 생겨도 안 칠해짐 (Task 2 브라우저 확인, Task 1 데이터 테스트).
2. 다른 커플의 점·표시가 데이터에 안 섞임 (Task 1 테스트).
3. 잘못된 level/state/code·JSON 아닌 본문 → 400, 500 없음 (Task 1 테스트).
4. 폰(375px)에서 서울 동 423개 지도가 끊김 없이 그려지고 눌러짐 (Task 2 브라우저 확인).
5. 동만 직접 칠해도 구·전국 색과 "구 N/25" 에 반영 (Task 2 브라우저 확인).

---

### Task 1: 색칠 표시 저장과 데이터

**Files:** Modify `web/couples/models.py` (`RegionMark`), `web/couples/views.py` (`region_data`, `region_mark`), `web/couples/urls.py`; migration `0012_region_mark`; Test `RegionMapTests`

**Interfaces — Produces:**
- `RegionMark(couple FK CASCADE related_name="region_marks", level Char 10 choices, code Char 10, state Char 3 choices, updated_by FK User SET_NULL null, updated_at auto_now)`, `UniqueConstraint(couple, level, code, name="unique_region_mark")`.
- `GET /tastes/regions/data/` name `region_data` (login): `{"points": [{"lat","lng","kind":"place"|"photo"}], "marks": [{"level","code","state"}]}` 내 커플만.
- `POST /tastes/regions/mark/` name `region_mark` (login, CSRF): JSON `{"level","code","state":"on"|"off"|"auto"}` → `{"ok": true}`; `on/off` 는 update_or_create, `auto` 는 delete. 검사 실패·JSON 아님 → 400 `{"ok": false}`.

- [ ] **Step 1: 실패하는 테스트**: 데이터에 내 위치 있는 장소·사진만(위치 없는 것·순간 글·다른 커플 제외, kind 구분); marks 는 내 커플 것만; mark on → 행, 다시 off → 같은 행 state off, auto → 삭제; 잘못된 level `"gu"`, state `"maybe"`, code `"abc"`/`"1"`/`"12345678901"`, 본문 `"x"` → 400; 로그인 필요(302).
- [ ] **Step 2–4. Step 5: 커밋** — `feat: 색칠 지도 표시 저장과 데이터`

### Task 2: 색칠 지도 화면

**Files:** Create `web/static/js/coloring-map.js`, `web/static/geo/seoul-dongs-2013.topo.json` (southkorea/seoul-maps `kostat/2013/json/seoul_submunicipalities_topo_simple.json` 그대로); Modify `web/templates/couples/taste.html` (기록 탭: `핀 지도 · 색칠 지도` 전환, 색칠 칸 `<section data-coloring-map data-data-url data-mark-url data-geo-kr data-geo-seoul hidden>`: 경로 `data-crumbs`, 요약 `data-color-summary`, `<svg data-color-svg>`, 안내 `data-color-note`, 아래 칸 `data-region-panel`), `web/static/css/app.css`

**Interfaces — Consumes:** Task 1 JSON·주소, CSRF 쿠키(`csrftoken`).
- 전환: 기본 핀 지도, localStorage `nos.recordView` 에 `pin|color` (try/catch). 색칠 지도를 처음 열 때 로드.
- 단계 `nation`(KR 250, 서울(코드 앞 `11`) 구는 누르면 `seoul`), `seoul`(코드 `11…` 25개), `gu:<code>`(동 중 대표점이 그 구 안에 있는 것).
- 시·도 표: 11 서울, 21 부산, 22 대구, 23 인천, 24 광주, 25 대전, 26 울산, 29 세종, 31 경기, 32 강원, 33 충북, 34 충남, 35 전북, 36 전남, 37 경북, 38 경남, 39 제주.
- 투영: 단계 피처들의 경계 상자로 `x = (lng - lng0) * cos(lat0)`, `y = -(lat - lat0)`, viewBox 맞춤. 단계별 path 문자열은 한 번 만들어 캐시.
- 색: 칠함 `fill: var(--primary)` 불투명도 .75, 안 칠함 `var(--tile)`, 경계 선 `var(--surface)` 1px(non-scaling-stroke), 고른 지역 굵은 선 `var(--text)`. 이름 글자: 서울·구 단계는 전부, 전국은 칠해진 곳만, 글자 크기는 화면 기준 일정(SVG 텍스트 크기를 viewBox 비율로 계산).
- 아래 칸: 이름, 근거("장소 N곳 · 사진 M장" / "기록 없음"), 버튼 `칠하기`(on) `지우기`(off) `자동으로`(auto) — 지금 상태 강조, 누르면 바로 반영 후 POST, 실패 시 되돌리고 "저장하지 못했어요. 잠시 뒤 다시 해 볼까요?". 서울 구 칸에는 `동까지 보기`.
- 요약: 전국 "시·군·구 N/250", 서울 "구 N/25 · 동 N/423", 구 "동 N/M".

- [ ] **Step 1: 동 경계 파일 받기**(98KB 확인).
- [ ] **Step 2: 구현.**
- [ ] **Step 3: 브라우저 확인 (375px·넓은 화면, 라이트/다크, 배/여정)** — 개발 데이터: 성수 장소·사진 → 전국에서 서울 성동구 칠함, 서울 단계 성동구 칠함, 성동구 단계 성수동 쪽 동 칠함; 제주 장소 → 제주시; 아무 동 직접 칠하기 → 그 구·요약 반영, 새로고침 뒤에도 유지; 칠해진 구 지우기 → 안 칠함, 새로고침 유지, `자동으로` → 다시 칠함; 서울 단계 동 423개 그려지는 시간·누르기; 다른 탭(핀 지도) 전환·기억; 콘솔 오류 없음.
- [ ] **Step 4: 전체 테스트. Step 5: 커밋** — `feat: 다녀온 곳 색칠 지도 (전국·서울·동)`

### Task 3: 문서

- [ ] README "추억 · 기록 지도" 에 색칠 지도 한 단락 + 데이터 출처(seoul-maps KOSTAT 2013), MEMO(체크, 확인 숫자 50, 다음: 가고 싶은 곳 저장 → 1년 리캡), 로컬 CLAUDE.md. 커밋 `docs: 색칠 지도 설명`.
