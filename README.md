# NÓS (노스)

커플 전용 공유 앱. NÓS는 포르투갈어로 '우리'이자 '매듭'이라는 뜻입니다. Django + HTML/CSS/JS, PWA. (FastAPI 는 나중에 확장할 때 더합니다.)

## 개발 환경 준비 (Mac / Windows 공통)

Python 3.12 이상이 필요합니다.

**Windows (PowerShell)**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r web/requirements.txt
Copy-Item .env.example .env
python web/manage.py migrate
python web/manage.py runserver
```

**Mac (터미널)**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r web/requirements.txt
cp .env.example .env
python web/manage.py migrate
python web/manage.py runserver
```

브라우저에서 http://localhost:8000 을 엽니다.

- `.env` 와 `db.sqlite3` 는 git에 올라가지 않으므로 기기마다 따로 만듭니다.
- 테스트 실행: `python web/manage.py test` (`web` 폴더 기준이면 `python manage.py test`)

## 배포 (Vercel + Neon + Cloudflare R2, 무료 한도)

| 역할 | 서비스 | 설정할 값 |
|---|---|---|
| 앱 | Vercel Hobby (GitHub 저장소 연결) | 아래 환경 변수 |
| DB | Neon Free | `DATABASE_URL` |
| 사진 | Cloudflare R2 (무료) | `MEDIA_BUCKET_NAME`, `MEDIA_ENDPOINT_URL`, `MEDIA_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |

### 지역: 셋 다 싱가포르 근처로

앱과 DB가 멀면 화면 하나를 열 때마다 DB 왕복 시간이 쌓여 느려집니다. 세 서비스를 모두 싱가포르에 둡니다. (Neon에는 서울·도쿄 지역이 없습니다.)

| 서비스 | 지역 |
|---|---|
| Vercel 함수 | `sin1` (싱가포르). `web/vercel.json` 에 적어 두었습니다. |
| Neon | AWS Asia Pacific (Singapore), `aws-ap-southeast-1`. 프로젝트를 만들 때만 고를 수 있습니다. |
| Cloudflare R2 | 버킷을 만들 때 위치 힌트를 Asia-Pacific(APAC)으로. |

### 처음 배포할 때

1. **Neon**: 지역을 싱가포르로 골라 프로젝트를 만들고 연결 문자열 두 가지를 복사합니다.
   - 풀링 주소 (호스트에 `-pooler` 가 붙음): 앱이 씁니다. Vercel 의 `DATABASE_URL` 에 넣습니다.
   - 직접 연결 주소: 자기 컴퓨터에서 `migrate` 를 돌릴 때 씁니다.
2. **DB 표 만들기**: 저장소 맨 위에 `.env.neon` 파일을 만들고 직접 연결 주소를 `DATABASE_URL` 에 넣은 뒤 실행합니다. 이 파일은 git 에 올라가지 않고, `ENV_FILE` 을 줄 때만 읽히므로 평소 개발은 SQLite 그대로입니다.

   ```bash
   ENV_FILE=.env.neon python web/manage.py migrate
   ```

   `.env.neon` 예시: `DATABASE_URL=<직접 연결 주소>`, `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY=<긴 임의 문자열>`

3. **Cloudflare R2**: 버킷을 만들고(위치 힌트 APAC) API 토큰을 발급합니다. 버킷은 공개하지 않습니다. `MEDIA_REGION` 은 `auto` 입니다.
4. **Vercel**: 이 저장소를 가져오고 **Root Directory 를 `web`** 으로 지정합니다. Vercel 이 `manage.py` 를 찾아 Django 로 인식하고, 정적 파일도 빌드할 때 알아서 모읍니다.
5. **환경 변수**: Vercel 프로젝트 설정에서 **Production** 환경에 넣습니다. 빌드할 때도 읽으므로 배포 전에 넣어야 합니다.
   - `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`
   - `DJANGO_ALLOWED_HOSTS` (예: `nos-xxxx.vercel.app`), `DJANGO_CSRF_TRUSTED_ORIGINS` (예: `https://nos-xxxx.vercel.app`)
   - `DATABASE_URL` (풀링 주소), `MEDIA_*`, `AWS_*`
   - 카카오·구글 로그인을 쓰면 해당 키를 넣고, 각 개발자 콘솔에 배포 도메인의 redirect URI 를 등록합니다.
