"""
Calls the SAME function the booking flow uses (with the QR attachment),
directly and synchronously, so any error prints immediately instead of
disappearing into a background task.

Usage (from backend/ folder, venv active):
    python scripts/test_booking_email.py you@example.com
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.email_service import send_booking_confirmation_email


async def main(to_email: str):
    await send_booking_confirmation_email(
        to_email=to_email,
        booking_id="test-booking-id-1234",
        event_title="Test Event",
        show_time="Sun, Aug 30, 1:57 PM",
        seat_labels=["A1", "A2"],
    )
    print(f"Sent successfully to {to_email}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_booking_email.py you@example.com")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))