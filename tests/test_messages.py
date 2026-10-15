from sqlalchemy import select

from app.models import Message


def saved_messages(db, conversation_id):
    return db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).all()


def test_send_message_saves_both_messages_and_returns_reply(client, db, auth_headers, fake_ai):
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]
    fake_ai.reply = "Orders usually ship within 2 business days."

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "When will my order ship?"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "assistant"
    assert response.json()["content"] == "Orders usually ship within 2 business days."

    messages = saved_messages(db, conversation_id)
    assert [(m.role, m.content) for m in messages] == [
        ("user", "When will my order ship?"),
        ("assistant", "Orders usually ship within 2 business days."),
    ]

    # The AI got the system prompt and the user's message
    assert len(fake_ai.calls) == 1
    assert "customer support agent" in fake_ai.calls[0]["system_prompt"]
    assert fake_ai.calls[0]["history"] == [{"role": "user", "content": "When will my order ship?"}]


def test_messages_are_listed_oldest_first(client, auth_headers):
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]
    client.post(f"/conversations/{conversation_id}/messages", json={"content": "first"}, headers=headers)
    client.post(f"/conversations/{conversation_id}/messages", json={"content": "second"}, headers=headers)

    response = client.get(f"/conversations/{conversation_id}/messages", headers=headers)

    assert [m["content"] for m in response.json()] == [
        "first", "This is a fake AI reply.", "second", "This is a fake AI reply.",
    ]


def test_only_last_20_messages_are_sent_to_ai(client, db, auth_headers, fake_ai):
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]
    for i in range(15):  # 15 exchanges = 30 saved messages
        client.post(f"/conversations/{conversation_id}/messages", json={"content": f"q{i}"}, headers=headers)

    client.post(f"/conversations/{conversation_id}/messages", json={"content": "latest"}, headers=headers)

    history = fake_ai.calls[-1]["history"]
    assert len(history) == 20
    assert history[-1] == {"role": "user", "content": "latest"}


def test_ai_failure_returns_502_and_saves_no_assistant_message(client, db, auth_headers, fake_ai):
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]
    fake_ai.fail = True

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Hello?"},
        headers=headers,
    )

    assert response.status_code == 502
    assert response.json()["detail"]
    messages = saved_messages(db, conversation_id)
    assert [m.role for m in messages] == ["user"]


def test_message_over_2000_characters_returns_422(client, db, auth_headers, fake_ai):
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "x" * 2001},
        headers=headers,
    )

    assert response.status_code == 422
    assert saved_messages(db, conversation_id) == []
    assert fake_ai.calls == []


def test_message_of_exactly_2000_characters_is_accepted(client, auth_headers):
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "x" * 2000},
        headers=headers,
    )

    assert response.status_code == 201


def test_cannot_send_message_to_another_users_conversation(client, db, auth_headers, fake_ai):
    alice = auth_headers("alice@example.com")
    bob = auth_headers("bob@example.com")
    conversation_id = client.post("/conversations", headers=alice).json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages", json={"content": "hi"}, headers=bob
    )

    assert response.status_code == 404
    assert saved_messages(db, conversation_id) == []
    assert fake_ai.calls == []
