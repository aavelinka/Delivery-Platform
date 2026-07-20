import uuid


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_profile_and_addresses_flow(client, auth_headers):
    user_id = str(uuid.uuid4())
    headers = auth_headers(user_id)

    profile_response = client.get(f"/users/{user_id}", headers=headers)
    assert profile_response.status_code == 200
    assert profile_response.json()["user_id"] == user_id

    update_response = client.patch(
        f"/users/{user_id}",
        json={"full_name": "Customer One", "phone": "+375291112233"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["full_name"] == "Customer One"

    address_response = client.post(
        f"/users/{user_id}/addresses",
        json={
            "label": "Home",
            "city": "Minsk",
            "street": "Main street",
            "building": "12",
            "is_default": True,
        },
        headers=headers,
    )
    assert address_response.status_code == 201
    address = address_response.json()
    assert address["is_default"] is True

    list_response = client.get(f"/users/{user_id}/addresses", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    delete_response = client.delete(
        f"/users/{user_id}/addresses/{address['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204


def test_user_cannot_read_another_user(client, auth_headers):
    owner_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())

    response = client.get(f"/users/{other_id}", headers=auth_headers(owner_id))
    assert response.status_code == 403
