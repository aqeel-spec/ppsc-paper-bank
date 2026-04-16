from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import List, Optional


def is_email_enabled() -> bool:
    return os.getenv("EMAIL_ENABLED", "0") == "1"


def get_email_recipients() -> List[str]:
    raw = os.getenv("EMAIL_RECIPIENTS", "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def send_email_message(to_email: str, subject: str, body: str) -> dict:
    smtp_host = os.getenv("EMAIL_SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587").strip() or "587")
    smtp_username = os.getenv("EMAIL_SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("EMAIL_SMTP_PASSWORD", "").strip()
    from_email = os.getenv("EMAIL_FROM", smtp_username).strip()
    use_tls = os.getenv("EMAIL_USE_TLS", "1") == "1"

    if not smtp_host or not smtp_username or not smtp_password or not from_email:
        return {
            "ok": False,
            "detail": (
                "Missing EMAIL_SMTP_HOST, EMAIL_SMTP_USERNAME, "
                "EMAIL_SMTP_PASSWORD, or EMAIL_FROM"
            ),
        }

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if use_tls:
                server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(message)

        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


def broadcast_email_message(subject: str, body: str, recipients: Optional[List[str]] = None) -> dict:
    recipients = recipients or get_email_recipients()
    if not recipients:
        return {
            "ok": False,
            "detail": "No recipients provided and none configured in EMAIL_RECIPIENTS",
        }

    results = []
    success = 0
    for recipient in recipients:
        outcome = send_email_message(recipient, subject, body)
        if outcome.get("ok"):
            success += 1
        results.append({"to": recipient, **outcome})

    return {
        "ok": success > 0,
        "success_count": success,
        "total": len(recipients),
        "results": results,
    }