from enum import IntEnum


class Priority(IntEnum):
    """
    Named priorities for django-bulk-triggers triggers.
    Replaces module-level constants with a clean IntEnum.
    """

    HIGHEST = 0  # runs first
    HIGH = 25  # runs early
    NORMAL = 50  # default ordering
    LOW = 75  # runs late
    LOWEST = 100  # runs last


DEFAULT_PRIORITY = Priority.NORMAL
