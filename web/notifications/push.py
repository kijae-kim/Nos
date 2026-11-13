"""웹 푸시 보내기. 브라우저 회사의 푸시 서비스로 보내므로 무료다."""

import json
import logging

import requests
from django.conf import settings
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)

GONE = (404, 410)  # 구독이 끝났다는 뜻. 이 기기에는 다시 보내지 않는다.


def send(subscription, payload: dict) -> bool:
    """기기 하나에 보낸다. 실패해도 예외를 밖으로 내지 않고 False 를 돌려준다."""
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=86400,
            timeout=5,
        )
        return True
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in GONE:
            subscription.delete()
        else:
            logger.warning("푸시 보내기 실패 (상태 %s)", status)
        return False
    except requests.exceptions.RequestException:
        logger.warning("푸시 보내기 실패 (네트워크)")
        return False


def send_to_user(user, payload: dict) -> int:
    """그 사람의 모든 기기로 보내고 성공한 개수를 돌려준다."""
    return sum(send(sub, payload) for sub in list(user.push_subscriptions.all()))
