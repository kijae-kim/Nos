# 캘린더 날짜 팝업 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 날짜를 누르면(폰은 꾹 눌러도) 그날 일정과 빠른 추가 칸이 든 팝업, 폰 달력 칸에 일정 이름.

**Spec:** `docs/superpowers/specs/2026-11-22-calendar-popup-design.md`

## Global Constraints

- 문구 존댓말, 색 토큰, 375px·넓은 화면·라이트/다크. 모델 바뀌지 않음(migrate 없음). 브랜치 `feat/calendar-popup`.
- 테스트 `cd web && ../.venv/bin/python manage.py test`.

## Review Focus

1. 다른 커플·상대 개인 일정이 팝업 목록에 안 보임 (Task 1 테스트).
2. 팝업 저장 실패(이름표만, 끝 < 시작) → 400 + 팝업 HTML 에 오류, 일정 안 생김 (Task 1).
3. 여러 날 일정이 가운데 날 팝업에도 보임 (Task 1).
4. 스크립트 없이 칸을 누르면 일정 추가 화면(`?date=`) (Task 2 테스트).
5. 데스크톱 끌기 직후 클릭으로 팝업이 열리지 않음 (Task 2 브라우저 확인).

### Task 1: 팝업 주소와 빠른 추가 폼

- `QuickEventForm(EventForm)`: place·memo·color 칸 없음(저장 때 빈 값·"sky"), date 숨은 칸.
- `GET|POST calendar/day/<str:day>/` `day_popup`: 조각 템플릿 `couples/_day_popup.html`. GET 200. POST 성공 → `{"ok": true, "url": _calendar_url(date)}`, 실패 → 400 조각. 잘못된 날짜 404. 로그인.
- `event_create` 가 `?text=` 초기값을 받음.
- 테스트(`DayPopupTests`): 그날·여러 날 일정, 남의 일정 없음, 저장 성공 JSON·이름표 생성, 실패 400 오류 문구, 잘못된 날짜 404, 로그인 필요, `event_create?text=` 초기값.
- 커밋 `feat: 캘린더 날짜 팝업 주소와 빠른 추가`

### Task 2: 캘린더 화면·팝업 스크립트·폰 칸

- calendar.html: 폰 `.day`·데스크톱 `.cell` 에 `href=event_create?date=` + `data-day-popup`; 폰 칸에 `cell.pieces`/`more`; "일정 추가" 버튼 2곳 지움; 폰 목록은 늘 다가오는 일정; `<dialog class="day-sheet">` 하나.
- `static/js/calendar-popup.js`: 누름·꾹 누름(500ms)·Enter → 열기, fetch 로 내용, 폼 제출 fetch, 실패 HTML 바꿔 넣기, 성공 이동, 끌기 중·직후 무시, 바깥 누르면 닫기, "자세히 쓰기" 는 글 이어 붙여 이동.
- CSS: 바텀시트/가운데 창, 폰 칸 높이·조각.
- 테스트(`CalendarPopupScreenTests`): 칸 링크·data 속성, 버튼 없음, 폰 칸에 조각 이름, 스크립트 로드.
- 브라우저 확인 후 커밋 `feat: 캘린더 날짜를 누르면 일정 추가 팝업`

### Task 3: 문서 — README·MEMO·CLAUDE.md, 커밋 `docs: 캘린더 팝업 설명`
