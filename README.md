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

1. Neon에서 프로젝트를 만들고 연결 문자열(`postgres://...?sslmode=require`)을 복사합니다.
2. 아래 명령으로 DB 표를 만듭니다. 자기 컴퓨터에서 한 번만 실행하면 됩니다.

   ```bash
   DATABASE_URL="<Neon 연결 문자열>" DJANGO_SECRET_KEY="<긴 임의 문자열>" DJANGO_DEBUG=0 python web/manage.py migrate
   ```

3. Cloudflare에서 R2 버킷을 만들고 API 토큰을 발급합니다. 버킷은 공개하지 않습니다.
4. Vercel에서 이 저장소를 가져옵니다. 설정은 기본값으로 두고(진입점 `index.py`, 의존성 `requirements.txt`), 환경 변수를 넣습니다.
   - `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`
   - `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` (배포 도메인)
   - `DATABASE_URL`, `MEDIA_*`, `AWS_*` (위 표)
   - 카카오·구글 로그인을 쓰면 해당 키와 redirect URI도 넣습니다.
5. 배포 도메인으로 접속해 로그인이 되는지 확인합니다.

> 주의: Vercel Hobby는 개인·비상업 용도로만 쓸 수 있습니다. 배포 기록이 10GB를 넘으면 오래된 기록이 지워질 수 있습니다.

## 업로드 사진 저장소

사진과 취향 이미지는 개발 중에는 `web/media/` 에 저장됩니다. 배포에서는 S3 호환 저장소(AWS S3, Cloudflare R2 등)를 쓰세요.

- `.env` 에 `MEDIA_BUCKET_NAME`, `MEDIA_ENDPOINT_URL`, `MEDIA_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` 를 넣으면 자동으로 켜집니다 (`.env.example` 참고).
- 사진 주소는 1시간짜리 서명 주소로만 보입니다. 저장소 버킷은 공개하지 마세요.
- 파일 이름은 무작위로 만들고 커플별 폴더에 나눠 담습니다. 한 장은 10MB 이하여야 합니다.

## 소셜 로그인 설정

`.env` 에 키를 넣으면 로그인 화면에 버튼이 나타납니다. 발급 방법과 Redirect URI는 `.env.example` 의 주석을 참고하세요.

## 구조

```
web/
  config/     설정, URL
  accounts/   사용자 모델 (닉네임, 커플 연결)
  couples/    커플 공간, 초대 코드, 홈·우리 화면
  anniversaries/  기념일 (직접 등록 + 100일·주년 자동 계산)
  templates/  화면
  static/     CSS, JS, 아이콘
```

## 개발 단계

1. [x] 프로젝트 세팅, 로그인, 초대 코드로 커플 연결
2. [x] 기념일·D-day (알림 발송은 8단계)
3. [ ] 캘린더와 ICS 구독 내보내기
4. [ ] 취향 피드 (FastAPI 링크 미리보기)
5. [ ] 사진 앨범
6. [ ] 웹 배포
7. [ ] 구글 캘린더·드라이브 연동
8. [ ] Capacitor로 iOS 앱, 애플 로그인·푸시, TestFlight
