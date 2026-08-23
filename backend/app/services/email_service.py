from io import BytesIO

from fastapi_mail import FastMail, MessageSchema, MessageType, ConnectionConfig
from starlette.datastructures import UploadFile, Headers

from app.core.config import settings
from app.services.qr_service import generate_qr_png_bytes

_mail_config = None


def _get_mail_config() -> ConnectionConfig:
    """
    Built lazily on first send, not at import time. Constructing this eagerly
    at module load would crash the entire app on startup if MAIL_* env vars
    aren't set yet (fastapi-mail validates MAIL_FROM as a real email address) --
    that would take down auth, venues, everything, over an unrelated feature.
    """
    global _mail_config
    if _mail_config is None:
        _mail_config = ConnectionConfig(
            MAIL_USERNAME=settings.mail_username,
            MAIL_PASSWORD=settings.mail_password,
            MAIL_FROM=settings.mail_from,
            MAIL_PORT=settings.mail_port,
            MAIL_SERVER=settings.mail_server,
            MAIL_FROM_NAME=settings.mail_from_name,
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
        )
    return _mail_config


async def send_booking_confirmation_email(
    to_email: str, booking_id: str, event_title: str, show_time: str, seat_labels: list[str]
):
    qr_bytes = generate_qr_png_bytes(booking_id)
    qr_file = UploadFile(
        filename="ticket-qr.png",
        file=BytesIO(qr_bytes),
        headers=Headers({"content-type": "image/png"}),
    )
    html = f"""
    <h2>Booking confirmed</h2>
    <p><strong>{event_title}</strong><br/>{show_time}</p>
    <p>Seats: {', '.join(seat_labels)}</p>
    <p>Booking reference: {booking_id}</p>
    <p>Your QR ticket is attached.</p>
    """
    message = MessageSchema(
        subject=f"Booking confirmed: {event_title}",
        recipients=[to_email],
        body=html,
        subtype=MessageType.html,
        attachments=[qr_file],
    )
    fm = FastMail(_get_mail_config())
    await fm.send_message(message)


async def send_waitlist_offer_email(to_email: str, claim_url: str, expires_at: str):
    """Used by Feature 6 -- kept here alongside the other outbound email so all
    mail-sending logic lives in one place."""
    html = f"""
    <h2>A seat is available for you</h2>
    <p>You have until <strong>{expires_at}</strong> to claim it.</p>
    <p><a href="{claim_url}">Claim your seat</a></p>
    <p>If you don't claim in time, it will be offered to the next person on the waitlist.</p>
    """
    message = MessageSchema(
        subject="A seat opened up — claim it now",
        recipients=[to_email],
        body=html,
        subtype=MessageType.html,
    )
    fm = FastMail(_get_mail_config())
    await fm.send_message(message)
