import pytest


def test_register_succeeds(register):
    response = register("Alice@Example.com", "correct-horse")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert set(body) == {"id", "email", "role", "created_at"}


def test_register_duplicate_email_returns_400(register):
    assert register("alice@example.com").status_code == 201

    response = register("ALICE@example.com")  # same email, different case

    assert response.status_code == 400


def test_register_short_password_returns_422(register):
    response = register("alice@example.com", "pw7Qz")

    assert response.status_code == 422
    assert "pw7Qz" not in response.text  # the password isn't echoed back


def test_login_succeeds(client, register):
    register("alice@example.com", "correct-horse")

    response = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "correct-horse"}
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_wrong_password_and_unknown_email_return_same_401(client, register):
    register("alice@example.com", "correct-horse")

    wrong_password = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "wrong-password"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/auth/me"),
        ("POST", "/conversations"),
        ("GET", "/conversations"),
        ("GET", "/conversations/1/messages"),
        ("POST", "/conversations/1/messages"),
    ],
)
def test_protected_endpoint_without_token_returns_401(client, method, path):
    response = client.request(method, path, json={"content": "hello"})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_protected_endpoint_with_invalid_token_returns_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_me_returns_current_user_without_password_hash(client, auth_headers):
    headers = auth_headers("alice@example.com", "correct-horse")

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert set(body) == {"id", "email", "role", "created_at"}
    assert "argon2" not in response.text
