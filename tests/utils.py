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
    from django_bulk_hooks.registry import register_hook
    from tests.test_integration import (
        BulkCreateTestHook,
        BulkUpdateTestHook,
        BulkDeleteTestHook,
        ConditionalTestHook,
        ComplexConditionalTestHook,
        ErrorTestHook,
        PerformanceTestHook,
        RelatedTestHook,
        TransactionTestHook,
        MultiModelTestHook,
        PriorityTestHook,
        InventoryHook,
        AuditHook,
        UserRegistrationHook,
    )
    
    # Clear the registry first to ensure clean state
    from django_bulk_hooks.registry import clear_hooks
    clear_hooks()
    
    # Manually register the hooks for each class
    # BulkCreateTestHook
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=BulkCreateTestHook,
        method_name="on_before_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=AFTER_CREATE,
        handler_cls=BulkCreateTestHook,
        method_name="on_after_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # BulkUpdateTestHook
    register_hook(
        model=HookModel,
        event=BEFORE_UPDATE,
        handler_cls=BulkUpdateTestHook,
        method_name="on_before_update",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=AFTER_UPDATE,
        handler_cls=BulkUpdateTestHook,
        method_name="on_after_update",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # BulkDeleteTestHook
    register_hook(
        model=HookModel,
        event=BEFORE_DELETE,
        handler_cls=BulkDeleteTestHook,
        method_name="on_before_delete",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=AFTER_DELETE,
        handler_cls=BulkDeleteTestHook,
        method_name="on_after_delete",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # ConditionalTestHook
    from django_bulk_hooks.conditions import IsEqual, HasChanged
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=ConditionalTestHook,
        method_name="on_active_create",
        condition=IsEqual("status", "active"),
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=BEFORE_UPDATE,
        handler_cls=ConditionalTestHook,
        method_name="on_status_change",
        condition=HasChanged("status"),
        priority=Priority.NORMAL,
    )
    
    # ComplexConditionalTestHook
    from django_bulk_hooks.conditions import HasChanged
    register_hook(
        model=HookModel,
        event=BEFORE_UPDATE,
        handler_cls=ComplexConditionalTestHook,
        method_name="on_status_change",
        condition=HasChanged("status"),
        priority=Priority.NORMAL,
    )
    
    # ErrorTestHook
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=ErrorTestHook,
        method_name="on_before_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # PerformanceTestHook
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=PerformanceTestHook,
        method_name="on_before_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # RelatedTestHook
    register_hook(
        model=HookModel,
        event=AFTER_CREATE,
        handler_cls=RelatedTestHook,
        method_name="on_after_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # TransactionTestHook
    register_hook(
        model=HookModel,
        event=AFTER_CREATE,
        handler_cls=TransactionTestHook,
        method_name="on_after_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # MultiModelTestHook
    from tests.models import SimpleModel
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=MultiModelTestHook,
        method_name="on_test_model_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=SimpleModel,
        event=BEFORE_CREATE,
        handler_cls=MultiModelTestHook,
        method_name="on_simple_model_create",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # PriorityTestHook
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=PriorityTestHook,
        method_name="high_priority",
        condition=None,
        priority=Priority.HIGH,
    )
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=PriorityTestHook,
        method_name="normal_priority",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=BEFORE_CREATE,
        handler_cls=PriorityTestHook,
        method_name="low_priority",
        condition=None,
        priority=Priority.LOW,
    )
    
    # InventoryHook
    register_hook(
        model=HookModel,
        event=BEFORE_UPDATE,
        handler_cls=InventoryHook,
        method_name="check_stock_levels",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=AFTER_DELETE,
        handler_cls=InventoryHook,
        method_name="log_deletion",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # AuditHook
    register_hook(
        model=HookModel,
        event=AFTER_CREATE,
        handler_cls=AuditHook,
        method_name="log_creation",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=AFTER_UPDATE,
        handler_cls=AuditHook,
        method_name="log_status_change",
        condition=None,
        priority=Priority.NORMAL,
    )
    register_hook(
        model=HookModel,
        event=AFTER_DELETE,
        handler_cls=AuditHook,
        method_name="log_deletion",
        condition=None,
        priority=Priority.NORMAL,
    )
    
    # UserRegistrationHook
    from tests.models import User
    register_hook(
        model=User,
        event=AFTER_CREATE,
        handler_cls=UserRegistrationHook,
        method_name="send_welcome_email",
        condition=None,
        priority=Priority.NORMAL,
    )
