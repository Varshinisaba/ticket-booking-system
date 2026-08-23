import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.core.ws_manager import manager
from app.database import get_db
from app.models import Show, ShowSeat, CategoryPrice, User
from app.schemas import SeatMapOut, ShowSeatOut, CategoryPriceOut

router = APIRouter(prefix="/shows", tags=["shows"])


@router.get("/{show_id}/seatmap", response_model=SeatMapOut)
def get_seat_map(
    show_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full seat map with live status. Frontend renders this once on load, then
    patches individual seats from the WebSocket 'seat:update' messages below
    instead of re-fetching -- keeps the grid in sync without polling.
    """
    show = db.get(Show, show_id)
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    show_seats = (
        db.query(ShowSeat)
        .options(joinedload(ShowSeat.seat))
        .filter(ShowSeat.show_id == show_id)
        .all()
    )
    prices = db.query(CategoryPrice).filter(CategoryPrice.show_id == show_id).all()

    return SeatMapOut(
        show_id=show_id,
        prices=[CategoryPriceOut.model_validate(p) for p in prices],
        seats=[
            ShowSeatOut(
                show_seat_id=ss.id,
                seat_id=ss.seat_id,
                row=ss.seat.row,
                number=ss.seat.number,
                category=ss.seat.category,
                status=ss.status.value,
            )
            for ss in show_seats
        ],
    )


@router.websocket("/{show_id}/ws")
async def seat_map_ws(websocket: WebSocket, show_id: str):
    """
    Client connects here after loading the seat map via the GET above.
    No inbound messages are expected -- this is a push-only channel; the
    server broadcasts seat:update events whenever a hold/release/booking
    changes a seat's status (wired up in Feature 4/5/6).
    """
    await manager.connect(show_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep the connection open; ignore client pings
    except WebSocketDisconnect:
        manager.disconnect(show_id, websocket)