6. 배포 도메인으로 접속해 회원가입과 로그인, 사진 올리기가 되는지 확인합니다.

`DATABASE_URL` 이나 `MEDIA_BUCKET_NAME` 이 빠진 채로 Vercel 에 올리면 앱이 시작하지 않고 오류로 알려 줍니다. 데이터가 조용히 사라지는 일을 막기 위해서입니다.

### 운영하면서

- **모델을 바꿨을 때**: 배포 전에 2번의 `migrate` 명령을 다시 실행합니다. 처음 한 번으로 끝나지 않습니다.
- **관리자 계정**: 2번과 같은 환경 변수를 붙여 `python web/manage.py createsuperuser` 를 실행합니다.
- **더미 데이터**: `seed_demo` 는 개발용입니다. 배포 DB에는 실행하지 마세요.
- **미리보기 배포**: 도메인이 달라 `DJANGO_ALLOWED_HOSTS` 에 걸립니다. 환경 변수를 Production 에만 넣어 두면 미리보기가 운영 DB를 건드리지 않습니다.
- **백업**: Neon 무료 플랜은 복구할 수 있는 기간이 짧고, R2 에서 지운 사진은 되살릴 수 없습니다. 중요한 데이터는 따로 내려받아 두세요.

> 주의: Vercel Hobby 는 개인·비상업 용도로만 쓸 수 있습니다. 무료 한도는 바뀔 수 있으니 각 서비스의 요금 페이지를 확인하세요.

### 나중에 확장할 때

코드를 바꿀 필요는 없습니다. Vercel Pro(상업 용도), Neon 유료 플랜, R2 종량제로 각각 따로 올리면 됩니다. 그때 `SECURE_HSTS_SECONDS` 를 늘리고 오류 추적 도구를 붙이는 것을 권합니다.

## 업로드 사진 저장소

사진과 취향 이미지는 개발 중에는 `web/media/` 에 저장됩니다. 배포에서는 S3 호환 저장소(AWS S3, Cloudflare R2 등)를 쓰세요.

- `.env` 에 `MEDIA_BUCKET_NAME`, `MEDIA_ENDPOINT_URL`, `MEDIA_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` 를 넣으면 자동으로 켜집니다 (`.env.example` 참고).
- 사진 주소는 1시간짜리 서명 주소로만 보입니다. 저장소 버킷은 공개하지 마세요.
- 파일 이름은 무작위로 만들고 커플별 폴더에 나눠 담습니다. 한 장은 4MB 이하여야 합니다.
- Vercel 은 요청 하나를 4.5MB까지만 받습니다. 그래서 1.5MB가 넘는 사진은 브라우저가 올리기 전에 긴 변 2560px의 JPEG로 줄여서 보냅니다. 이때 위치 같은 촬영 정보도 빠집니다.
- 여러 장을 고르면 한 장씩 따로 보냅니다 (한 번에 30장까지). 찍은 날을 비워 두면 줄이기 전에 사진의 촬영 정보(EXIF)에서 읽어 넣습니다. 스크립트가 꺼진 브라우저에서는 고른 사진 중 한 장만 올라갑니다.

## 무료 한도 지키기

| 서비스 | 무료 한도를 넘으면 | 앱이 하는 일 |
|---|---|---|
| Neon (Free) | 요금 없이 멈춤. 저장 1GB 초과 시 쓰기 실패, 계산 100 CU-시간/월 초과 시 다음 달까지 정지 | 별도 장치 없음. 콘솔 설정 권장 (아래) |
| Cloudflare R2 | **등록한 카드로 청구.** 지출 상한 설정 없음 | 아래 한도에서 올리기를 멈춘다 |

앱의 사진 저장소 한도 (`couples/quota.py`). 환경 변수로 바꿀 수 있습니다.

| 환경 변수 | 기본값 | 뜻 |
|---|---|---|
| `MEDIA_QUOTA_TOTAL_GB` | `8` | 앱 전체 사진·이미지 합계. R2 무료 10GB 보다 여유를 둔다 (R2 는 날마다의 최고치로 계산) |
| `MEDIA_QUOTA_PER_COUPLE_GB` | `2` | 커플 하나당 |
| `MEDIA_UPLOADS_PER_DAY` | `300` | 커플 하나가 하루에 올릴 수 있는 파일 수 (R2 쓰기 횟수 보호) |

- 쓴 용량은 R2 에 묻지 않고 DB 에 적어 둔 파일 크기를 더해 계산합니다. R2 의 목록 조회도 유료 작업이기 때문입니다.
- 사진을 지우면 R2 에서도 지워져 공간이 돌아옵니다 (지우기는 R2 에서 무료).
- 목록의 사진은 화면에 보일 때만 받습니다 (`loading="lazy"`). R2 읽기 횟수와 휴대폰 데이터를 아낍니다.
- **Neon 콘솔 권장 설정**: Compute 의 Autoscaling 최대값을 `0.25` CU 로 낮추고, 5분 뒤 잠들기(scale to zero)를 그대로 둡니다. 계산 시간이 급하게 줄지 않습니다.

## 소셜 로그인 설정

키를 넣은 로그인 방법만 버튼이 나타납니다. 개발 중에는 `.env`, 배포에서는 Vercel 환경 변수(Production)에 넣고 재배포합니다.

| 변수 | 어디서 |
|---|---|
| `KAKAO_CLIENT_ID` | 카카오 앱의 **REST API 키** |
| `KAKAO_CLIENT_SECRET` | 카카오 앱 보안 설정에서 Client Secret 을 켰을 때만 |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Cloud 의 OAuth 클라이언트(웹 애플리케이션) |

Redirect URI 는 주소마다 따로 등록합니다. 끝의 `/` 까지 정확히 같아야 합니다.

- 배포: `https://nos-rho-jade.vercel.app/accounts/kakao/login/callback/`, `https://nos-rho-jade.vercel.app/accounts/google/login/callback/`
- 개발: `http://localhost:8000/accounts/kakao/login/callback/`, `http://localhost:8000/accounts/google/login/callback/`

### 카카오 ([developers.kakao.com](https://developers.kakao.com))

1. 애플리케이션을 만들고, 플랫폼의 Web 사이트 도메인에 배포 주소와 `http://localhost:8000` 을 넣습니다.
2. 카카오 로그인을 켜고 위의 Redirect URI 를 등록합니다. 새 콘솔에서는 **앱 › 플랫폼 키 › REST API 키** 안에 리다이렉트 URI 칸이 있습니다 (빠지면 KOE006 오류).
3. 동의 항목에서 **닉네임**을 필수로 둡니다. 이메일은 비즈 앱 심사가 필요해서 쓰지 않습니다. 앱은 카카오 닉네임을 앱 닉네임으로 넣습니다.

### Google ([console.cloud.google.com](https://console.cloud.google.com))

1. 프로젝트 `nos` 를 만들고 Google 인증 플랫폼(OAuth 동의 화면)을 **외부 · 테스트** 상태로 둡니다.
2. **테스트 사용자**에 쓸 사람의 Google 계정을 넣습니다 (최대 100명). 등록되지 않은 계정은 로그인할 수 없습니다.
3. 클라이언트를 **웹 애플리케이션**으로 만들고 위의 Redirect URI 를 넣습니다. 범위는 `openid`, `email`, `profile` 만 씁니다.

테스트 상태로 두는 이유: 나중에 붙일 드라이브 가져오기(`drive.file`)까지 심사 없이 쓸 수 있습니다. 테스트 상태의 "7일 뒤 권한 만료"는 로그인과 그때그때 골라 가져오기에는 영향이 없습니다.

### 드라이브에서 골라 가져오기

사진 올리기 화면의 "Google 드라이브에서 가져오기" 버튼입니다. 로그인과 같은 Google 프로젝트를 씁니다. 아래 셋이 모두 있어야 버튼이 나타납니다.

