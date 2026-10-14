from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.dependencies import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Incorrect email or password"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two sign-ups with the same email at the same moment: the unique
        # index in the database catches the second one.
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))

    if user is None:
        verify_password(body.password, DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS)
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS)

    return TokenResponse(access_token=create_access_token(user.id))
