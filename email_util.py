"""Send transactional email via Resend HTTPS (preferred) and/or SMTP."""

from __future__ import annotations

import json
import os
import smtplib
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from http.client import RemoteDisconnected

RESEND_MAX_ATTEMPTS = max(1, int(os.getenv("EMAIL_SEND_RETRIES", "3")))
RESEND_RETRY_BASE_SEC = max(1, int(os.getenv("EMAIL_SEND_RETRY_SEC", "15")))

DEFAULT_RESEND_FROM = "OPCG Assistant <noreply@optcgassistant.com>"


class EmailSendError(RuntimeError):
    pass


def _smtp_config() -> tuple[str, int, str, str, str]:
    host = str(os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = str(os.getenv("SMTP_USER") or "").strip()
    password = str(os.getenv("SMTP_PASS") or "").strip()
    from_email = str(os.getenv("SMTP_FROM") or user or "").strip()
    return host, port, user, password, from_email


def _resend_from() -> str:
    explicit = str(os.getenv("RESEND_FROM") or "").strip()
    if explicit:
        return explicit
    return DEFAULT_RESEND_FROM


def _skip_smtp_fallback() -> bool:
    """VPS sets SMTP_SKIP_GMAIL=1 so Resend failures do not hang on Gmail 587/465."""
    flag = str(os.getenv("SMTP_SKIP_GMAIL") or os.getenv("RESEND_NO_SMTP_FALLBACK") or "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if str(os.getenv("SMTP_FORCE") or "").strip().lower() in {"1", "true", "yes"}:
        return False
    host, port, *_ = _smtp_config()
    return "gmail.com" in host.lower() and port in {587, 465}


def _send_via_smtp(to_email: str, subject: str, body: str, *, html: str | None = None) -> None:
    host, port, user, password, from_email = _smtp_config()
    if not host:
        raise EmailSendError("SMTP_HOST unset")
    if not from_email:
        raise EmailSendError("SMTP_FROM unset")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(host, port, timeout=12) as server:
        if port != 465:
            server.starttls()
        if user:
            server.login(user, password)
        server.send_message(msg)


def _resend_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionResetError, RemoteDisconnected, urllib.error.URLError)):
        return True
    if isinstance(exc, urllib.error.HTTPError) and exc.code >= 500:
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in {104, 110, 111}:
        return True
    return False


def _send_via_resend(to_email: str, subject: str, body: str, *, html: str | None = None) -> None:
    api_key = str(os.getenv("RESEND_API_KEY") or "").strip()
    if not api_key:
        raise EmailSendError("RESEND_API_KEY unset")
    from_addr = _resend_from()
    payload: dict[str, object] = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if html:
        payload["html"] = html
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "OPCG-Assistant/1.0",
        },
        method="POST",
    )
    last_exc: BaseException | None = None
    for attempt in range(1, RESEND_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if resp.status >= 300:
                    raise EmailSendError(f"Resend HTTP {resp.status}: {raw[:500]}")
            return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            last_exc = EmailSendError(f"Resend HTTP {exc.code}: {detail}")
            if exc.code < 500 or attempt >= RESEND_MAX_ATTEMPTS:
                raise last_exc from exc
        except Exception as exc:
            last_exc = exc
            if not _resend_retryable(exc) or attempt >= RESEND_MAX_ATTEMPTS:
                if isinstance(exc, EmailSendError):
                    raise
                raise EmailSendError(f"Resend failed: {exc}") from exc
        wait = RESEND_RETRY_BASE_SEC * attempt
        print(f"[email] Resend attempt {attempt}/{RESEND_MAX_ATTEMPTS} failed ({last_exc}); retry in {wait}s")
        time.sleep(wait)
    if last_exc:
        if isinstance(last_exc, EmailSendError):
            raise last_exc
        raise EmailSendError(f"Resend failed after {RESEND_MAX_ATTEMPTS} attempts: {last_exc}") from last_exc


def send_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
    log_prefix: str = "email",
) -> str:
    """Send email. Prefer Resend HTTPS when configured; else SMTP."""
    to_email = str(to_email or "").strip()
    if not to_email:
        raise EmailSendError("missing recipient")

    resend_key = str(os.getenv("RESEND_API_KEY") or "").strip()
    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    skip_smtp = bool(resend_key) and _skip_smtp_fallback()

    if resend_key:
        try:
            _send_via_resend(to_email, subject, body, html=html)
            print(f"[{log_prefix}] sent via Resend → {to_email}")
            return "resend"
        except EmailSendError:
            if skip_smtp or not smtp_host:
                raise
            print(f"[{log_prefix}] Resend failed; trying SMTP…")

    if not smtp_host:
        print(f"[{log_prefix}] no SMTP/Resend — printing email\nTo: {to_email}\nSubject: {subject}\n\n{body}")
        if html:
            print(f"\n[HTML]\n{html[:800]}")
        return "stdout"

    try:
        _send_via_smtp(to_email, subject, body, html=html)
        print(f"[{log_prefix}] sent via SMTP → {to_email}")
        return "smtp"
    except OSError as exc:
        if resend_key:
            raise EmailSendError(f"SMTP failed ({exc}) and Resend already tried") from exc
        raise EmailSendError(
            f"SMTP failed ({exc}). DigitalOcean VPS often blocks Gmail ports 587/465; "
            "set RESEND_API_KEY in .env (HTTPS) or use SMTP on port 2525 (Brevo/SendGrid)."
        ) from exc
