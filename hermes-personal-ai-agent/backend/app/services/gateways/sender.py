"""Outbound message sender for Telegram and WhatsApp.

Supports:
  * Telegram Bot API (plain HTTPS call — no long-polling needed).
  * Twilio WhatsApp (official API).
  * Baileys gateway (self-hosted HTTP bridge).

Every send is best-effort and returns a boolean; callers log failures.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


async def send_telegram(chat_id: str, text: str) -> bool:
    if not settings.telegram_bot_token:
        log.warning("telegram_not_configured")
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text[:4096],
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code >= 400:
                log.warning("telegram_send_failed", status=resp.status_code)
                return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram_send_error", error=str(exc))
        return False


async def send_whatsapp(to: str, text: str) -> bool:
    provider = settings.whatsapp_provider
    if provider == "twilio":
        return await _send_twilio(to, text)
    if provider == "baileys":
        return await _send_baileys(to, text)
    log.warning("whatsapp_not_configured", provider=provider)
    return False


async def _send_twilio(to: str, text: str) -> bool:
    if not (settings.twilio_account_sid and settings.twilio_auth_token):
        log.warning("twilio_not_configured")
        return False
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Messages.json"
    )
    to_number = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                url,
                data={
                    "From": settings.twilio_whatsapp_from,
                    "To": to_number,
                    "Body": text[:1600],
                },
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
            if resp.status_code >= 400:
                log.warning("twilio_send_failed", status=resp.status_code)
                return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("twilio_send_error", error=str(exc))
        return False


async def _send_baileys(to: str, text: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.baileys_gateway_url.rstrip('/')}/send",
                json={"to": to, "text": text},
                headers={"X-Gateway-Token": settings.baileys_gateway_token},
            )
            if resp.status_code >= 400:
                log.warning("baileys_send_failed", status=resp.status_code)
                return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("baileys_send_error", error=str(exc))
        return False


async def send_to_platform(platform: str, chat_id: str, text: str) -> bool:
    if platform == "telegram":
        return await send_telegram(chat_id, text)
    if platform == "whatsapp":
        return await send_whatsapp(chat_id, text)
    log.warning("unknown_platform", platform=platform)
    return False
