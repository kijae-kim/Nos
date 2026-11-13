import tempfile
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from config.storage import VersionedStaticFilesStorage


class StaticVersionTests(SimpleTestCase):
    """정적 파일 주소 뒤에 내용 해시(?v=)를 붙여, 배포 뒤 폰이 예전 파일을 쓰지 않게 한다."""

    def setUp(self):
        VersionedStaticFilesStorage.clear_versions()

    def render(self, name):
        return Template("{% load static %}{% static name %}").render(Context({"name": name}))

    def test_static_url_has_version(self):
        url = self.render("css/app.css")
        self.assertRegex(url, r"^/static/css/app\.css\?v=[0-9a-f]{12}$")

    def test_missing_file_has_no_version(self):
        self.assertEqual(self.render("css/none.css"), "/static/css/none.css")

    def test_version_changes_with_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.css"
            path.write_text("a{}")
            with override_settings(STATICFILES_DIRS=[tmp], DEBUG=True):
                first = self.render("x.css")
                path.write_text("b{}")
                second = self.render("x.css")
        self.assertNotEqual(first, second)