| 변수 | 어디서 |
|---|---|
| `GOOGLE_CLIENT_ID` | 로그인에 쓰는 것과 같은 OAuth 클라이언트 ID |
| `GOOGLE_PICKER_API_KEY` | API 및 서비스 → 사용자 인증 정보 → API 키 |
| `GOOGLE_PROJECT_NUMBER` | IAM 및 관리자 → 설정의 **프로젝트 번호** (프로젝트 ID 아님) |

1. **API 사용 설정**: `Google Picker API` 와 `Google Drive API` 를 켭니다.
2. **API 키 제한**: 웹사이트 제한에 `https://nos-rho-jade.vercel.app/*`, `http://localhost:8000/*`, **`https://docs.google.com/*`** 를 넣습니다 (마지막 것이 없으면 "API developer key is invalid" 오류). API 제한은 Picker API 와 Drive API 만.
3. **OAuth 클라이언트**: 승인된 JavaScript 원본에 `https://nos-rho-jade.vercel.app` 과 `http://localhost:8000` 을 넣습니다 (끝에 `/` 없이).
4. **데이터 액세스(범위)**: `.../auth/drive.file` 을 더합니다. Google 이 민감하지 않은 범위로 분류해 심사가 필요 없습니다.

동작: 사용자가 버튼을 누르면 그때 "선택한 파일만 보기" 권한을 묻고, Google 파일 선택 창에서 고른 사진을 **브라우저가 직접** 내려받아 여러 장 올리기 목록에 더합니다. 그다음은 휴대폰 사진과 똑같이 줄여서 올라갑니다 (용량·횟수 한도 포함). Google 토큰은 서버로 보내지 않습니다. API 키는 화면에 드러나는 값이라 위의 제한을 꼭 걸어 둡니다.

### 알아 둘 점

- **로그인 방법 여러 개**: 같은 사람이 이메일과 카카오로 따로 가입하면 계정이 둘이 됩니다. 이메일이 같아도 저절로 합치지 않습니다(남이 내 이메일로 먼저 가입해 둔 계정에 들어가게 되는 일을 막기 위해서). 로그인한 뒤 **우리 › 연결된 계정**에서 다른 방법을 이어 붙입니다.
- **카카오톡 안에서 연 링크**: Google 이 앱 안의 브라우저에서 로그인을 막아서, 그때는 Google 버튼을 숨기고 다른 브라우저로 열라는 안내를 보입니다. 카카오 로그인은 그대로 됩니다.
- **애플 로그인**: Apple Developer Program 가입이 필요해서 TestFlight 단계에서 붙입니다.

## 기념일 알림 설정

기념일 당일에는 항상, 하루 전·일주일 전에는 켠 사람에게만 웹 푸시 알림을 보냅니다. Vercel Cron 이 하루 한 번 `/cron/anniversaries/` 를 부릅니다 (`vercel.json`, `0 0 * * *` = UTC 00시 = 한국 오전 9시대. 무료 플랜이라 그 시간 안 아무 때나 실행됩니다).

1. **열쇠 만들기**: `python web/manage.py make_vapid_keys` → 출력된 세 줄을 메모장에 옮기고 `VAPID_SUBJECT` 를 내 이메일(`mailto:…`)로 바꿉니다. 출력은 메신저·채팅으로 보내지 않습니다. 개발용(`.env`)과 운영용은 따로 만듭니다.
2. **Cron 비밀 값**: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
3. **Vercel 환경 변수 (Production)**: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `CRON_SECRET` → 재배포. Vercel 은 Cron 을 부를 때 `Authorization: Bearer <CRON_SECRET>` 을 붙입니다.
4. **폰에서 켜기**: 우리 › 알림 › 이 기기에서 알림 받기 → 허용 → 시험 알림 보내기.

- VAPID 세 값 중 하나라도 없으면 알림 메뉴가 숨겨지고 알림 주소는 404 입니다 (개발 서버는 그대로 뜹니다).
- 아이폰은 iOS 16.4 이상, **홈 화면에 추가한 앱**에서만 받을 수 있습니다.
- 열쇠를 바꾸면 이미 켠 기기는 다시 켜야 합니다.
- 같은 날 Cron 이 두 번 불려도 보낸 기록(`PushLog`, 60일 보관)으로 다시 보내지 않습니다. 푸시 발송은 무료입니다.

