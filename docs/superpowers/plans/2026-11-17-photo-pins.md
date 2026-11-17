# 앨범 사진 핀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사진마다 작은 사진(320px)을 만들고, 기록 핀 지도에서 장소 카드 사진 줄과 사진 핀으로 그날 찍은 사진을 둘러본다.

**Architecture:** `Photo.thumb`/`thumb_size` + `couples/thumbs.py`(Pillow). 올리기 경로(`PhotoForm.save_for`)에서 만들고 지울 때 함께 지운다. 지도는 `photo_map_data`(사진 핀)·`place_photo_strip`(장소 줄) JSON 과 map.js 의 사진 겹쳐 보기.

**Tech Stack:** Django 5.2, Pillow, R2(django-storages), 바닐라 JS(map.js), Leaflet/카카오맵.

**Spec:** `docs/superpowers/specs/2026-11-17-photo-pins-design.md`

## Global Constraints

- 마이그레이션 `couples.0015_photo_thumb` → Neon 확인 숫자 **54**, 배포보다 먼저.
- 작은 사진: 긴 변 320px, JPEG 품질 80, EXIF 없음, 투명은 흰 바탕. 못 만들면 `None`(올리기는 성공).
- 이름: 원본 이름의 확장자 앞에 `-thumb` + `.jpg` (예: `photos/7/ab12.jpg` → `photos/7/ab12-thumb.jpg`).
- `quota.used_bytes` 에 `thumb_size` 포함. R2 LIST 금지.
- 사진 핀 = 위치 있고 (`place` 없음 또는 `place` 에 위치 없음), 최근 순 500장. 장소 줄 60장, 넘으면 "모두 보기 ›"(장소 화면 `taste_detail`).
- 문구 존댓말, 색 토큰, 375px·라이트/다크·배/여정. 테스트 `cd web && ../.venv/bin/python manage.py test`. 브랜치 `feat/photo-pins`.

## Review Focus

1. 사진 지우기·바꾸기·커플 마지막 사람 나가기 → 작은 사진 파일도 지워짐 (Task 1 테스트).
2. HEIC/깨진 파일 올리기 → 사진은 저장, `thumb` 비고 `thumb_url` 은 원본 (Task 1 테스트).
3. 다른 커플 사진·장소가 `photo_map_data`·`place_photo_strip` 에 없음 / 404 (Task 2 테스트).
4. 손으로 위치 없는 장소에 묶은 사진도 사진 핀으로 나옴 (Task 2 테스트).
5. 사진 핀이 많을 때(500 초과) 최근 500장만 (Task 2 테스트).

---

### Task 1: 작은 사진 만들기·지우기·한도·채우기 명령·앨범 격자

**Files:** Create `web/couples/thumbs.py`, `couples/management/commands/make_photo_thumbs.py`; Modify `couples/models.py` (Photo), `couples/forms.py` (`PhotoForm.save_for`), `couples/views.py` (`photo_delete`, `leave`), `couples/quota.py`, `templates/couples/album.html`, `album_detail.html`, `taste_detail.html`; migration `0015_photo_thumb`; Test `PhotoThumbTests`

**Interfaces — Produces:**
- `Photo.thumb = ImageField(upload_to=None 대신 이름을 직접 정해 저장, blank=True, max_length=200)`, `Photo.thumb_size = PositiveIntegerField(default=0, editable=False)`, `Photo.thumb_url` property (thumb 있으면 `thumb.url`, 아니면 `image.url`).
- `couples.thumbs.make_thumb(fileobj) -> bytes | None`, `couples.thumbs.thumb_name(image_name: str) -> str`, `couples.thumbs.attach_thumb(photo) -> bool` (원본을 열어 만들고 `photo.thumb`·`thumb_size` 저장, 옛 thumb 지움; 실패면 False), `couples.thumbs.delete_thumb(photo)`.
- 명령 `make_photo_thumbs [--dry-run] [--limit N]`: thumb 없는 사진만 pk 순, 끝에 "만든 N장 · 못 만든 M장" 과 커플별 `used_bytes/couple 한도`, 넘은 커플은 "한도를 넘었어요" 줄.

