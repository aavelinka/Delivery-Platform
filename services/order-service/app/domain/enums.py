from enum import StrEnum


class OrderStatus(StrEnum):
    CREATED = "created"
    WAITING_FOR_COURIER = "waiting_for_courier"
    COURIER_ASSIGNED = "courier_assigned"
    IN_DELIVERY = "in_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


TERMINAL_ORDER_STATUSES = {
    OrderStatus.DELIVERED,
    OrderStatus.CANCELLED,
}

ALLOWED_STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {
        OrderStatus.WAITING_FOR_COURIER,
        OrderStatus.COURIER_ASSIGNED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.WAITING_FOR_COURIER: {
        OrderStatus.COURIER_ASSIGNED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.COURIER_ASSIGNED: {
        OrderStatus.WAITING_FOR_COURIER,
        OrderStatus.IN_DELIVERY,
        OrderStatus.CANCELLED,
    },
    OrderStatus.IN_DELIVERY: {
        OrderStatus.DELIVERED,
    },
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}
