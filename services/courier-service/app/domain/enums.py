from enum import StrEnum


class CourierAvailability(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    ACCEPTED = "accepted"
    PICKED_UP = "picked_up"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


TERMINAL_ASSIGNMENT_STATUSES = {
    AssignmentStatus.DELIVERED,
    AssignmentStatus.CANCELLED,
}

ALLOWED_ASSIGNMENT_TRANSITIONS: dict[AssignmentStatus, set[AssignmentStatus]] = {
    AssignmentStatus.ASSIGNED: {AssignmentStatus.ACCEPTED, AssignmentStatus.CANCELLED},
    AssignmentStatus.ACCEPTED: {AssignmentStatus.PICKED_UP, AssignmentStatus.CANCELLED},
    AssignmentStatus.PICKED_UP: {AssignmentStatus.DELIVERED},
    AssignmentStatus.DELIVERED: set(),
    AssignmentStatus.CANCELLED: set(),
}