- [ ] **Step 1: 실패하는 테스트**: 올리기(600×400 GPS JPEG) → `thumb` 이름 `…-thumb.jpg`, 긴 변 320, EXIF 없음, `thumb_size>0`; 사진 바꾸기 → 옛 thumb 지움(`default_storage.exists` False); 지우기 → 원본·thumb 둘 다 없음; 커플 마지막 사람 `leave` → thumb 없음; 깨진 바이트(이미지 검사를 통과하지 못하는 경우는 폼 오류이므로 `make_thumb(b"...")` 직접) → None, 업로드 경로에서 `attach_thumb` 실패해도 사진 저장(패치로 `make_thumb` 가 None 반환); `used_bytes` 에 thumb 포함; 명령 `--dry-run` 은 저장 안 함, 실제 실행은 thumb 채움·출력에 "만든 1장"; 앨범 화면 격자 `img src` 가 thumb 주소.
- [ ] **Step 2–4.** 앨범 격자·표지·장소 화면 사진 칸은 `thumb_url`. 사진 화면·고치기 미리 보기는 원본 그대로.
- [ ] **Step 5: 커밋** — `feat: 사진 작은 사진(320px) 만들기`

### Task 2: 지도 데이터

**Files:** Modify `couples/views.py`, `couples/urls.py`; Test `PhotoMapDataTests`

**Interfaces:**
- Consumes: Task 1 `Photo.thumb`/`thumb_url`.
- Produces: `GET tastes/photos/data/` `photo_map_data` → `{"photos": [{"id", "lat", "lng", "thumb": str|null, "url": photo_detail, "date": "YYYY-MM-DD"}]}` (`date` = `taken_on` 또는 `created_at` 의 지역 날짜, 정렬 `date` 내림차순·pk, 500개). `GET tastes/places/<pk>/photos/data/` `place_photo_strip` → `{"photos": [{"id","thumb","url","date"}], "total": N, "more_url": taste_detail 주소}` (date 오름차순, 60개). 로그인, 내 커플만.

- [ ] **Step 1: 실패하는 테스트**: 장소 없는 위치 사진 → 나옴; 위치 있는 장소에 묶인 사진 → 안 나옴; 위치 없는 장소에 손으로 묶인 사진 → 나옴; 위치 없는 사진 → 안 나옴; 다른 커플 → 안 나옴; thumb 없는 사진 `thumb` null; 501장 → 500개(최근 찍은 것 먼저); 장소 줄: 순서 오래된 날 먼저, 61장 → 60개·`total` 61; 다른 커플 장소 404; 로그인 필요.
- [ ] **Step 2–4. Step 5: 커밋** — `feat: 사진 핀·장소 사진 줄 데이터`

### Task 3: 지도 화면

**Files:** Modify `static/js/map.js` (recordMap), `templates/couples/taste.html` (칩·data 주소), `static/css/app.css`; Test (템플릿) `PhotoPinScreenTests`

**Interfaces:**
- Consumes: Task 2 주소. 기록 블록에 `data-photo-url`, `data-strip-url-base`(예: `/tastes/places/0/photos/data/` 의 0 을 바꿔 씀) 또는 장소 데이터에 strip 주소를 함께 넣는다(빌더 판단, 장소 데이터 `strip` 키 추가 권장).
- 칩 `<label class="overlay-chip pin-only"><input type="checkbox" data-photo-overlay checked> 사진도 보기</label>`, localStorage `nos.photoOverlay`(없으면 켬).
- 사진 핀: kind `photo`, 34px 동그라미 `background-image: url(thumb)`, thumb 없으면 카메라 아이콘(`#i-album` 재사용 가능). 장소·가고 싶은 곳과 같은 묶음.
- 사진 핀 누름 → 그 사진에서 50m 안(하버사인) 사진들 → 카드 줄. 장소 핀 누름 → 장소 카드 + `strip` 주소로 받아 줄. 줄: 가로 스크롤, 64px, 날이 바뀌는 곳 `<span class="strip-day">11월 8일</span>`, 60장 넘으면 끝에 "모두 보기 ›".

- [ ] **Step 1: 실패하는 테스트**: 기록 탭 HTML 에 `data-photo-overlay`, `data-photo-url="/tastes/photos/data/"`; 장소 데이터 각 항목에 `strip` 주소.
- [ ] **Step 2–4.**
- [ ] **Step 5: 브라우저 확인** (개발 데이터: 장소 근처 사진 2장·장소 없는 사진 3장(두 곳)·HEIC 흉내(thumb 없음) 1장; 카카오·Leaflet(해외) 모두, 칩 끄기·기억, 사진 핀 누르기 → 날짜 나눔 줄, 장소 핀 → 줄, 375px·라이트/다크, 콘솔 오류 없음) **후 커밋** — `feat: 기록 지도에서 사진 둘러보기`

### Task 4: 문서

- [ ] README(작은 사진, `make_photo_thumbs`, 사진 핀), MEMO(체크, 확인 숫자 54, 배포 뒤 `ENV_FILE=.env.neon python web/manage.py make_photo_thumbs` 한 번, 다음: 1년 리캡), 로컬 CLAUDE.md. 커밋 `docs: 사진 핀 설명`.
