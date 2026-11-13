import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# 평소에는 개발용 .env 를 읽는다. ENV_FILE 로 다른 파일을 고를 수 있다.
# 예: 운영 DB(Neon)에 migrate 할 때 ENV_FILE=.env.neon python web/manage.py migrate
load_dotenv(BASE_DIR.parent / os.getenv("ENV_FILE", ".env"))

# 앱 이름. 포르투갈어로 '우리'이자 '매듭'. 한글 표기는 '노스'.
APP_NAME = "NÓS"

DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY 환경 변수가 필요합니다. (.env.example 참고)")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.kakao",
    "allauth.socialaccount.providers.google",
    "accounts",
    "couples",
    "anniversaries",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # 배포에서 정적 파일(CSS, JS, 아이콘)을 Django가 직접 내준다
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "couples.middleware.CoupleRequiredMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context.app",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# DATABASE_URL 이 있으면 (배포: Neon Postgres) 그 DB를 쓰고, 없으면 개발용 SQLite 를 쓴다.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}
if DATABASES["default"]["ENGINE"].endswith("postgresql"):
    # Neon 의 풀링 주소(-pooler)는 요청마다 다른 연결로 갈 수 있어서 서버 쪽 커서를 쓰지 않는다
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# Vercel 에서는 디스크에 쓴 것이 남지 않는다. DB나 사진 저장소 설정이 빠진 채로 뜨면
# 데이터가 조용히 사라지므로, 시작할 때 바로 알린다.
ON_VERCEL = bool(os.getenv("VERCEL"))
if ON_VERCEL and not os.getenv("DATABASE_URL"):
    raise ImproperlyConfigured("배포에는 DATABASE_URL 환경 변수가 필요합니다. (README 배포 참고)")
if ON_VERCEL and not os.getenv("MEDIA_BUCKET_NAME"):
    raise ImproperlyConfigured("배포에는 MEDIA_BUCKET_NAME 등 사진 저장소 환경 변수가 필요합니다. (README 배포 참고)")

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# --- 로그인 (django-allauth) ---
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/accounts/login/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_SESSION_REMEMBER = True
# 카카오는 이메일을 주지 않을 수 있으므로 소셜 가입에는 이메일을 요구하지 않는다.
SOCIALACCOUNT_EMAIL_REQUIRED = False
SOCIALACCOUNT_AUTO_SIGNUP = True
# 소셜 가입 때 카카오 닉네임·구글 이름을 앱 닉네임으로 넣는다
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
# 같은 이메일이라도 소셜 계정을 기존 계정에 저절로 붙이지 않는다.
# 이메일 인증을 하지 않으므로, 남이 내 이메일로 먼저 가입해 둔 계정에 내가 들어가게 되는 일을 막기 위해서다.
# 여러 로그인 방법은 로그인한 뒤 '우리 > 연결된 계정'에서 직접 이어 붙인다.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False

# 키가 설정된 소셜 로그인만 활성화된다.
SOCIALACCOUNT_PROVIDERS = {}
if os.getenv("KAKAO_CLIENT_ID"):
    SOCIALACCOUNT_PROVIDERS["kakao"] = {
        "APPS": [{"client_id": os.environ["KAKAO_CLIENT_ID"], "secret": os.getenv("KAKAO_CLIENT_SECRET", ""), "key": ""}],
    }
if os.getenv("GOOGLE_CLIENT_ID"):
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APPS": [{"client_id": os.environ["GOOGLE_CLIENT_ID"], "secret": os.getenv("GOOGLE_CLIENT_SECRET", ""), "key": ""}],
        "SCOPE": ["profile", "email"],
    }

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# 배포 빌드에서 collectstatic 을 따로 돌리지 않아도 되도록, 앱 폴더의 정적 파일을 바로 찾아 쓴다.
WHITENOISE_USE_FINDERS = True

# 업로드한 사진. 개발 중에는 runserver 가 직접 내준다 (config/urls.py).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# 업로드 저장소. 배포에서는 S3 호환 저장소(AWS S3, Cloudflare R2 등)를 쓴다.
# MEDIA_BUCKET_NAME 이 없으면 개발용으로 web/media/ 에 저장한다.
# 사진은 비공개로 두고, 주소는 1시간짜리 서명 주소로만 보여 준다.
if os.getenv("MEDIA_BUCKET_NAME"):
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    AWS_STORAGE_BUCKET_NAME = os.getenv("MEDIA_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = os.getenv("MEDIA_ENDPOINT_URL") or None
    AWS_S3_REGION_NAME = os.getenv("MEDIA_REGION") or None
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "private, max-age=3600"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 배포(DEBUG 끔)에서만 쓰는 보안 설정. Vercel 이 HTTPS를 맡아 주므로 프록시 헤더를 믿는다.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 3600  # 처음에는 짧게 (1시간). 익숙해지면 늘린다.
