import inspect
from functools import wraps

from django.core.exceptions import FieldDoesNotExist
from django_bulk_hooks.enums import DEFAULT_PRIORITY
from django_bulk_hooks.registry import register_hook
from django_bulk_hooks.engine import safe_get_related_object


def hook(event, *, model, condition=None, priority=DEFAULT_PRIORITY):
    """
    Decorator to annotate a method with multiple hooks hook registrations.
    If no priority is provided, uses Priority.NORMAL (50).
    """

    def decorator(fn):
        if not hasattr(fn, "hooks_hooks"):
            fn.hooks_hooks = []
        fn.hooks_hooks.append((model, event, condition, priority))
        return fn

    return decorator


def select_related(*related_fields):
    """
    Decorator that marks a hook method to preload related fields.
    
    This decorator works in conjunction with the hook system to ensure that
    related fields are bulk-loaded before the hook logic runs, preventing
    queries in loops.

    - Works with instance methods (resolves `self`)
    - Avoids replacing model instances
    - Populates Django's relation cache to avoid extra queries
    - Provides bulk loading for performance optimization
    """

    def decorator(func):
        # Store the related fields on the function for later access
        func._select_related_fields = related_fields
        return func

    return decorator


def bulk_hook(model_cls, event, when=None, priority=None):
    """
    Decorator to register a bulk hook for a model.
    
    Args:
        model_cls: The model class to hook into
        event: The event to hook into (e.g., BEFORE_UPDATE, AFTER_UPDATE)
        when: Optional condition for when the hook should run
        priority: Optional priority for hook execution order
    """
    def decorator(func):
        # Create a simple handler class for the function
        class FunctionHandler:
            def __init__(self):
                self.func = func
            
            def handle(self, new_instances, original_instances):
                return self.func(new_instances, original_instances)
        
        # Register the hook using the registry
        register_hook(
            model=model_cls,
            event=event,
            handler_cls=FunctionHandler,
            method_name='handle',
            condition=when,
            priority=priority or DEFAULT_PRIORITY,
        )
        return func
    return decorator
