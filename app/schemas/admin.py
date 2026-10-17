from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    """One page of a list. total says how many there are in all."""

    items: list[Item]
    total: int
    limit: int
    offset: int


class AdminUser(BaseModel):
    # No password hash: only these fields are ever sent
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    created_at: datetime


class AdminConversation(BaseModel):
    id: int
    title: str | None
    user_id: int
    owner_email: str
    message_count: int
    created_at: datetime


class AdminDocument(BaseModel):
    id: int
    title: str
    source: str
    chunk_count: int
    # Every model used by this document's chunks (more than one part way through a re-embed)
    embedding_models: list[str]
    # True when any chunk was made by a model other than EMBEDDING_MODEL
    stale: bool
    updated_at: datetime


class AdminStats(BaseModel):
    users: int
    conversations: int
    messages: int
    documents: int
    chunks: int
