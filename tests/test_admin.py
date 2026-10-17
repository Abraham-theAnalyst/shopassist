import pytest
from sqlalchemy import update

from app.models import User
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER
from tests.conftest import vector

LIST_PATHS = [
    "/admin/users",
    "/admin/conversations",
    "/admin/conversations/{cid}/messages",
    "/admin/knowledge/documents",
]
ALL_PATHS = LIST_PATHS + ["/admin/stats"]


def set_role(db, email, role):
    db.execute(update(User).where(User.email == email).values(role=role))
    db.commit()


@pytest.fixture
def customer(auth_headers):
    return auth_headers("customer@example.com")


@pytest.fixture
def admin(auth_headers, db):
    headers = auth_headers("admin@example.com")
    set_role(db, "admin@example.com", ROLE_ADMIN)
    return headers


@pytest.fixture
def conversation_id(client, customer):
    cid = client.post("/conversations", json={"title": "Order question"}, headers=customer).json()["id"]
    client.post(f"/conversations/{cid}/messages", json={"content": "Where is my order?"}, headers=customer)
    return cid


@pytest.mark.parametrize("path", ALL_PATHS)
def test_no_token_gets_401(client, path):
    response = client.get(path.format(cid=1))

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ALL_PATHS)
def test_customer_gets_403(client, customer, path):
    response = client.get(path.format(cid=1), headers=customer)

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required"}
    assert "WWW-Authenticate" not in response.headers  # logging in again won't help


@pytest.mark.parametrize("path", ALL_PATHS)
def test_admin_gets_200(client, admin, conversation_id, path):
    assert client.get(path.format(cid=conversation_id), headers=admin).status_code == 200


def test_register_ignores_a_role_in_the_request(client, db):
    response = client.post(
        "/auth/register", json={"email": "sneaky@example.com", "password": "long-enough", "role": "admin"}
    )

    assert response.status_code == 201
    assert response.json()["role"] == ROLE_CUSTOMER
    assert db.query(User).filter_by(email="sneaky@example.com").one().role == ROLE_CUSTOMER


def test_me_returns_the_role(client, admin):
    assert client.get("/auth/me", headers=admin).json()["role"] == ROLE_ADMIN


def test_promote_and_demote_take_effect_without_a_new_token(client, db, customer):
    assert client.get("/admin/stats", headers=customer).status_code == 403

    set_role(db, "customer@example.com", ROLE_ADMIN)
    assert client.get("/admin/stats", headers=customer).status_code == 200  # same token

    set_role(db, "customer@example.com", ROLE_CUSTOMER)
    assert client.get("/admin/stats", headers=customer).status_code == 403  # same token


@pytest.mark.parametrize("path", LIST_PATHS)
@pytest.mark.parametrize("query", ["limit=101", "limit=0", "offset=-1"])
def test_out_of_range_pagination_is_rejected(client, admin, conversation_id, path, query):
    response = client.get(f"{path.format(cid=conversation_id)}?{query}", headers=admin)

    assert response.status_code == 422


def test_lists_return_total_limit_and_offset(client, admin, auth_headers):
    for i in range(3):
        auth_headers(f"user{i}@example.com")

    page = client.get("/admin/users?limit=2&offset=1", headers=admin).json()

    assert page["total"] == 4  # the admin plus three users
    assert (page["limit"], page["offset"]) == (2, 1)
    assert len(page["items"]) == 2


def test_limit_defaults_to_20(client, admin):
    page = client.get("/admin/users", headers=admin).json()

    assert (page["limit"], page["offset"]) == (20, 0)


def test_admin_responses_never_include_password_hashes(client, admin, conversation_id):
    for path in ALL_PATHS:
        body = client.get(path.format(cid=conversation_id), headers=admin).text
        assert "hashed_password" not in body
        assert "argon2" not in body


def test_users_list_has_only_safe_fields(client, admin):
    user = client.get("/admin/users", headers=admin).json()["items"][0]

    assert set(user) == {"id", "email", "role", "created_at"}


def test_conversations_show_owner_and_message_count(client, admin, conversation_id):
    [conversation] = client.get("/admin/conversations", headers=admin).json()["items"]

    assert conversation["id"] == conversation_id
    assert conversation["owner_email"] == "customer@example.com"
    assert conversation["message_count"] == 2  # the question and the reply


def test_conversations_filter_by_user_id(client, admin, conversation_id):
    owner_id = client.get("/admin/conversations", headers=admin).json()["items"][0]["user_id"]

    mine = client.get(f"/admin/conversations?user_id={owner_id}", headers=admin).json()
    nobody = client.get("/admin/conversations?user_id=999999", headers=admin)

    assert mine["total"] == 1
    assert nobody.status_code == 200
    assert nobody.json()["items"] == []  # a filter, not a lookup


def test_admin_can_read_any_conversation_oldest_first(client, admin, conversation_id):
    messages = client.get(f"/admin/conversations/{conversation_id}/messages", headers=admin).json()["items"]

    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_missing_conversation_is_404(client, admin):
    response = client.get("/admin/conversations/999999/messages", headers=admin)

    assert response.status_code == 404


def test_knowledge_documents_flag_stale_embeddings(client, admin, add_document):
    add_document("current.md", [("Current > A", vector(d0=1.0))])
    add_document("old.md", [("Old > A", vector(d0=1.0))], model="some-old-model")

    docs = {d["source"]: d for d in client.get("/admin/knowledge/documents", headers=admin).json()["items"]}

    assert docs["current.md"]["stale"] is False
    assert docs["old.md"]["stale"] is True
    assert docs["old.md"]["embedding_models"] == ["some-old-model"]
    assert docs["old.md"]["chunk_count"] == 1


def test_stats_count_everything(client, admin, conversation_id, add_document):
    add_document("faq.md", [("FAQ > A", vector(d0=1.0)), ("FAQ > B", vector(d1=1.0))])

    stats = client.get("/admin/stats", headers=admin).json()

    assert stats == {"users": 2, "conversations": 1, "messages": 2, "documents": 1, "chunks": 2}


def test_admin_requests_are_logged_without_content(client, admin, caplog):
    caplog.set_level("INFO", logger="app.dependencies")

    client.get("/admin/stats", headers=admin)

    [line] = [r.getMessage() for r in caplog.records if "Admin request" in r.getMessage()]
    assert line.endswith("GET /admin/stats")
    assert "user_id=" in line
