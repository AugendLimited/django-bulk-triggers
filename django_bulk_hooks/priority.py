from enum import IntEnum


class Priority(IntEnum):
    """
    Named priorities for django-bulk-hooks hooks.

    Lower values run earlier (higher priority).
    Hooks are sorted in ascending order.
    """

    HIGHEST = 0  # runs first
    HIGH = 25  # runs early
    NORMAL = 50  # default ordering
    LOW = 75  # runs later
    LOWEST = 100  # runs last
