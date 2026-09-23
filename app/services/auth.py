

from fastapi import HTTPException, status
from sqlmodel import Session

from app.models.user import Role, User
from app.repositories.users import create_user, get_user_by_email
from app.repositories.zones import get_zone_by_name
from app.schemas.user import CourierCreate, TokenResponse, UserRegister,UserLogin
from app.utils.security import create_access_token, hash_password, verify_password


def register_customer(
    session: Session,
    data: UserRegister,
) -> User:

    existing_user = get_user_by_email(
        session, data.email,
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    zone = get_zone_by_name(session, data.zone)

    if zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found",
        )

    user = User(
        name=data.name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=Role.CUSTOMER,
        zone_id=zone.id,
    )

    create_user(session, user)

    session.commit()
    session.refresh(user)

    return user


def confirm_user(
        session: Session,
    data: UserLogin,
) -> TokenResponse:
    user = get_user_by_email(session, data.email)

    if user is None or not verify_password(
        data.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User has no database identity",
        )

    token = create_access_token(
        user_id=user.id,
        role=user.role.value
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
    )

def create_courier(
    session: Session,
    data: CourierCreate,
) -> User:
    
    existing_user = get_user_by_email(
        session,
        data.email,
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    zone = get_zone_by_name(
        session,
        data.zone,
    )

    if zone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zone not found",
        )

    courier = User(
        name=data.name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=Role.COURIER,
        zone_id=zone.id
    )

    create_user(session, courier)

    session.commit()
    session.refresh(courier)

    return courier