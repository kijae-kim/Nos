# 기념일 알림 (웹 푸시) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기념일 당일(항상)과 하루 전·일주일 전(사용자 선택)에 커플 두 사람의 기기로 웹 푸시 알림을 보낸다.

**Architecture:** 새 앱 `notifications` 가 구독(`PushSubscription`)·보낸 기록(`PushLog`)·보낼 알림 계산(`schedule.py`)·보내기(`push.py`)·화면과 Cron 주소를 맡는다. 사용자 설정 두 칸은 `accounts.User` 에 둔다. Vercel Cron 이 매일 UTC 00:00 에 `/cron/anniversaries/` 를 부른다.

**Tech Stack:** Django 5.2, `pywebpush>=2.0,<3` (py-vapid 포함), 바닐라 JS, 서비스 워커 Push API, Vercel Cron.

**Spec:** `docs/superpowers/specs/2026-11-13-anniversary-push-design.md`

## Global Constraints

- 화면 문구·알림 문구는 부드러운 존댓말("~해요"). 코드 주석은 한국어. 색은 `app.css` 토큰만.
- 당일 알림은 끌 수 없다. `notify_day_before`, `notify_week_before` 기본값 `False`.
- 보내는 시각: `vercel.json` cron `"0 0 * * *"` (UTC 00시 = 한국 9시대).
- 열쇠 환경 변수: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `CRON_SECRET`. 셋(VAPID) 중 하나라도 없으면 알림 기능을 숨기고 500 을 내지 않는다.
- 비밀 값은 채팅·로그·응답에 출력하지 않는다.
- 보내기에 **성공한 것만** `PushLog` 에 남긴다. 60일 넘은 `PushLog` 는 Cron 이 지운다.
- 테스트는 `cd web && python manage.py test` (저장소 맨 위 `.venv`). 브랜치 `feat/anniversary-push`, 커밋 `feat: 한국어로 무엇을`.
- 마이그레이션 2개 추가 → Neon 확인 숫자 44 → **46**.

## Review Focus

1. Cron 이 같은 날 두 번 불림 → 두 번째는 아무것도 보내지 않는다 (Task 4 테스트).
2. 구독이 끝난 기기(푸시 서비스 404/410) → 그 구독만 지우고 같은 사람의 다른 기기에는 보낸다 (Task 3 테스트).
3. VAPID 열쇠가 없는 서버 → "우리" 화면 메뉴 줄 숨김, 알림 화면·구독 주소 404, Cron 503, 어디서도 500 없음 (Task 4·5 테스트).
4. 상대가 아직 없는 커플, 사귄 날이 비어 있는 커플 → 있는 사람·있는 기념일만으로 계산, 오류 없음 (Task 2 테스트).
5. 이름이 받침 없이 끝나거나 한글이 아닌 기념일("바다 생일", "1주년", "Anniversary", "500일") → 이에요/예요가 맞게 붙는다 (Task 2 테스트).

---

### Task 1: 모델과 사용자 설정 칸

**Files:**
- Create: `web/notifications/__init__.py`, `apps.py`, `models.py`, `admin.py`, `tests.py`, `migrations/__init__.py`
- Modify: `web/accounts/models.py` (두 칸), `web/config/settings.py` (`INSTALLED_APPS` 에 `"notifications"`)
- Create (생성): `web/accounts/migrations/0003_notify.py`, `web/notifications/migrations/0001_initial.py`

**Interfaces:**
- Produces:
  - `User.notify_day_before: bool = False`, `User.notify_week_before: bool = False` (verbose "하루 전 알림", "일주일 전 알림")
  - `PushSubscription(user FK→User related_name="push_subscriptions" CASCADE, endpoint CharField(500, unique), p256dh CharField(200), auth CharField(100), created_at auto_now_add)`
  - `PushLog(user FK CASCADE, key CharField(120), sent_on DateField)`, `UniqueConstraint(fields=["user","key"], name="unique_push_log")`

- [ ] **Step 1: 실패하는 테스트** — `notifications/tests.py` `ModelTests`:
  `test_user_notify_defaults_off` (새 사용자의 두 칸이 `False`), `test_push_log_unique` (같은 user·key 두 번 만들면 `IntegrityError`).
