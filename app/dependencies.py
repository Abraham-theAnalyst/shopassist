from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    # One session per request, closed afterwards even if the request fails
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
