from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, get_user_conversation
from app.models import Conversation, Message, User
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.schemas.message import MessageCreate, MessageResponse
from app.services.ai import AIServiceError, generate_reply
from app.services.prompts import build_system_prompt

# How many recent messages are sent to the AI as context
HISTORY_LIMIT = 20

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


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    body: MessageCreate,
    conversation: Conversation = Depends(get_user_conversation),
    db: Session = Depends(get_db),
):
    db.add(Message(conversation_id=conversation.id, role="user", content=body.content))
    db.commit()

    # The newest HISTORY_LIMIT messages (including the one just saved),
    # put back into oldest-first order for the AI
    recent = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(recent)]

    try:
        reply = generate_reply(build_system_prompt(), history)
    except AIServiceError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The assistant is unavailable right now. Please try again in a moment.",
        )

    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=reply)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return assistant_message
