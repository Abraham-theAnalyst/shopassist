from collections.abc import Generator

import jwt
import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import Conversation, User
from app.models.user import ROLE_ADMIN

logger = logging.getLogger(__name__)

# Reads "Authorization: Bearer <token>" and adds the Authorize button to /docs.
# auto_error=False lets us send our own 401 instead of FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    # One session per request, closed afterwards even if the request fails
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    # Every failure gets the same response, so callers can't tell
    # a forged token from an expired one or a deleted user.
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_admin(request: Request, current_user: User = Depends(get_current_user)) -> User:
    """The current user, but only if they are an admin.

    The role is read from the database on every request (not from the
    token), so promoting or demoting someone takes effect immediately.
    """
    if current_user.role != ROLE_ADMIN:
        # 403, not 401: they are logged in, just not allowed. No
        # WWW-Authenticate header, since logging in again won't help.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    # Who did what, never request bodies or customer data
    logger.info("Admin request: user_id=%s %s %s", current_user.id, request.method, request.url.path)
    return current_user


def get_user_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Return the conversation in the URL, but only if the current user owns it.

    A conversation that doesn't exist and one that belongs to someone else
    get the same 404, so users can't discover other users' conversation ids.
    """
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation
