import threading
from collections import deque
from django_bulk_triggers.handler import trigger_vars


_trigger_context = threading.local()


def get_trigger_queue():
    if not hasattr(_trigger_context, "queue"):
        _trigger_context.queue = deque()
    return _trigger_context.queue


def set_bypass_triggers(bypass_triggers):
    """Set the current bypass_triggers state for the current thread."""
    _trigger_context.bypass_triggers = bypass_triggers


def get_bypass_triggers():
    """Get the current bypass_triggers state for the current thread."""
    return getattr(_trigger_context, 'bypass_triggers', False)


# Thread-local storage for passing per-object field values from bulk_update -> update
def set_bulk_update_value_map(value_map):
    """Store a mapping of {pk: {field_name: value}} for the current thread.

    This allows the internal update() call (triggered by Django's bulk_update)
    to populate in-memory instances with the concrete values that will be
    written to the database, instead of Django expression objects like Case/Cast.
    """
    _trigger_context.bulk_update_value_map = value_map


def get_bulk_update_value_map():
    """Retrieve the mapping {pk: {field_name: value}} for the current thread, if any."""
    return getattr(_trigger_context, 'bulk_update_value_map', None)


class TriggerContext:
    def __init__(self, model, bypass_triggers=False):
        self.model = model
        self.bypass_triggers = bypass_triggers
        # Set the thread-local bypass state when creating a context
        set_bypass_triggers(bypass_triggers)

    @property
    def is_executing(self):
        """
        Check if we're currently in a trigger execution context.
        Similar to Salesforce's Trigger.isExecuting.
        Use this to prevent infinite recursion in triggers.
        """
        return hasattr(trigger_vars, 'event') and trigger_vars.event is not None

    @property
    def current_event(self):
        """
        Get the current trigger event being executed.
        """
        return getattr(trigger_vars, 'event', None)

    @property
    def execution_depth(self):
        """
        Get the current execution depth to detect deep recursion.
        """
        return getattr(trigger_vars, 'depth', 0)
