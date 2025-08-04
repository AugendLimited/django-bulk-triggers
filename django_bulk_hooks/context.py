import threading
from collections import deque
from django_bulk_hooks.handler import hook_vars


_hook_context = threading.local()


def get_hook_queue():
    if not hasattr(_hook_context, "queue"):
        _hook_context.queue = deque()
    return _hook_context.queue


class HookContext:
    def __init__(self, model):
        self.model = model

    @property
    def is_executing(self):
        """
        Check if we're currently in a hook execution context.
        Similar to Salesforce's Trigger.isExecuting.
        Use this to prevent infinite recursion in hooks.
        """
        return hasattr(hook_vars, 'event') and hook_vars.event is not None

    @property
    def current_event(self):
        """
        Get the current hook event being executed.
        """
        return getattr(hook_vars, 'event', None)

    @property
    def execution_depth(self):
        """
        Get the current execution depth to detect deep recursion.
        """
        return getattr(hook_vars, 'depth', 0)
