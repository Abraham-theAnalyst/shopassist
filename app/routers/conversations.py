from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, get_user_conversation
from app.models import Conversation, Message, User
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.schemas.message import MessageResponse

# Every route in this router requires a logged-in user
router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    # The body is optional: a plain POST with no body creates an untitled conversation
    body: ConversationCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = Conversation(user_id=current_user.id, title=body.title if body else None)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # id breaks ties when two rows have the same created_at
    return db.scalars(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
    ).all()


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conversation: Conversation = Depends(get_user_conversation),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at, Message.id)
    ).all()
