# User Service

Stores user profile data and delivery addresses.

## Endpoints

- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `GET /users/{user_id}/addresses`
- `POST /users/{user_id}/addresses`
- `PATCH /users/{user_id}/addresses/{address_id}`
- `DELETE /users/{user_id}/addresses/{address_id}`

All endpoints require an auth-service JWT. Admins can access any user, regular users can access only their own profile and addresses.
