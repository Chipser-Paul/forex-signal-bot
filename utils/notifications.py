from __future__ import annotations

import os
import urllib.parse
import urllib.request
from pathlib import Path

from app_security.environment import load_project_environment


load_project_environment()


def send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10):  # nosec B310
            return True
    except Exception:
        return False


def _fcm_tokens() -> list[str]:
    token_single = os.getenv("FCM_DEVICE_TOKEN", "").strip()
    tokens_bulk = os.getenv("FCM_DEVICE_TOKENS", "").strip()

    values: list[str] = []
    if token_single:
        values.append(token_single)
    if tokens_bulk:
        values.extend([tok.strip() for tok in tokens_bulk.split(",") if tok.strip()])

    # Deduplicate while keeping order
    seen: set[str] = set()
    unique: list[str] = []
    for token in values:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def _init_firebase() -> tuple[bool, object | None]:
    service_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "secrets/firebase-service-account.json").strip()
    if not service_path:
        service_path = "secrets/firebase-service-account.json"

    cert_file = Path(service_path)
    if not cert_file.exists():
        return False, None

    try:
        import firebase_admin  # pyright: ignore[reportMissingImports]
        from firebase_admin import credentials, messaging  # pyright: ignore[reportMissingImports]

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(cert_file))
            firebase_admin.initialize_app(cred)
        return True, messaging
    except Exception:
        return False, None


def send_push(message: str, title: str = "Forex Signal Bot") -> bool:
    ok, messaging = _init_firebase()
    tokens = _fcm_tokens()
    if not ok or messaging is None or not tokens:
        return False

    body = str(message)
    sent = False
    for token in tokens:
        try:
            payload = messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body[:500]),
                data={
                    "source": "forex_signal_bot",
                },
            )
            messaging.send(payload)
            sent = True
        except Exception:
            continue
    return sent


def send_alert(message: str, title: str = "Forex Signal Bot") -> bool:
    """
    Multi-channel alert:
    - Telegram (if configured)
    - Firebase Cloud Messaging (if configured)
    """
    ok_tg = send_telegram(message)
    ok_push = send_push(message, title=title)
    return ok_tg or ok_push
