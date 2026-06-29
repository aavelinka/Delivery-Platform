def test_register_login_me_refresh_and_logout(client):
    register_response = client.post(
        "/auth/register",
        json={
            "email": "customer@example.com",
            "password": "strong-password",
            "full_name": "Customer One",
        },
    )
    assert register_response.status_code == 201
    tokens = register_response.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["user"]["email"] == "customer@example.com"

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "customer@example.com"

    login_response = client.post(
        "/auth/login",
        json={"email": "customer@example.com", "password": "strong-password"},
    )
    assert login_response.status_code == 200

    refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["refresh_token"] != tokens["refresh_token"]

    reused_refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused_refresh_response.status_code == 401

    logout_response = client.post(
        "/auth/logout",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert logout_response.status_code == 204


def test_duplicate_registration_is_rejected(client):
    payload = {
        "email": "customer@example.com",
        "password": "strong-password",
        "full_name": "Customer One",
    }
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_invalid_login_is_rejected(client):
    response = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
