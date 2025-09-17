"""
Decorators for bulk operation triggers.

This module provides decorators for easily registering trigger handlers
for bulk operations, similar to Salesforce trigger patterns.

The decorators are now purely for registration - business logic is handled
by the service layer.
"""

import logging
from functools import wraps
from typing import Callable, Optional

from django.dispatch import receiver

from django_bulk_signals.conditions import TriggerCondition
from django_bulk_signals.signals import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)

logger = logging.getLogger(__name__)


def bulk_trigger(
    signal,
    sender,
    condition: Optional[TriggerCondition] = None,
    dispatch_uid: Optional[str] = None,
):
    """
    Decorator for registering bulk operation triggers.

    This decorator provides a clean way to register trigger handlers
    for bulk operations, similar to Salesforce trigger patterns.

    The decorator is now purely for registration - condition filtering
    is handled by the service layer during signal execution.

    Args:
        signal: The signal to listen for (e.g., bulk_pre_update)
        sender: The model class to listen for
        condition: Optional condition to filter when the trigger fires
        dispatch_uid: Optional unique identifier for the handler

    Example:
        @bulk_trigger(bulk_pre_update, MyModel, condition=HasChanged('status'))
        def handle_status_change(sender, instances, originals, **kwargs):
            for instance, original in zip(instances, originals):
                if instance.status != original.status:
                    # Handle status change
                    pass
    """

    def decorator(func: Callable) -> Callable:
        # Store condition metadata on the function for service layer to use
        func._trigger_condition = condition

        @receiver(signal, sender=sender, dispatch_uid=dispatch_uid)
        @wraps(func)
        def wrapper(sender, **kwargs):
            # Pure handler execution - no business logic here
            return func(sender, **kwargs)

        return wrapper

    return decorator


# Convenience decorators for specific trigger types
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


# Utility decorator for processing instances with conditions
def process_instances(condition: Optional[TriggerCondition] = None):
    """
    Decorator for processing instances in trigger handlers.

    This decorator can be used to wrap trigger handler functions
    to automatically filter instances based on conditions.

    Args:
        condition: Optional condition to filter instances

    Example:
        @after_update(MyModel)
        @process_instances(HasChanged('status'))
        def handle_status_change(sender, instances, originals, **kwargs):
            # This function will only be called with instances where status changed
            for instance, original in zip(instances, originals):
                # Handle status change
                pass
    """

    def decorator(func: Callable) -> Callable:
        # Store condition metadata on the function
        func._trigger_condition = condition

        @wraps(func)
        def wrapper(sender, instances=None, originals=None, **kwargs):
            if not instances:
                return

            if condition:
                # Filter instances based on condition
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
