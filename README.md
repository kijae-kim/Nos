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

### 처음 배포할 때

1. **Neon**: 프로젝트를 만들고 연결 문자열 두 가지를 복사합니다.
   - 풀링 주소 (호스트에 `-pooler` 가 붙음): 앱이 씁니다. Vercel 의 `DATABASE_URL` 에 넣습니다.
   - 직접 연결 주소: 자기 컴퓨터에서 `migrate` 를 돌릴 때 씁니다.
2. **DB 표 만들기**: 자기 컴퓨터에서 직접 연결 주소로 실행합니다.

   ```bash
   DATABASE_URL="<Neon 직접 연결 주소>" DJANGO_SECRET_KEY="<긴 임의 문자열>" DJANGO_DEBUG=0 python web/manage.py migrate
   ```

3. **Cloudflare R2**: 버킷을 만들고 API 토큰을 발급합니다. 버킷은 공개하지 않습니다. `MEDIA_REGION` 은 `auto` 입니다.
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
