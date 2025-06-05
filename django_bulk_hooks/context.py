import threading
from collections import deque

_hook_context = threading.local()


def get_hook_queue():
    if not hasattr(_hook_context, "queue"):
        _hook_context.queue = deque()
    return _hook_context.queue


class TriggerContext:
    def __init__(self, model_cls, metadata=None):
        self.model_cls = model_cls
        self.metadata = metadata or {}
