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
