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


def test_reply_uses_retrieved_store_information(client, auth_headers, fake_ai, add_document, monkeypatch):
    from app.services import ai
    from tests.conftest import vector

    add_document("returns.md", [("Returns > Window\n\n14 days from delivery.", vector(d0=1.0))])
    add_document("contact.md", [("Contact > Email\n\nsupport@example.test", vector(d5=1.0))])
    monkeypatch.setitem(ai._EMBEDDING_PROVIDERS, "openrouter", lambda texts, mode: [vector(d0=1.0) for _ in texts])
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages", json={"content": "Return window?"}, headers=headers
    )

    assert response.status_code == 201
    prompt = fake_ai.calls[0]["system_prompt"]
    store_information = prompt.split("<store_information>")[1].split("</store_information>")[0]
    assert "14 days from delivery." in store_information
    assert "support@example.test" in store_information  # always included


def test_search_text_includes_the_previous_customer_message(client, auth_headers, add_document, monkeypatch):
    from app.services import ai
    from tests.conftest import vector

    searched = []

    def fake_embed(texts, mode):
        searched.extend(texts)
        return [vector(d0=1.0) for _ in texts]

    monkeypatch.setitem(ai._EMBEDDING_PROVIDERS, "openrouter", fake_embed)
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]
    url = f"/conversations/{conversation_id}/messages"

    client.post(url, json={"content": "How long is delivery to Abuja?"}, headers=headers)
    client.post(url, json={"content": "And how much?"}, headers=headers)

    assert searched[-1] == "How long is delivery to Abuja?\nAnd how much?"


def test_chat_still_replies_when_embedding_fails(client, db, auth_headers, fake_ai, add_document):
    from tests.conftest import vector

    # conftest makes every embedding call fail, like an outage
    add_document("contact.md", [("Contact > Email\n\nsupport@example.test", vector(d5=1.0))])
    headers = auth_headers()
    conversation_id = client.post("/conversations", headers=headers).json()["id"]

    response = client.post(
        f"/conversations/{conversation_id}/messages", json={"content": "Hello?"}, headers=headers
    )

    assert response.status_code == 201
    assert response.json()["content"] == fake_ai.reply
    assert [m.role for m in saved_messages(db, conversation_id)] == ["user", "assistant"]
    # The support contact details still reach the AI
    assert "support@example.test" in fake_ai.calls[0]["system_prompt"]
