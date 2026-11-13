import hashlib

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    """{% static %} 주소 뒤에 파일 내용 해시를 붙인다. 예: /static/css/app.css?v=a1b2c3d4e5f6

    파일이 바뀌면 주소가 바뀌므로 폰은 새 파일을 받고, 같은 주소는 오래 저장해 두고 쓴다
    (vercel.json 이 ?v= 붙은 요청만 1년 캐시). 파일을 못 찾으면 버전 없이 예전처럼 내보낸다.
    """

    _versions = {}

    @classmethod
    def clear_versions(cls):
        cls._versions.clear()

    def url(self, name):
        url = super().url(name)
        version = self.version(name)
        return f"{url}?v={version}" if version else url

    def version(self, name):
        # 개발 중에는 파일을 고칠 때마다 바로 보이도록 매번 계산한다
        if settings.DEBUG or name not in self._versions:
            self._versions[name] = self._hash(name)
        return self._versions[name]

    def _hash(self, name):
        # 배포 빌드는 collectstatic 없이 static/ 을 바로 쓰기도 하고(WHITENOISE_USE_FINDERS),
        # 모은 파일(STATIC_ROOT)만 있기도 하니 둘 다 찾아본다.
        path = finders.find(name)
        if not path and self.exists(name):
            path = self.path(name)
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read(), usedforsecurity=False).hexdigest()[:12]
        except OSError:
            return None
