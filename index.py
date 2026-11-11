"""Vercel 진입점. Vercel 이 이 파일의 app 을 WSGI 앱으로 실행한다.

Django 프로젝트는 web/ 폴더에 있으므로, web/ 을 import 경로에 넣고 설정 모듈을 가리킨다.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from config.wsgi import application as app  # noqa: E402,F401