- [ ] **Step 2: 실행해서 실패 확인** — `cd web && python manage.py test notifications` → ImportError/에러.
- [ ] **Step 3: 모델 구현, `INSTALLED_APPS` 추가, `python manage.py makemigrations accounts notifications --name ...`** (accounts 는 `notify`, notifications 는 기본 `initial`).
- [ ] **Step 4: 통과 확인** — `python manage.py test` 전체 OK.
- [ ] **Step 5: 커밋** — `feat: 기념일 알림 모델과 사용자 설정 칸`

### Task 2: 보낼 알림 계산 (`schedule.py`)

**Files:**
- Create: `web/notifications/schedule.py`
- Test: `web/notifications/tests.py` `ScheduleTests`

**Interfaces:**
- Consumes: `anniversaries.services.build(couple, today) -> (upcoming: list[Item], past)`; `Item.title, .date, .days_left, .anniversary`.
- Produces:
  - `@dataclass Due: user, key: str, title: str, body: str, url: str = "/anniversaries/"`
  - `due_for_couple(couple, today: date) -> list[Due]`
  - `josa_ieyo(word: str) -> str` — `"500일"→"500일이에요"`, `"바다 생일"→"바다 생일이에요"`, `"파티"→"파티예요"`. 마지막 글자가 한글이면 받침 있으면 "이에요", 없으면 "예요"; 한글이 아니면 "이에요".
  - 열쇠: 직접 등록 `f"anniv:{a.pk}:{date.isoformat()}:{offset}"`, 자동 `f"auto:{title}:{date.isoformat()}:{offset}"` (offset ∈ 0,1,7).
  - 문구 (정확히):
    - offset 0: title `f"오늘은 {josa_ieyo(t)}"`, body `"함께한 날을 축하해요"`
    - offset 1: title `f"내일은 {josa_ieyo(t)}"`, body `f"{d.month}월 {d.day}일, 미리 준비해 볼까요?"`
    - offset 7: title `f"{t}까지 일주일 남았어요"`, body `f"{d.month}월 {d.day}일이에요"`
  - 받는 사람: `couple.members` 전원. offset 0 은 모두, 1 은 `notify_day_before`, 7 은 `notify_week_before` 인 사람만.

- [ ] **Step 1: 실패하는 테스트** (today 고정 `date(2026, 12, 1)`, 사귄 날을 골라 500일이 원하는 날에 오게):
  - `test_today_always_sent` — 오늘이 500일, 두 사람 모두 설정 꺼짐 → Due 2개, title `"오늘은 500일이에요"`, key `"auto:500일:2026-12-01:0"`.
  - `test_day_before_only_when_on` — 내일이 기념일, A 만 `notify_day_before=True` → Due 1개(A), title `"내일은 …이에요"`.
  - `test_week_before_only_when_on` — 7일 뒤, B 만 켬 → Due 1개(B), title `"…까지 일주일 남았어요"`.
  - `test_other_offsets_ignored` — 2일·6일 뒤 기념일 → Due 없음.
  - `test_custom_yearly_anniversary` — `Anniversary(title="바다 생일", date=date(1999,12,1), repeat_yearly=True)` → title `"오늘은 바다 생일이에요"`, key `f"anniv:{pk}:2026-12-01:0"`.
  - `test_single_member_and_no_start_date` — 멤버 1명·`start_date=None`·직접 기념일 오늘 → Due 1개, 오류 없음.
  - `test_josa` — `josa_ieyo("1주년")=="1주년이에요"`, `("바다 생일")` 받침 ㄹ→`"이에요"`, `("파티")=="파티예요"`, `("Anniversary")=="Anniversary이에요"`.
- [ ] **Step 2: 실행해서 실패 확인** — `python manage.py test notifications.tests.ScheduleTests`.
- [ ] **Step 3: `schedule.py` 구현** — `build(couple, today)` 의 upcoming 에서 `days_left in (0, 1, 7)` 만 고른다.
- [ ] **Step 4: 통과 확인.**
- [ ] **Step 5: 커밋** — `feat: 오늘 보낼 기념일 알림 계산`

### Task 3: 푸시 보내기와 열쇠

**Files:**
- Create: `web/notifications/push.py`, `web/notifications/management/__init__.py`, `management/commands/__init__.py`, `management/commands/make_vapid_keys.py`
- Modify: `web/requirements.txt` (`pywebpush>=2.0,<3`), `web/config/settings.py`, `.env.example`
- Test: `web/notifications/tests.py` `PushTests`, `VapidKeyCommandTests`

