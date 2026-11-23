
import hmac
import os

from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth_models import (
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.database import get_db
from app.identity_models import User, UserSession
from app.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_token,
    password_hash_needs_update,
    verify_password,
    verify_token,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])

SESSION_DURATION = timedelta(days=7)
SESSION_MAX_AGE_SECONDS = int(SESSION_DURATION.total_seconds())

CSRF_COOKIE_NAME = "opspilot_csrf"


def _cookie_secure() -> bool:
    configured_value = os.getenv(
        "SESSION_COOKIE_SECURE",
        "false",
    ).strip().lower()

    if configured_value not in {"true", "false"}:
        raise RuntimeError(
            "SESSION_COOKIE_SECURE must be either true or false"
        )

    return configured_value == "true"


def _session_cookie_name() -> str:
    if _cookie_secure():
        return "__Host-opspilot_session"

    return "opspilot_session"


def _set_auth_cookies(
    response: Response,
    session_token: str,
    csrf_token: str,
) -> None:
    secure = _cookie_secure()

    response.set_cookie(
        key=_session_cookie_name(),
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )

    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _delete_auth_cookies(response: Response) -> None:
    secure = _cookie_secure()

    response.delete_cookie(
        key=_session_cookie_name(),
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )

    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )


def _create_session(
    db: Session,
    user: User,
    request: Request,
) -> tuple[str, str]:
    session_token = generate_session_token()
    csrf_token = generate_csrf_token()

    session_record = UserSession(
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=datetime.now(timezone.utc) + SESSION_DURATION,
        user_agent=request.headers.get("user-agent", "")[:500],
    )

    db.add(session_record)

    return session_token, csrf_token


def _get_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()

    existing_user = db.scalar(
        select(User).where(User.email == email)
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )

    try:
        db.add(user)
        db.flush()

        session_token, csrf_token = _create_session(
            db,
            user,
            request,
        )

        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create account",
        )

    _set_auth_cookies(
        response,
        session_token,
        csrf_token,
    )

    return _get_user_response(user)


@router.post(
    "/login",
    response_model=UserResponse,
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if (
        user is None
        or not user.is_active
        or not verify_password(
            payload.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    try:
        if password_hash_needs_update(user.password_hash):
            user.password_hash = hash_password(payload.password)

        session_token, csrf_token = _create_session(
            db,
            user,
            request,
        )

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create login session",
        )

    _set_auth_cookies(
        response,
        session_token,
        csrf_token,
    )

    return _get_user_response(user)


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession:
    session_token = request.cookies.get(
        _session_cookie_name()
    )

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session_record = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(session_token)
        )
    )

    now = datetime.now(timezone.utc)

    if session_record is None or session_record.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    expires_at = session_record.expires_at

    # SQLite may return naive datetimes in tests.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user = db.get(User, session_record.user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
        csrf_header = request.headers.get("X-CSRF-Token")

        if (
            not csrf_cookie
            or not csrf_header
            or not hmac.compare_digest(
                csrf_cookie,
                csrf_header,
            )
            or not verify_token(
                csrf_cookie,
                session_record.csrf_token_hash,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed",
            )

    request.state.current_user = user

    return session_record


def get_current_user(
    request: Request,
    session_record: UserSession = Depends(get_current_session),
) -> User:
    return request.state.current_user


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return _get_user_response(current_user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout(
    response: Response,
    session_record: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    session_record.revoked_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to end session",
        )

    _delete_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT

    return response
