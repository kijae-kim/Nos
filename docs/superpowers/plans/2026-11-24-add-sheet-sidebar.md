# + 추가 팝업과 사이드바 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline).

**Goal:** + 는 어디서나 그 화면의 추가 팝업(열리면 ×), 메뉴는 NÓS 사이드바, 아래 바 색 구분.

**Spec:** `docs/superpowers/specs/2026-11-24-add-sheet-sidebar-design.md`

## Global Constraints

- 문구 존댓말, 색 토큰, 375px·라이트/다크·배/여정. 모델 바뀌지 않음(migrate 없음). 넓은 화면(900px+)은 그대로.
- 테스트 `cd web && ../.venv/bin/python manage.py test`. 브랜치 `feat/add-sheet`.

## Review Focus

1. 팝업 안 등록 화면에서 저장 실패(빈 제목 등)면 팝업에 그대로 오류, 성공이면 팝업 닫고 상세로.
2. 팝업이 열린 동안 + 는 × (누르면 닫힘), 닫히면 다시 +.
3. 사진 올리기(줄이기·HEIC·드라이브)가 팝업 안에서도 된다 (브라우저 확인).
4. 스크립트 없을 때: + 는 등록 화면 링크, NÓS 는 홈 링크.
5. 넓은 화면 날짜 팝업은 지금처럼 가운데 창.

### Task 1: 팝업 틀을 모든 화면에 · + 동작 · `?sheet=1`

- `layout_app.html`: `<dialog class="day-sheet">` 와 `calendar-popup.js` 를 여기로(캘린더 화면에서 지움). `?sheet=1` 이면 `html.in-sheet`, 사이드바·아래 바·메시지 외 머리 없음(`sheet_mode` 컨텍스트: `request.GET.sheet == "1"`).
- `calendar-popup.js`: 폰은 `show()`(모달 아님, 아래 바 위, `#dim` 어둡게), 넓은 화면은 `showModal()`. `window.nosOpenPage(url)`: 판에 `iframe.sheet-frame`(`url` + `sheet=1`), 불러온 주소가 시작 주소와 다르면 판 닫고 그 주소로 이동. Esc·dim 누르기로 닫기. 열림/닫힘 때 `html.sheet-open` 과 + 의 aria-label("닫기"/원래).
- `app.js` +: 판이 열려 있으면 닫기, 아니면 `data-fab-popup`→`nosOpenDay`, `data-fab-page`→`nosOpenPage`, 그 밖은 `href` 이동. 꾹 누르기·안내·반원 메뉴 지움.
- `?sheet=1` 화면의 뒤로(`.bar-head` 첫 `.circle`)는 부모에게 `postMessage({nos: "sheet-close"})`.
- 홈 + = 오늘 날짜 팝업, 추억 순간/기록 = `taste_create`/`?kind=place` 페이지 팝업, 앨범 = `photo_create`(앨범 안이면 `?album=`).
- 추억 '순간 남기기' 버튼 지움.
- 테스트(`AddSheetTests`): 홈 fab 에 day_popup 오늘, 추억·앨범 fab 에 `data-fab-page`, 모든 화면에 `day-sheet` 하나와 스크립트, `?sheet=1` 이면 tabbar 없음·`in-sheet`, 추억에 '순간 남기기' 링크 없음, `class="quick"` 없음.
- 커밋 `feat: + 를 누르면 그 화면의 추가 팝업`

### Task 2: NÓS 사이드바 · 아래 바 색

- `layout_app.html`: `nav.drawer`(새로 만들기 6: 일정=오늘 날짜 팝업, 순간·기록·사진=페이지 팝업, 메모=`memo_new`, 기념일=`anniversary_create` / 바로가기: 메모·기념일·가고 싶은 곳·우리·알림 설정(웹 푸시 켜진 서버만)). 로고(`.home-brand`)에 `data-drawer-open`, JS 가 열기(href 는 홈 그대로). 바깥·Esc·항목 누르면 닫기.
- 아래 바 색: 토큰 `--bar-bg`·`--bar-fg`·`--bar-on` (4조합), 바 위 경계.
- 테스트(`DrawerTests`): 홈·캘린더에 drawer 와 6개 링크·바로가기, 로고에 data-drawer-open.
- 커밋 `feat: NÓS 를 누르면 사이드바, 아래 바 색 구분`

### Task 3: 문서 — README·MEMO, 커밋 `docs: + 추가 팝업과 사이드바`
