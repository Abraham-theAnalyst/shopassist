def test_create_and_list_conversations(client, auth_headers):
    headers = auth_headers()

    first = client.post("/conversations", json={"title": "First"}, headers=headers)
    second = client.post("/conversations", headers=headers)  # no body: untitled

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["title"] is None

    listed = client.get("/conversations", headers=headers).json()
    assert [c["id"] for c in listed] == [second.json()["id"], first.json()["id"]]  # newest first


def test_users_only_see_their_own_conversations(client, auth_headers):
    alice = auth_headers("alice@example.com")
    bob = auth_headers("bob@example.com")
    client.post("/conversations", json={"title": "Alice's"}, headers=alice)

    response = client.get("/conversations", headers=bob)

    assert response.status_code == 200
    assert response.json() == []


def test_user_cannot_read_another_users_conversation(client, auth_headers):
    alice = auth_headers("alice@example.com")
    bob = auth_headers("bob@example.com")
    conversation_id = client.post("/conversations", headers=alice).json()["id"]

    response = client.get(f"/conversations/{conversation_id}/messages", headers=bob)

    assert response.status_code == 404


def test_other_users_conversation_and_missing_conversation_look_the_same(client, auth_headers):
    alice = auth_headers("alice@example.com")
    bob = auth_headers("bob@example.com")
    conversation_id = client.post("/conversations", headers=alice).json()["id"]

    someone_elses = client.get(f"/conversations/{conversation_id}/messages", headers=bob)
    missing = client.get("/conversations/999999/messages", headers=bob)

    assert someone_elses.status_code == missing.status_code == 404
    assert someone_elses.json() == missing.json()
