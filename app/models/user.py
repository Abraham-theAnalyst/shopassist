from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation

ROLE_CUSTOMER = "customer"
ROLE_ADMIN = "admin"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('customer', 'admin')", name="role_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    # Everyone starts as a customer; admins are made with python -m app.cli.users
    role: Mapped[str] = mapped_column(String(20), default=ROLE_CUSTOMER, server_default=ROLE_CUSTOMER)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
