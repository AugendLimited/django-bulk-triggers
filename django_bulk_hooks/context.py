import threading
from collections import deque

_hook_context = threading.local()


def get_hook_queue():
    if not hasattr(_hook_context, "queue"):
        _hook_context.queue = deque()
    return _hook_context.queue


def is_in_bulk_operation():
    """Check if we're currently in a bulk operation to prevent recursion."""
    return getattr(_hook_context, "in_bulk_operation", False)


def set_bulk_operation_flag(value):
    """Set the bulk operation flag to prevent recursion."""
    _hook_context.in_bulk_operation = value


class HookContext:
    def __init__(self, model_cls, metadata=None):
        self.model_cls = model_cls
        self.metadata = metadata or {}
