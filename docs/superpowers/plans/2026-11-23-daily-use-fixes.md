# 써 보며 나온 것 고치기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline).

**Goal:** 하루 써 보고 나온 12가지 — + 버튼이 화면별 추가, 글로 일정, 메모 체크 단축·알림, 색 12개, 홈 '오늘' 카드 등.

**Architecture:** 기존 Django 템플릿 + 바닐라 JS 에 덧붙인다. 새 파이썬 모듈 `couples/quickparse.py` 하나, 마이그레이션 3개.

**Spec:** `docs/superpowers/specs/2026-11-23-daily-use-fixes-design.md`

## Global Constraints

- 문구 존댓말, 색은 토큰, 375px·넓은 화면·라이트/다크·배/여정 확인.
- 마이그레이션 accounts·memos·couples 각 1개 → Neon 확인 숫자 **58**. 외부 유료 API 없음.
- 테스트 `cd web && ../.venv/bin/python manage.py test`. 브랜치 `feat/daily-fixes`.

## Review Focus

1. 메모 `-5도`·줄 가운데 `- `·한글 조합 중에는 체크로 안 바뀜 (Task 2 브라우저 확인).
2. 메모 알림: 쓴 사람 본인에게 안 감, 30분 안 두 번째 저장은 안 보냄, 푸시 실패해도 저장 200 (Task 4 테스트).
3. 글 해석: 올해 지난 날짜는 내년, 날짜 없는 글은 None, `25~27일` 끝나는 날, `오후 3시 반` 15:30 (Task 5 테스트).
4. + 버튼: 꾹 누르면 어느 화면이든 메뉴, 스크립트 없을 때도 메뉴 링크는 쓸 수 있음 (Task 3).
5. '오늘' 카드에 다른 커플 것·상대 개인 일정이 안 보임 (Task 6 테스트).

### Task 1: 작은 화면 고치기 (모델 안 바뀜)

- 시작 화면: `theme.js` 가 `html.splash-on` 동안 `theme-color` 를 시작 화면 색(테마·모드별 `--hero-bg` 값 표)으로, 끝나면 `syncBar()`. `.splash` 가 안전 영역까지 덮음.
- 캘린더: `.day.sel` 채움 지우고 오늘은 고리만(`app.css` 320·506·673 줄 근처 세 곳 모두 고리 방식).
- 추억: `segment three` 지우고 머리 줄 오른쪽 `a.who-pill` (다음 값으로 가는 링크, 글 `모두`/`나`/`상대`), 기록 탭에선 없음.
- 색칠 지도: 지역 이름 글자 없앰. 가고 싶은 곳 지역(`region_data` 에 `wish` 코드 목록 더함: 가고 싶은 곳 좌표 → 지역, 다녀온 곳 판정과 같은 함수)은 옅은 색 + 빗금 패턴, 지도 아래 범례.
- 테스트(`DailyFixScreenTests`): 추억 화면에 who-pill 링크와 `segment three` 없음, region_data 에 wish 코드.
- 커밋 `fix: 시작 화면 바·오늘 표시·추억 버튼·색칠 지도`

### Task 2: 메모 체크 단축 (`memo-editor.js`)

- `input` 뒤(조합 중이 아닐 때) 지금 줄이 글 줄이고 글이 `- ` 또는 `/todo ` 로 시작하며 커서가 그 바로 뒤면 → 그 글자 지우고 체크 줄로, 커서는 줄 맨 앞.
- 브라우저 확인(크롬 375px): `- 우유`, `/todo 여권`, `-5도`, 줄 가운데 `a - b`, 한글 조합 직후.
- 커밋 `feat: 메모에서 - 나 /todo 로 체크 항목`

### Task 3: + 버튼이 화면별 추가

