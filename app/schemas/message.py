from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


class MessageCreate(BaseModel):
    # Surrounding spaces are removed first, so "   " counts as empty
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime
