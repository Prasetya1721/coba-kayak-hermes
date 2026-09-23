"""Message gateway webhooks: Telegram and WhatsApp.

Security:
  * Telegram: verifies the `X-Telegram-Bot-Api-Secret-Token` header.
  * Twilio: verifies the `X-Twilio-Signature` HMAC when an auth token is set.
  * Handlers return 200 quickly; the agent reply is sent back out-of-band via
    the sender, so platforms do not retry on slow LLM calls.
"""

# NOTE: no `from __future__ import annotations` here on purpose. The
# @limiter.limit decorator wraps these endpoints; with PEP 563 the annotations
# become strings that FastAPI cannot resolve in the wrapper's namespace, so
# `Request`/`BackgroundTasks` would be misread as required query params (422).

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import WEBHOOK_LIMIT, limiter
from app.db.session import SessionLocal
from app.services.gateways.processor import process_inbound
from app.services.gateways.sender import send_telegram, send_whatsapp

log = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# --- Telegram -----------------------------------------------------------------


async def _handle_telegram(chat_id: str, text: str) -> None:
    async with SessionLocal() as db:
        reply = await process_inbound(
            db, platform="telegram", platform_chat_id=str(chat_id), text=text
        )
    await send_telegram(str(chat_id), reply)


@router.post("/telegram")
@limiter.limit(WEBHOOK_LIMIT)
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    # Fail closed: if no secret is configured, registration is incomplete and
    # we refuse inbound traffic rather than accepting forged updates.
    if not settings.telegram_webhook_secret or (
        x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")

    try:
        update = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Payload bukan JSON valid.") from exc
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="Payload bukan JSON valid.")
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat", {})
    text = message.get("text")
    chat_id = chat.get("id")

    if chat_id and text:
        background.add_task(_handle_telegram, chat_id, text)
    return {"ok": True}


@router.get("/telegram/setup")
async def telegram_setup_info():
    """Helper describing how to register the webhook with Telegram."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN belum diisi.")
    if not settings.telegram_webhook_url:
        raise HTTPException(status_code=400, detail="TELEGRAM_WEBHOOK_URL belum diisi.")
    return {
        "hint": "Panggil URL berikut sekali untuk mendaftarkan webhook.",
        "url": (
            f"https://api.telegram.org/bot<TOKEN>/setWebhook"
            f"?url={settings.telegram_webhook_url}"
            f"&secret_token={settings.telegram_webhook_secret}"
        ),
    }


# --- WhatsApp (Twilio) --------------------------------------------------------


async def _handle_whatsapp(from_number: str, text: str) -> None:
    async with SessionLocal() as db:
        reply = await process_inbound(
            db, platform="whatsapp", platform_chat_id=from_number, text=text
        )
    await send_whatsapp(from_number, reply)


def _verify_twilio_signature(url: str, params: dict[str, str], signature: str) -> bool:
    if not settings.twilio_auth_token:
        return True  # verification disabled in dev
    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(settings.twilio_auth_token)
        return validator.validate(url, params, signature)
    except Exception as exc:  # noqa: BLE001
        log.warning("twilio_signature_error", error=str(exc))
        return False


@router.post("/whatsapp")
@limiter.limit(WEBHOOK_LIMIT)
async def whatsapp_webhook(
    request: Request,
    background: BackgroundTasks,
    x_twilio_signature: str | None = Header(default=None),
):
    if settings.whatsapp_provider == "baileys":
        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Payload bukan JSON valid.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Payload bukan JSON valid.")
        from_number = str(payload.get("from", ""))
        text = str(payload.get("text", ""))
        if from_number and text:
            background.add_task(_handle_whatsapp, from_number, text)
        return {"ok": True}

    # Twilio posts application/x-www-form-urlencoded.
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}

    # When Twilio is the configured provider, a signature is mandatory and
    # must verify — a missing or invalid signature is rejected.
    if settings.whatsapp_provider == "twilio":
        if not x_twilio_signature or not _verify_twilio_signature(
            str(request.url), params, x_twilio_signature
        ):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature.")

    from_number = params.get("From", "")
    text = params.get("Body", "")

    if from_number and text:
        background.add_task(_handle_whatsapp, from_number, text)

    # Twilio expects TwiML or an empty 200.
    return PlainTextResponse("<Response></Response>", media_type="application/xml")