- `layout_app.html`: 각 화면 템플릿이 `{% block fab_href %}` 로 주소를 준다 (캘린더 `event_create?date=<오늘 또는 그 달 1일>` + `data-day-popup`, 추억 순간/기록 `taste_create`/`?kind=place`, 앨범 `photo_create`). 없으면 지금처럼 메뉴 버튼.
- `app.js`: 주소가 있으면 짧게 누르면 그 주소(캘린더는 `calendar-popup.js` 의 열기 함수 `window.nosOpenDay(day)`), 500ms 꾹 누르면 메뉴, 처음 한 번 안내 토스트(localStorage `nos.fabHint`). `aria-label` 은 "일정 추가" 등.
- 테스트(`FabTests`): 캘린더·추억 두 탭·앨범에 각 주소, 홈에는 없음, 이번 달 아닐 때 1일.
- 커밋 `feat: + 버튼이 화면마다 추가 버튼으로`

### Task 4: 색 12개 · 메모 알림 (마이그레이션 3개)

- `COLOR_CHOICES` 에 6개 더함(기존 이름 유지, 10자 이하). `app.css` 4조합 토큰. `_choices.html` swatch 는 동그라미만(이름은 `aria-label`/숨은 글). 마이그레이션 couples.
- `User.notify_memo = BooleanField("메모 알림", default=True)` + 알림 설정 화면 칸. `Memo.notified_at = DateTimeField(null=True)`.
- `memos/notify.py`: `notify_partner(memo, editor) -> bool` — 상대가 있고 `notify_memo`, `notified_at` 이 30분 전보다 옛것(또는 없음)이면 `send_to_user(partner, {"title": f"{editor.display_name}님이 메모를 고쳤어요", "body": memo.title, "url": memo 주소, "tag": f"memo-{pk}"})`, `notified_at` 갱신. 예외는 로그만. `memo_save` 성공 뒤 부름(제목이 빈 메모는 안 보냄).
- 테스트(`MemoNotifyTests`, push.send 를 mock): 상대에게 1번, 본인 아님, 30분 안 두 번째 없음, 30분 뒤 다시, 꺼 두면 없음, 예외에도 저장 200. 색: 새 색으로 일정 저장, 폼에 12개.
- 커밋 `feat: 색 12개와 메모 고치면 상대에게 알림`

### Task 5: 글로 일정 (`couples/quickparse.py`)

- `parse(text: str, today: date) -> dict | None` — `{"date": date, "end_date": date|None, "start_time": time|None, "end_time": time|None, "title": str}`, 날짜 못 찾으면 None.
- 테스트(`QuickParseTests`): `12월 25일 찜질방가기`(today 11-23 → 올해 12-25, 제목 "찜질방가기"), `3월 1일 등산`(→ 내년), `12/25`, `25일`, `내일 저녁 7시 영화`(19:00), `오후 3시 반 카페`(15:30), `19:30 저녁`, `3시~5시`, `다음 주 금요일 여행`, `금요일 장보기`, `12월 25일~27일 여행`, `25~27일`, `그냥 글`(None), `@데이트 내일 산책 #공원`(제목에 @ # 남음).
- 뷰 `calendar_quick` `GET ?q=` → 해석되면 `{"ok": true, "day": "YYYY-MM-DD", "fields": {...}}`, 아니면 `{"ok": false, "url": event_create?text=}`. 캘린더 위 입력칸(폰·넓은 화면), JS 가 받아 `nosOpenDay(day, fields)` 로 팝업 칸을 채움.
- 테스트(`CalendarQuickTests`): 성공 JSON, 실패 url, 로그인 필요, 입력칸 있음.
- 커밋 `feat: 글로 쓰면 날짜를 알아듣는 일정 입력`

### Task 6: 홈 '오늘' 카드

- `couples/views.py` home: 메모·일정·추억·사진 목록 대신 `today_events`(오늘·내일, visible_to), `next_event`(없을 때 하나), `partner_news`(3일 안 상대가 만든 순간·기록·사진, 상대가 고친 메모, 최근순 3개: `{kind, title, url, at}`).
- `home.html`: 다가오는 기념일 아래 '오늘' 카드 하나, 나머지 섹션 지움.
- 테스트(`HomeTodayTests`): 오늘 일정 보임, 상대 개인 일정 안 보임, 상대 새 사진·메모 보임, 내 것 안 보임, 4일 전 것 안 보임, 빈 안내.
- 커밋 `feat: 홈을 오늘 카드 하나로`

### Task 7: 문서 — README·MEMO(확인 숫자 58)·CLAUDE.md, 커밋 `docs: 써 보며 고친 것`
