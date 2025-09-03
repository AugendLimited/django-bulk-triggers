"""
Utility functions and helpers for testing django-bulk-hooks.
"""

import logging
from typing import Any, List, Optional

from django.db import models

from django_bulk_hooks import HookClass
from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.decorators import hook
from django_bulk_hooks.priority import Priority
from tests.models import HookModel, SimpleModel


class HookTracker:
    """Utility class to track hook calls for testing."""

    def __init__(self):
        self.calls = []
        self.before_create_calls = []
        self.after_create_calls = []
        self.before_update_calls = []
        self.after_update_calls = []
        self.before_delete_calls = []
        self.after_delete_calls = []

    def reset(self):
        """Reset all call tracking."""
        self.calls.clear()
        self.before_create_calls.clear()
        self.after_create_calls.clear()
        self.before_update_calls.clear()
        self.after_update_calls.clear()
        self.before_delete_calls.clear()
        self.after_delete_calls.clear()

    def add_call(
        self,
        event: str,
        new_records: List,
        old_records: Optional[List] = None,
        **kwargs,
    ):
        """Add a hook call to tracking."""
        call_data = {
            "event": event,
            "new_records": new_records,
            "old_records": old_records,
            "kwargs": kwargs,
        }
        self.calls.append(call_data)

        if event == BEFORE_CREATE:
            self.before_create_calls.append(call_data)
        elif event == AFTER_CREATE:
            self.after_create_calls.append(call_data)
        elif event == BEFORE_UPDATE:
            self.before_update_calls.append(call_data)
        elif event == AFTER_UPDATE:
            self.after_update_calls.append(call_data)
        elif event == BEFORE_DELETE:
            self.before_delete_calls.append(call_data)
        elif event == AFTER_DELETE:
            self.after_delete_calls.append(call_data)


def create_test_hook_class(
    tracker: HookTracker, model_class, events: List[str] = None
):
    """
    Create a test hook class that tracks calls.

    Args:
        tracker: HookTracker instance to track calls
        model_class: Django model class to hook into
        events: List of events to hook into (defaults to all events)

    Returns:
        Hook class that tracks calls
    """
    if events is None:
        events = [
            BEFORE_CREATE,
            AFTER_CREATE,
            BEFORE_UPDATE,
            AFTER_UPDATE,
            BEFORE_DELETE,
            AFTER_DELETE,
        ]

    class TestHook(Hook):
        def __init__(self):
            self.tracker = tracker

        def _create_hook_method(self, event):
            def hook_method(new_records, old_records=None, **kwargs):
                self.tracker.add_call(event, new_records, old_records, **kwargs)

            return hook_method

    # Dynamically add hook methods for each event
    for event in events:
        method_name = f"on_{event}"
        setattr(
            TestHook,
            method_name,
            hook(event, model=model_class)(
                TestHook._create_hook_method.__get__(None, TestHook)(event)
            ),
        )

    return TestHook


def assert_hook_called(tracker: HookTracker, event: str, expected_count: int = 1):
    """Assert that a specific hook event was called the expected number of times."""
    if event == BEFORE_CREATE:
        actual_count = len(tracker.before_create_calls)
    elif event == AFTER_CREATE:
        actual_count = len(tracker.after_create_calls)
    elif event == BEFORE_UPDATE:
        actual_count = len(tracker.before_update_calls)
    elif event == AFTER_UPDATE:
        actual_count = len(tracker.after_update_calls)
    elif event == BEFORE_DELETE:
        actual_count = len(tracker.before_delete_calls)
    elif event == AFTER_DELETE:
        actual_count = len(tracker.after_delete_calls)
    else:
        raise ValueError(f"Unknown event: {event}")

    assert actual_count == expected_count, (
        f"Expected {expected_count} calls for {event}, got {actual_count}"
    )


def assert_hook_not_called(tracker: HookTracker, event: str):
    """Assert that a specific hook event was not called."""
    assert_hook_called(tracker, event, expected_count=0)


def create_test_instances(model_class, count: int = 3, **kwargs) -> List[models.Model]:
    """Create test instances of a model class."""
    instances = []
    for i in range(count):
        instance_data = {"name": f"Test {i}", "value": i, **kwargs}
        # Filter out fields that don't exist on the model
        filtered_data = {
            k: v for k, v in instance_data.items() if hasattr(model_class, k)
        }
        instance = model_class(**filtered_data)
        instances.append(instance)
    return instances


