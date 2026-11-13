# NÓS (노스)

커플 전용 공유 앱. NÓS는 포르투갈어로 '우리'이자 '매듭'이라는 뜻입니다. Django(메인) + FastAPI(보조 서비스, 예정) + HTML/CSS/JS, PWA.

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
2. 카카오 로그인을 켜고 위의 Redirect URI 를 등록합니다.
3. 동의 항목에서 **닉네임**을 필수로 둡니다. 이메일은 비즈 앱 심사가 필요해서 쓰지 않습니다. 앱은 카카오 닉네임을 앱 닉네임으로 넣습니다.

### Google ([console.cloud.google.com](https://console.cloud.google.com))

1. 프로젝트 `nos` 를 만들고 Google 인증 플랫폼(OAuth 동의 화면)을 **외부 · 테스트** 상태로 둡니다.
2. **테스트 사용자**에 쓸 사람의 Google 계정을 넣습니다 (최대 100명). 등록되지 않은 계정은 로그인할 수 없습니다.
3. 클라이언트를 **웹 애플리케이션**으로 만들고 위의 Redirect URI 를 넣습니다. 범위는 `openid`, `email`, `profile` 만 씁니다.

테스트 상태로 두는 이유: 나중에 붙일 드라이브 가져오기(`drive.file`)까지 심사 없이 쓸 수 있습니다. 테스트 상태의 "7일 뒤 권한 만료"는 로그인과 그때그때 골라 가져오기에는 영향이 없습니다.

### 알아 둘 점

- **로그인 방법 여러 개**: 같은 사람이 이메일과 카카오로 따로 가입하면 계정이 둘이 됩니다. 이메일이 같아도 저절로 합치지 않습니다(남이 내 이메일로 먼저 가입해 둔 계정에 들어가게 되는 일을 막기 위해서). 로그인한 뒤 **우리 › 연결된 계정**에서 다른 방법을 이어 붙입니다.
- **카카오톡 안에서 연 링크**: Google 이 앱 안의 브라우저에서 로그인을 막아서, 그때는 Google 버튼을 숨기고 다른 브라우저로 열라는 안내를 보입니다. 카카오 로그인은 그대로 됩니다.
- **애플 로그인**: Apple Developer Program 가입이 필요해서 TestFlight 단계에서 붙입니다.

## 구조

```
web/
  config/     설정, URL
  accounts/   사용자 모델 (닉네임, 커플 연결)
  couples/    커플 공간, 초대 코드, 홈·우리 화면, 캘린더·취향·앨범
  anniversaries/  기념일 (직접 등록 + 100일·주년 자동 계산)
  templates/  화면
  static/     CSS, JS, 아이콘
tools/
  make_icons.py  앱 아이콘 만들기 (로고를 바꾸면 다시 실행)
design/       화면·로고 시안 (앱과 따로 여는 HTML)
```

## 개발 단계

1. [x] 프로젝트 세팅, 로그인, 초대 코드로 커플 연결
2. [x] 기념일·D-day (알림 발송은 8단계)
3. [x] 캘린더 (일정, @카테고리·#태그)
   - [ ] ICS 구독 내보내기
4. [x] 취향 피드
   - [ ] 링크 미리보기
5. [x] 사진 앨범
   - [ ] 여러 장 한 번에 올리기
6. [ ] 웹 배포
7. [ ] 구글 캘린더·드라이브 연동
8. [ ] Capacitor로 iOS 앱, 애플 로그인·푸시, TestFlight