**Interfaces:**
- Produces:
  - settings: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `CRON_SECRET` (`os.getenv(..., "")`), `WEBPUSH_ENABLED = bool(세 VAPID 모두)`.
  - `push.send(subscription: PushSubscription, payload: dict) -> bool` — `pywebpush.webpush(subscription_info={"endpoint", "keys": {"p256dh", "auth"}}, data=json.dumps(payload, ensure_ascii=False), vapid_private_key=settings.VAPID_PRIVATE_KEY, vapid_claims={"sub": settings.VAPID_SUBJECT}, ttl=86400, timeout=5)`. `WebPushException` 의 응답 상태가 404·410 이면 구독을 지운다. 실패면 `False`, 예외를 밖으로 내지 않는다(그 외 `requests` 예외도).
  - `push.send_to_user(user, payload: dict) -> int` — 그 사람의 모든 구독에 보내고 성공 개수.
  - payload 모양: `{"title", "body", "url", "tag"}`.
  - 명령 `make_vapid_keys`: 새 열쇠를 만들어 `.env` 에 붙여 넣을 세 줄을 출력 (`VAPID_PUBLIC_KEY=<applicationServerKey, base64url 비압축 공개점>`, `VAPID_PRIVATE_KEY=<base64url 원시 개인 키>`, `VAPID_SUBJECT=mailto:you@example.com`). py-vapid(`py_vapid.Vapid`)로 만든다.

- [ ] **Step 1: 실패하는 테스트** (`notifications.push.webpush` 를 `unittest.mock.patch`):
  - `test_send_success` — 호출 인자의 `subscription_info["endpoint"]`, `ttl==86400` 확인, `True`.
  - `test_gone_subscription_deleted_others_still_sent` — 두 구독 중 하나에서 `WebPushException(response=status 410)` → 그 구독만 사라지고 `send_to_user` 는 1.
  - `test_network_error_returns_false` — `requests.exceptions.ConnectionError` → `False`, 구독은 남는다.
  - `test_make_vapid_keys_output_loads` — 명령 출력을 `call_command(..., stdout=buf)` 로 받아 개인 키 줄이 `py_vapid.Vapid.from_string(...)` 로 읽히고, 공개 키가 base64url 디코드 65바이트.
- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: `pip install -r web/requirements.txt`, 설정·`push.py`·명령 구현, `.env.example` 에 네 변수 주석과 만드는 명령 추가.**
- [ ] **Step 4: 통과 확인** (전체 테스트).
- [ ] **Step 5: 커밋** — `feat: 웹 푸시 보내기와 VAPID 열쇠 만들기 명령`

### Task 4: Cron 주소

**Files:**
- Create: `web/notifications/views.py` (`cron_anniversaries`), `web/notifications/urls.py`
- Modify: `web/config/urls.py` (`path("cron/anniversaries/", ...)`, `path("me/notifications/", include("notifications.urls"))`), `web/vercel.json` (`"crons": [{"path": "/cron/anniversaries/", "schedule": "0 0 * * *"}]`)
- Test: `web/notifications/tests.py` `CronTests`

**Interfaces:**
- Consumes: `schedule.due_for_couple`, `push.send_to_user`, `PushLog`.
- Produces: `cron_anniversaries(request)` name `"cron_anniversaries"`, GET 만.
  - `Authorization` 헤더가 `f"Bearer {settings.CRON_SECRET}"` 와 같아야 한다 (`hmac.compare_digest`, `CRON_SECRET` 비면 항상 401).
  - `WEBPUSH_ENABLED` 아니면 503 `{"ok": false, "reason": "vapid"}`.
  - 오늘 = `timezone.localdate()`. 멤버가 있는 모든 커플에 대해 Due 마다: `PushLog(user, key)` 있으면 건너뜀, 없으면 보내고 성공(≥1)일 때만 `PushLog(sent_on=today)` 만든다. 마지막에 `sent_on < today - 60일` 삭제.
  - 응답 `{"ok": true, "sent": n, "skipped": n, "failed": n}`.

