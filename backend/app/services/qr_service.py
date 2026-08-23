import base64
import io

import qrcode


def generate_qr_png_bytes(booking_id: str) -> bytes:
    """QR encodes the booking reference (its UUID) -- venue staff/scanner apps
    look up the booking server-side by this id, nothing sensitive is embedded."""
    img = qrcode.make(booking_id)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_qr_data_url(booking_id: str) -> str:
    png_bytes = generate_qr_png_bytes(booking_id)
    b64 = base64.b64encode(png_bytes).decode()
    return f"data:image/png;base64,{b64}"
