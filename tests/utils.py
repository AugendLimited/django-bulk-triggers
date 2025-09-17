"""
Utility functions and helpers for testing django-bulk-triggers.
"""

import logging
from typing import Any, List, Optional

from django.db import models

from django_bulk_triggers import TriggerClass
from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.enums import Priority
from tests.models import SimpleModel, TriggerModel


class TriggerTracker:
    """Utility class to track trigger calls for testing."""

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
        """Add a trigger call to tracking."""
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


def create_test_trigger_class(
    tracker: TriggerTracker, model_class, events: List[str] = None
):
    """
    Create a test trigger class that tracks calls.

    Args:
        tracker: TriggerTracker instance to track calls
        model_class: Django model class to trigger into
        events: List of events to trigger into (defaults to all events)

    Returns:
        Trigger class that tracks calls
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

    class TestTrigger(Trigger):
        def __init__(self):
            self.tracker = tracker

        def _create_trigger_method(self, event):
            def trigger_method(new_records, old_records=None, **kwargs):
                self.tracker.add_call(event, new_records, old_records, **kwargs)

            return trigger_method

    # Dynamically add trigger methods for each event
    for event in events:
        method_name = f"on_{event}"
        setattr(
            TestTrigger,
            method_name,
            trigger(event, model=model_class)(
                TestTrigger._create_trigger_method.__get__(None, TestTrigger)(event)
            ),
        )

    return TestTrigger


def assert_trigger_called(tracker: TriggerTracker, event: str, expected_count: int = 1):
    """Assert that a specific trigger event was called the expected number of times."""
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


def assert_trigger_not_called(tracker: TriggerTracker, event: str):
    """Assert that a specific trigger event was not called."""
    assert_trigger_called(tracker, event, expected_count=0)


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


def re_register_test_triggers():
    """
    Re-register test triggers after they've been cleared.
    This is needed because the test setup calls clear_triggers() which removes
    all registered triggers, but the trigger classes are already defined.

    The @trigger decorator automatically registers triggers via the TriggerMeta metaclass,
    but only when the class is first created. After clear_triggers() is called, we need
    to manually re-register them since the classes are already created.
    """
    from django_bulk_triggers.handler import TriggerMeta
    from django_bulk_triggers.registry import clear_triggers
    from tests.test_integration import (
        AuditTrigger,
        BulkCreateTestTrigger,
        BulkDeleteTestTrigger,
        BulkUpdateTestTrigger,
        ComplexConditionalTestTrigger,
        ConditionalTestTrigger,
        ErrorTestTrigger,
        InventoryTrigger,
        MultiModelTestTrigger,
        PerformanceTestTrigger,
        PriorityTestTrigger,
        RelatedTestTrigger,
        TransactionTestTrigger,
        UserRegistrationTrigger,
    )

    # Clear the registry first to ensure clean state
    clear_triggers()

    # Re-register all triggers using the new method
    TriggerMeta.re_register_all_triggers()
