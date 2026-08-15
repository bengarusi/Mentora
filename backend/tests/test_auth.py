from tests.conftest import auth_headers


def register(client, email="kid@example.com", password="secret123"):
    return client.post(
        "/auth/register",
        json={
            "full_name": "Test Kid",
            "email": email,
            "password": password,
            "age": 10,
            "grade": "5",
        },
    )


def test_register_returns_student(client):
    resp = register(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "kid@example.com"
    assert "password_hash" not in body


def test_duplicate_register_is_rejected(client):
    register(client)
    resp = register(client)
    assert resp.status_code == 400


def test_login_returns_token_and_student(client):
    register(client)
    resp = client.post(
        "/auth/login",
        data={"username": "kid@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["student"]["email"] == "kid@example.com"


def test_login_email_lookup_is_case_and_whitespace_insensitive(client):
    register(client, email="kid@example.com")

    resp = client.post(
        "/auth/login",
        data={"username": "  KID@EXAMPLE.COM  ", "password": "secret123"},
    )

    assert resp.status_code == 200
    assert resp.json()["student"]["email"] == "kid@example.com"


def test_register_rejects_normalized_duplicate_email(client):
    register(client, email="kid@example.com")

    resp = register(client, email="KID@EXAMPLE.COM")

    assert resp.status_code == 400


def test_login_with_wrong_password_fails(client):
    register(client)
    resp = client.post(
        "/auth/login",
        data={"username": "kid@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/sessions/").status_code == 401
    assert (
        client.get(
            "/sessions/", headers={"Authorization": "Bearer not-a-token"}
        ).status_code
        == 401
    )


def test_protected_route_with_valid_token(client):
    headers = auth_headers(client)
    assert client.get("/sessions/", headers=headers).status_code == 200


def test_student_cannot_read_another_students_session(client):
    headers_a = auth_headers(client, email="a@example.com")
    created = client.post(
        "/sessions/",
        json={
            "subject": "math",
            "topic": "Addition",
            "subtopic": "Addition basics",
            "goal_text": "Add numbers",
        },
        headers=headers_a,
    )
    assert created.status_code == 200
    session_id = created.json()["id"]

    headers_b = auth_headers(client, email="b@example.com")
    resp = client.get(f"/sessions/{session_id}", headers=headers_b)
    assert resp.status_code == 404
