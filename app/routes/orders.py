from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.dependencies import get_current_user, require_role
from app.models.user import Role, User
from app.schemas.order import (
    AssignCourier,
    CreateOrder,
    OrderOut,
    StatusHistoryOut,
    UpdateOrderStatus,
)
from app.services.order_assignments import accept_order, assign_courier
from app.services.order_booking import create_order
from app.services.order_events import stream_order_status
from app.services.order_queries import (
    get_order_history,
    get_order_for_user,
    list_orders_for_user,
)
from app.services.order_status import update_order_status
from app.utils.database import get_session


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)


@router.post(
    "/",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_order(
    data: CreateOrder,
    session: Session = Depends(get_session),
    current_user: User = Depends(
        require_role(Role.CUSTOMER)
    ),
):
    return create_order(
        session=session,
        customer=current_user,
        data=data,
    )


@router.get(
    "/",
    response_model=list[OrderOut],
    status_code=status.HTTP_200_OK,
)
def list_orders(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return list_orders_for_user(session, current_user)


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    status_code=status.HTTP_200_OK,
)
def get_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return get_order_for_user(session, order_id, current_user)


@router.patch(
    "/{order_id}/courier",
    response_model=OrderOut,
    status_code=status.HTTP_200_OK,
)
def assign_order_courier(
    order_id: int,
    data: AssignCourier,
    session: Session = Depends(get_session),
    current_user: User = Depends(
        require_role(Role.OPS_MANAGER)
    ),
):
    return assign_courier(
        session=session,
        order_id=order_id,
        data=data,
    )


@router.post(
    "/{order_id}/accept",
    response_model=OrderOut,
    status_code=status.HTTP_200_OK,
)
def accept_pickup(
    order_id: int,
    session: Session = Depends(get_session),
    courier: User = Depends(require_role(Role.COURIER)),
):
    return accept_order(
        session=session,
        order_id=order_id,
        courier=courier,
    )


@router.get(
    "/{order_id}/stream",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
async def stream_order_updates(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    # Authorize before opening the long-lived Redis subscription.
    get_order_for_user(session, order_id, current_user)

    return StreamingResponse(
        stream_order_status(order_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch(
    "/{order_id}/status",
    response_model=OrderOut,
    status_code=status.HTTP_200_OK,
)
def change_order_status(
    order_id: int,
    data: UpdateOrderStatus,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return update_order_status(
        session=session,
        order_id=order_id,
        data=data,
        actor=current_user,
    )


@router.get(
    "/{order_id}/history",
    response_model=list[StatusHistoryOut],
    status_code=status.HTTP_200_OK,
)
def read_order_history(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return get_order_history(
        session=session,
        order_id=order_id,
        viewer=current_user,
    )