## 추억 · 기록 지도

하단 탭 "추억" 은 **순간**(영화·음악·영상·책, 글마다 태그 하나)과 **기록**(함께 간 장소)으로 나뉩니다. 장소는 분류가 "장소" 인 추억 글에 위치·주소를 더한 것입니다.

- **기록 지도**: 국내는 카카오맵, 해외는 Leaflet + OpenStreetMap. 장소 핀을 누르면 장소 카드, 카드를 누르면 장소 글. 카카오 JavaScript 키(`KAKAO_JS_KEY`)가 없거나 카카오맵을 불러오지 못하면 국내도 Leaflet 으로 그립니다.
- **장소 기록하기**: 위치는 이름 검색(기본), 지도에서 찍기, 사진에서 가져오기. 검색은 서버가 카카오 로컬 검색(로그인과 같은 REST API 키 `KAKAO_CLIENT_ID`)을 부르고, 결과가 3개보다 적으면 OpenStreetMap(Nominatim, 초당 1회·하루 캐시)을 덧붙입니다. 둘 다 무료입니다.
- **사진 연결**: 사진의 **찍은 위치**(올린 곳이 아님)에서 200m 안의 가장 가까운 장소에 저절로 붙습니다. 장소 화면의 "사진 고르기"나 사진 고치기의 "장소" 로 직접 정하면, 그 사진은 자동 연결이 다시 바꾸지 않습니다.
- **카카오맵 키**: [developers.kakao.com](https://developers.kakao.com) → 앱 › 플랫폼 키 › **JavaScript 키** 의 JavaScript SDK 도메인에 `https://nos-rho-jade.vercel.app`, `http://localhost:8000` 을 넣고, Vercel 환경 변수 `KAKAO_JS_KEY`(Production)에 넣은 뒤 재배포합니다. 로컬에서 시험하려면 `.env` 에도 넣습니다.
- **사진 위치**: 사진을 올릴 때 브라우저가 줄이기 전에 촬영 위치(EXIF GPS)를 읽어 함께 보냅니다(exifr, JPEG·HEIC). 이미 올린 원본 사진은 `ENV_FILE=.env.neon python web/manage.py fill_photo_locations [--dry-run]` 로 채웁니다(R2 GET, 목록 조회 없음). 채우면 가까운 장소에도 저절로 붙습니다.
- **색칠 지도**: 기록 탭 지도 카드 오른쪽 위의 핀/붓 버튼으로 바꿔 봅니다(국내·해외는 왼쪽 위 작은 칩). 경계만 그린 지도로 전국 시·군·구 → 서울 구 → 구의 동까지 들어가고, 위치 있는 장소·사진이 있는 지역이 저절로 칠해집니다. 지역을 눌러 `칠하기 / 지우기 / 자동으로` 를 고르면 저장됩니다(`RegionMark`). 동이 칠해지면 그 구도 칠해집니다.
- **가고 싶은 곳**: 기록 탭의 `가고 싶은 곳 · N곳` 카드로 들어갑니다. 장소를 검색·지도에서 찍어 저장하고, 두 사람이 만든 목록(여행·맛집·카페…, 목록마다 색)에 넣습니다(`WishList`, `WishPlace`). 한 곳을 여러 목록에 넣을 수 있고 핀은 첫 목록(이름순) 색입니다. `다녀왔어요` 를 누르면 그 장소로 기록 장소를 만들고(근처 사진 자동 연결·색칠 지도 반영), 가고 싶은 곳은 `다녀옴` 으로 남습니다. 두 번 눌러도 기록은 하나이고, 두 사람 모두에게 다녀옴으로 보입니다. 기록 핀 지도 아래 `가고 싶은 곳도 보기` 를 켜면 아직 안 간 곳이 빈 핀으로 겹쳐 보입니다.
- **사진 핀**: 기록 핀 지도의 `사진도 보기` 칩을 켜면(처음엔 켬), 장소에 안 묶인 위치 있는 사진이 작은 사진 핀으로 보입니다. 누르면 50m 안 사진을 찍은 날로 나눠 줄로 보여 주고, 장소 핀 카드에는 그 장소 사진 줄이 나옵니다. 작은 사진(긴 변 320px, 촬영 정보 없음)은 올릴 때 서버가 만들어 R2 원본 옆 `-thumb.jpg` 로 두고 용량 한도에 넣습니다. 이미 올린 사진은 `ENV_FILE=.env.neon python web/manage.py make_photo_thumbs [--dry-run] [--limit N]` 로 채웁니다(LIST 없음).
- **데이터 출처** (`web/static/geo/`): 한국 시·군·구 — 통계청(KOSTAT) 2018 센서스용 행정구역경계([southkorea/southkorea-maps](https://github.com/southkorea/southkorea-maps)), 서울 행정동 — 통계청(KOSTAT) 2013([southkorea/seoul-maps](https://github.com/southkorea/seoul-maps), 423개 동, 2013년 이후 바뀐 동은 옛 경계), 세계 나라 — [world-atlas](https://github.com/topojson/world-atlas) 2.0.2 `countries-50m`(ISC, 원본 Natural Earth 퍼블릭 도메인), 지도 타일·해외 검색 — © OpenStreetMap 기여자.

## 구조

```
web/
  config/     설정, URL
  accounts/   사용자 모델 (닉네임, 커플 연결)
  couples/    커플 공간, 초대 코드, 홈·우리 화면, 캘린더·추억(순간·기록)·앨범
  anniversaries/  기념일 (직접 등록 + 100일·주년 자동 계산)
  notifications/  기념일 알림 (웹 푸시)
  templates/  화면
  static/     CSS, JS, 아이콘, 지도 경계 데이터(geo/)
tools/
  make_icons.py  앱 아이콘 만들기 (로고를 바꾸면 다시 실행)
design/       화면·로고 시안 (앱과 따로 여는 HTML)
```

## 개발 단계

1. [x] 프로젝트 세팅, 로그인, 초대 코드로 커플 연결
2. [x] 기념일·D-day (알림 발송은 8단계)
3. [x] 캘린더 (일정, @카테고리·#태그)
   - [x] 캘린더 앱 구독 (ICS, 우리 › 캘린더 앱에서 보기)
   - [x] 여러 날 일정 (끝나는 날, 하루 종일만). 지난 일정은 끝나는 날 기준이고 읽기 전용(지우기만)
   - [x] 넓은 화면 큰 달력에서 일정을 끌어 다른 날로 옮기기 (지난 날로는 안 됨, 옮긴 뒤 되돌리기). 폰은 눌러서 날짜를 고친다
   - [x] 이름표 관리 (캘린더 › 이름표 관리): 만들기·이름·색·지우기, 같은 이름으로 바꾸면 합침
   - [x] 메모 (홈 카드·+ 메뉴, `memos` 앱): 폴더(처음 버킷리스트·여행계획) → 메모 목록 → 아이폰 메모장처럼 쓰는 칸 안 체크 항목. 내용은 줄 목록 JSON, 저절로 저장, 동시에 고치면 버전으로 막고 안내
   - [x] 날짜 팝업: 날짜를 누르면(폰은 꾹 눌러도) 그날 일정과 빠른 추가 칸(`calendar/day/<날>/`, `calendar-popup.js`). 메모·색·장소는 "자세히 쓰기". 폰 달력 칸에 일정 이름 두 줄 + "+N"
   - [x] 프로필 (우리 › 프로필 바꾸기): 사진 또는 이모지, 내 색. 사진은 R2 가 아니라 DB(`accounts.Avatar`)에 256px JPEG 로 두고 촬영 정보는 지운다. 나와 상대만 볼 수 있다. 일정 만든 사람은 그 사람 색 점
4. [x] 취향 피드
   - [x] 링크 미리보기 (유튜브·스포티파이 바로 재생)
5. [x] 사진 앨범 (여러 장 한 번에 올리기, 무료 한도 보호)
6. [x] 웹 배포 (Vercel·Neon·R2. 운영 DB migrate 는 MEMO 참고)
7. [ ] 구글 연동
   - [x] 드라이브에서 골라 가져오기
   - [ ] 구글 캘린더
8. [ ] Capacitor로 iOS 앱, 애플 로그인·푸시, TestFlight
