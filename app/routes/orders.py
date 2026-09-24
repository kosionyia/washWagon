from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.dependencies import get_current_user, require_role
from app.models.orders import Order
from app.models.pickups import Pickup
from app.models.user import Role, User
from app.schemas.order import (
    AssignCourier,
    CreateOrder,
    OrderOut,
    StatusHistoryOut,
    UpdateOrderStatus,
)
from app.services.orders import (
    assign_courier,
    can_view_order,
    create_order,
    get_order_history,
    get_order_with_booking,
    update_order_status,
)
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
    if current_user.role == Role.OPS_MANAGER:
        statement = select(Order)
    elif current_user.role == Role.CUSTOMER:
        statement = select(Order).where(
            Order.customer_id == current_user.id
        )
    else:
        statement = (
            select(Order)
            .join(Pickup)
            .where(Pickup.courier_id == current_user.id)
        )

    statement = statement.options(
        selectinload(Order.items),           # type: ignore[arg-type]
        selectinload(Order.pickup),              # type: ignore[arg-type]
    )
    return session.exec(statement).all()


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
    order = get_order_with_booking(session, order_id)

    if order is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    if order.pickup is None or not can_view_order(
        order,
        order.pickup,
        current_user,
    ):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view this order",
        )

    return order


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
