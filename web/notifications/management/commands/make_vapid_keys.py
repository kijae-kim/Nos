from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid
from py_vapid.utils import b64urlencode


class Command(BaseCommand):
    help = "웹 푸시용 VAPID 열쇠를 새로 만들어 .env 에 붙여 넣을 줄을 출력해요. 출력은 채팅·메신저로 옮기지 마세요."

    def handle(self, *args, **options):
        vapid = Vapid()
        vapid.generate_keys()
        private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
        public = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.stdout.write("# 기념일 알림 (웹 푸시). VAPID_SUBJECT 는 내 이메일로 바꾸세요.")
        self.stdout.write(f"VAPID_PUBLIC_KEY={b64urlencode(public)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64urlencode(private)}")
        self.stdout.write("VAPID_SUBJECT=mailto:you@example.com")
