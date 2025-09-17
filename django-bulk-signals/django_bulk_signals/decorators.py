"""
Simple decorators for bulk operation triggers.

These decorators have ZERO dependencies on services, executors, or configuration.
They only register signal handlers using Django's native @receiver decorator.
"""

from functools import wraps
from typing import Callable, Optional

from django.dispatch import receiver

from django_bulk_signals.conditions import TriggerCondition
from django_bulk_signals.core import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)


def bulk_trigger(
    signal,
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """
    Decorator for registering bulk operation triggers.

    This decorator has ZERO dependencies on services or configuration.
    It only registers signal handlers and stores condition metadata.
    """

    def decorator(func: Callable) -> Callable:
        # Store condition metadata on function
        func._trigger_condition = condition

        @receiver(signal, sender=sender, dispatch_uid=dispatch_uid)
        @wraps(func)
        def wrapper(sender, instances=None, originals=None, **kwargs):
            # Apply condition filtering if present
            if condition and instances:
                filtered_instances = []
                filtered_originals = []

                for instance, original in zip(
                    instances, originals or [None] * len(instances)
                ):
                    if condition.check(instance, original):
                        filtered_instances.append(instance)
                        filtered_originals.append(original)

                if filtered_instances:
                    return func(
                        sender,
                        instances=filtered_instances,
                        originals=filtered_originals,
                        **kwargs,
                    )
            else:
                return func(sender, instances=instances, originals=originals, **kwargs)

        return wrapper

    return decorator


# Convenience decorators
def before_create(
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """Decorator for BEFORE_CREATE triggers."""
    return bulk_trigger(bulk_pre_create, sender, condition, dispatch_uid)


def after_create(
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """Decorator for AFTER_CREATE triggers."""
    return bulk_trigger(bulk_post_create, sender, condition, dispatch_uid)


def before_update(
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """Decorator for BEFORE_UPDATE triggers."""
    return bulk_trigger(bulk_pre_update, sender, condition, dispatch_uid)


def after_update(
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """Decorator for AFTER_UPDATE triggers."""
    return bulk_trigger(bulk_post_update, sender, condition, dispatch_uid)


def before_delete(
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """Decorator for BEFORE_DELETE triggers."""
    return bulk_trigger(bulk_pre_delete, sender, condition, dispatch_uid)


def after_delete(
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """Decorator for AFTER_DELETE triggers."""
    return bulk_trigger(bulk_post_delete, sender, condition, dispatch_uid)