def setup_logging():
    """Setup logging for tests."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


class MockException(Exception):
    """Mock exception for testing error handling."""

    pass


def re_register_test_hooks():
    """
    Re-register test hooks after they've been cleared.
    This is needed because the test setup calls clear_hooks() which removes
    all registered hooks, but the hook classes are already defined.
    """
    from django_bulk_hooks.registry import register_hook, clear_hooks
    from django_bulk_hooks.conditions import IsEqual, HasChanged
    from tests.models import SimpleModel
    from tests.test_integration import (
        BulkCreateTestHook, BulkUpdateTestHook, BulkDeleteTestHook,
        ConditionalTestHook, ComplexConditionalTestHook, ErrorTestHook,
        PerformanceTestHook, RelatedTestHook, TransactionTestHook,
        MultiModelTestHook, PriorityTestHook, InventoryHook,
        AuditHook, UserRegistrationHook,
    )

    # Clear the registry first to ensure clean state
    clear_hooks()

    # Define all hook registrations in a data structure for maintainability
    hook_registrations = [
        # (model, event, handler_cls, method_name, condition, priority)

        # BulkCreateTestHook
        (HookModel, BEFORE_CREATE, BulkCreateTestHook, "on_before_create", None, Priority.NORMAL),
        (HookModel, AFTER_CREATE, BulkCreateTestHook, "on_after_create", None, Priority.NORMAL),

        # BulkUpdateTestHook
        (HookModel, BEFORE_UPDATE, BulkUpdateTestHook, "on_before_update", None, Priority.NORMAL),
        (HookModel, AFTER_UPDATE, BulkUpdateTestHook, "on_after_update", None, Priority.NORMAL),

        # BulkDeleteTestHook
        (HookModel, BEFORE_DELETE, BulkDeleteTestHook, "on_before_delete", None, Priority.NORMAL),
        (HookModel, AFTER_DELETE, BulkDeleteTestHook, "on_after_delete", None, Priority.NORMAL),

        # ConditionalTestHook
        (HookModel, BEFORE_CREATE, ConditionalTestHook, "on_active_create", IsEqual("status", "active"), Priority.NORMAL),
        (HookModel, BEFORE_UPDATE, ConditionalTestHook, "on_status_change", HasChanged("status"), Priority.NORMAL),

        # ComplexConditionalTestHook
        (HookModel, BEFORE_UPDATE, ComplexConditionalTestHook, "on_status_change", HasChanged("status"), Priority.NORMAL),

        # ErrorTestHook
        (HookModel, BEFORE_CREATE, ErrorTestHook, "on_before_create", None, Priority.NORMAL),

        # PerformanceTestHook
        (HookModel, BEFORE_CREATE, PerformanceTestHook, "on_before_create", None, Priority.NORMAL),

        # RelatedTestHook
        (HookModel, AFTER_CREATE, RelatedTestHook, "on_after_create", None, Priority.NORMAL),

        # TransactionTestHook
        (HookModel, AFTER_CREATE, TransactionTestHook, "on_after_create", None, Priority.NORMAL),

        # MultiModelTestHook
        (HookModel, BEFORE_CREATE, MultiModelTestHook, "on_test_model_create", None, Priority.NORMAL),
        (SimpleModel, BEFORE_CREATE, MultiModelTestHook, "on_simple_model_create", None, Priority.NORMAL),

        # PriorityTestHook
        (HookModel, BEFORE_CREATE, PriorityTestHook, "high_priority", None, Priority.HIGH),
        (HookModel, BEFORE_CREATE, PriorityTestHook, "normal_priority", None, Priority.NORMAL),
        (HookModel, BEFORE_CREATE, PriorityTestHook, "low_priority", None, Priority.LOW),

        # InventoryHook
        (HookModel, BEFORE_UPDATE, InventoryHook, "check_stock_levels", None, Priority.NORMAL),
        (HookModel, AFTER_DELETE, InventoryHook, "log_deletion", None, Priority.NORMAL),

        # AuditHook
        (HookModel, AFTER_CREATE, AuditHook, "log_creation", None, Priority.NORMAL),
        (HookModel, AFTER_UPDATE, AuditHook, "log_status_change", None, Priority.NORMAL),
        (HookModel, AFTER_DELETE, AuditHook, "log_deletion", None, Priority.NORMAL),

        # UserRegistrationHook
        (SimpleModel, BEFORE_CREATE, UserRegistrationHook, "validate_user", None, Priority.NORMAL),
        (SimpleModel, AFTER_CREATE, UserRegistrationHook, "send_welcome_email", None, Priority.NORMAL),
    ]

    # Register all hooks in a loop
    for model, event, handler_cls, method_name, condition, priority in hook_registrations:
        register_hook(
            model=model,
            event=event,
            handler_cls=handler_cls,
            method_name=method_name,
            condition=condition,
            priority=priority,
        )
