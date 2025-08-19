import threading
from collections import deque
from django_bulk_hooks.handler import hook_vars


_hook_context = threading.local()


def get_hook_queue():
    if not hasattr(_hook_context, "queue"):
        _hook_context.queue = deque()
    return _hook_context.queue


def set_bypass_hooks(bypass_hooks):
    """Set the current bypass_hooks state for the current thread."""
    _hook_context.bypass_hooks = bypass_hooks


def get_bypass_hooks():
    """Get the current bypass_hooks state for the current thread."""
    return getattr(_hook_context, 'bypass_hooks', False)


class HookContext:
    def __init__(self, model, bypass_hooks=False):
        self.model = model
        self.bypass_hooks = bypass_hooks
        # Set the thread-local bypass state when creating a context
        set_bypass_hooks(bypass_hooks)

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
