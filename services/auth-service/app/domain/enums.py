from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    COURIER = "courier"
    ADMIN = "admin"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
