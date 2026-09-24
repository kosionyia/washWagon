from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.dependencies import require_role
from app.models.user import Role, User
from app.schemas.reports import CourierBoardEntry, ZoneRevenue
from app.services.reports import courier_board, revenue_by_zone
from app.utils.database import get_session


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


@router.get(
    "/revenue",
    response_model=list[ZoneRevenue],
)
def read_revenue_report(
    date_from: date | None = None,
    date_to: date | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role(Role.OPS_MANAGER)),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_from must not be after date_to",
        )
    return revenue_by_zone(session, date_from, date_to)


@router.get(
    "/courier-board",
    response_model=list[CourierBoardEntry],
)
def read_courier_board(
    board_date: date = Query(default_factory=date.today),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_role(Role.OPS_MANAGER)),
):
    return courier_board(session, board_date)