- [ ] **Step 1: 실패하는 테스트** (`send_to_user` patch, `timezone.localdate` 를 `date(2026,12,1)` 로 patch):
  - `test_rejects_without_secret` / `test_rejects_wrong_secret` → 401, `send_to_user` 안 불림.
  - `test_503_without_vapid` — `override_settings(WEBPUSH_ENABLED=False, CRON_SECRET="s")` → 503.
  - `test_sends_and_logs` — 오늘 500일 커플 → `sent==2`, `PushLog` 2개.
  - `test_second_call_same_day_sends_nothing` → 두 번째 응답 `sent==0, skipped==2`, `send_to_user` 누적 2번.
  - `test_failed_send_not_logged` — `send_to_user` 가 0 → `failed==2`, `PushLog` 없음.
  - `test_old_logs_pruned` — 61일 전 PushLog 는 지워지고 59일 전은 남는다.
- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현, `vercel.json` 에 crons 추가.**
- [ ] **Step 4: 통과 확인.**
- [ ] **Step 5: 커밋** — `feat: 하루 한 번 기념일 알림을 보내는 Cron 주소`

### Task 5: 알림 화면과 구독 주소

**Files:**
- Modify: `web/notifications/views.py`, `web/notifications/urls.py`, `web/templates/couples/us.html` (설정 메뉴에 "알림" 줄, `{% if WEBPUSH_ENABLED %}`), `web/config/context.py` (`WEBPUSH_ENABLED` 넘기기)
- Create: `web/templates/notifications/settings.html`
- Test: `web/notifications/tests.py` `SettingsViewTests`

**Interfaces:**
- Produces (모두 `login_required`, `WEBPUSH_ENABLED` 아니면 404):
  - `notification_settings` `GET|POST /me/notifications/` name `"notifications"`. POST 는 체크박스 `notify_day_before`, `notify_week_before` 저장 → 메시지 "알림 설정을 저장했어요." → 같은 화면으로 redirect.
  - `push_subscribe` `POST /me/notifications/subscribe/` JSON `{"endpoint", "keys": {"p256dh", "auth"}}`. endpoint 가 `https://` 로 시작하고 500자 이하, 키 둘 다 있어야 한다(아니면 400). `update_or_create(endpoint=..., defaults={user, p256dh, auth})` → `{"ok": true}`.
  - `push_unsubscribe` `POST /me/notifications/unsubscribe/` JSON `{"endpoint"}` → 내 구독만 지움 → `{"ok": true}`.
  - `push_test` `POST /me/notifications/test/` → `send_to_user(user, {"title": "알림이 잘 와요", "body": "기념일이 다가오면 이렇게 알려 드릴게요", "url": "/anniversaries/", "tag": "test"})` → `{"ok": true, "sent": n}`.
  - 화면(`settings.html`, `layout_app.html` 을 확장, `calendar_subscribe.html` 과 같은 머리줄·뒤로 버튼): 당일 안내 문구 "기념일 당일에는 항상 알려 드려요", 두 스위치 폼, `<section data-push data-public-key="{{ VAPID_PUBLIC_KEY }}">` 안에 상태 문단 5개(`data-push-state="on|off|unsupported|ios-install|denied"`, 기본 모두 hidden)와 버튼(`data-push-on` "이 기기에서 알림 받기", `data-push-off` "이 기기에서 끄기", `data-push-test` "시험 알림 보내기").
    - on "이 기기에서 알림을 받고 있어요" · off "이 기기는 알림이 꺼져 있어요" · unsupported "이 브라우저에서는 알림을 받을 수 없어요" · ios-install "아이폰은 홈 화면에 추가한 앱에서 알림을 켤 수 있어요" · denied "알림이 막혀 있어요. 기기 설정에서 NÓS 알림을 허용해 주세요".
  - "우리" 메뉴 줄: 아이콘 `#i-bell` 이 `_icons.html` 에 없으면 추가, 제목 "알림", 작은 글 "기념일 당일과 미리 알림".

- [ ] **Step 1: 실패하는 테스트:**
  - `test_menu_hidden_without_vapid` / `test_menu_shown_with_vapid` — `/us/` 에 `reverse("notifications")` 포함 여부.
  - `test_pages_404_without_vapid` — 네 주소 모두 404.
  - `test_save_toggles` — POST `notify_week_before=on` → 그 칸만 True.
  - `test_subscribe_creates_and_moves_owner` — 같은 endpoint 로 B 가 구독하면 구독 1개, 주인 B.
  - `test_subscribe_rejects_bad_payload` — `http://` endpoint, 키 없음 → 400.
  - `test_unsubscribe_only_mine` — 상대 endpoint 로 요청해도 상대 구독은 남는다.
  - `test_push_test_calls_send` — `send_to_user` patch, 응답 `sent`.
- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인.**
- [ ] **Step 5: 커밋** — `feat: 우리 › 알림 화면과 기기 구독`

### Task 6: 서비스 워커와 화면 동작

**Files:**
- Modify: `web/templates/sw.js`, `web/static/js/app.js` (새 구역 `// ---------- 기념일 알림 ----------`), 필요하면 `web/static/css/app.css`

**Interfaces:**
- Consumes: Task 5 의 `data-push*` 속성과 주소, `csrfToken()` (app.js 13행).
- Produces:
  - `sw.js`: `push` 이벤트 → `event.data.json()` 으로 `self.registration.showNotification(title, {body, tag, icon: "/static/icons/icon-192.png", badge 같음, data: {url}})`. `notificationclick` → 알림 닫고, 열린 창이 있으면 그 창을 `url` 로 이동·포커스, 없으면 `clients.openWindow(url)`. 기존 install/activate 는 그대로.
  - app.js: `[data-push]` 가 있을 때만. 상태 판정 순서: Push 미지원(`serviceWorker`·`PushManager`·`Notification` 중 없음) → 아이폰·아이패드이고 홈 화면 앱이 아니면(`navigator.standalone` 도 `display-mode: standalone` 도 아님) `ios-install`, 아니면 `unsupported` / `Notification.permission === "denied"` → `denied` / `registration.pushManager.getSubscription()` 있으면 `on` 없으면 `off`. 상태에 맞는 문단만 보이고, 버튼은 on 일 때 끄기·시험, off 일 때 받기만.
  - 받기: `pushManager.subscribe({userVisibleOnly: true, applicationServerKey: <data-public-key base64url → Uint8Array>})` → `subscription.toJSON()` 을 JSON 으로 POST (`X-CSRFToken`) → 상태 다시 그림. 거절되면 `denied`.
  - 끄기: 서버에 endpoint POST 후 `subscription.unsubscribe()`.
  - 시험: POST 후 응답 `sent` 가 0 이면 "보내지 못했어요. 잠시 뒤 다시 해 볼까요?" 를 기존 안내 문구 방식(`.toast` 등 app.js 에 있는 것)으로.

- [ ] **Step 1: 개발용 열쇠 만들기** — `python web/manage.py make_vapid_keys` 출력을 `.env` 에 붙인다 (출력은 채팅에 옮기지 않는다). `CRON_SECRET` 도 `.env` 에 임의 값.
- [ ] **Step 2: 브라우저 확인 (375px, 라이트·다크, 배·여정)** — 개발 서버 `nos`, demo1 로그인 → 우리 › 알림 → 받기 → 허용 → 상태 on → 시험 알림이 뜬다 → 끄기 → off. 콘솔 오류 없음.
- [ ] **Step 3: Cron 수동 확인** — `curl -H "Authorization: Bearer <.env 값>" localhost:8000/cron/anniversaries/` → `{"ok": true, ...}`; 헤더 없이 → 401.
- [ ] **Step 4: 전체 테스트 OK.**
- [ ] **Step 5: 커밋** — `feat: 서비스 워커 알림 표시와 알림 켜기 화면 동작`

### Task 7: 문서와 운영 준비

**Files:**
- Modify: `README.md` (새 절 "기념일 알림 설정": 열쇠 만들기, Vercel 환경 변수 네 개, Cron 이 UTC 00시, 아이폰 조건), `MEMO.md` (4단계 기념일 알림 체크, Neon 확인 숫자 46, 사용자 할 일: 운영 열쇠 만들기·환경 변수·재배포·폰 시험), 맨 위 `CLAUDE.md` (git 에 없음, 로컬만: 다음 할 일 갱신)

- [ ] **Step 1: 문서 갱신.**
- [ ] **Step 2: 전체 테스트 OK, `git status` 에 `.env*` 없음 확인.**
- [ ] **Step 3: 커밋** — `docs: 기념일 알림 설정 방법`
- [ ] **Step 4 (사용자 확인 뒤): main 병합·푸시, `ENV_FILE=.env.neon python web/manage.py migrate`, `showmigrations | grep -c "\[X\]"` 가 46.**
