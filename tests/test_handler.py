"""
Tests for the handler module.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.db import transaction
from django.test import TestCase

from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.handler import (
    Trigger,
    TriggerContextState,
    _trigger_context,
    get_trigger_queue,
    trigger_vars,
)
from django_bulk_triggers import TriggerClass
from tests.models import SimpleModel, TriggerModel
from tests.utils import TriggerTracker, assert_trigger_called, create_test_instances


class TestTriggerContextState(TestCase):
    """Test TriggerContextState properties."""

    def setUp(self):
        self.trigger_state = TriggerContextState()
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_is_before_property(self):
        """Test is_before property."""
        trigger_vars.event = BEFORE_CREATE
        self.assertTrue(self.trigger_state.is_before)

        trigger_vars.event = AFTER_CREATE
        self.assertFalse(self.trigger_state.is_before)

    def test_is_after_property(self):
        """Test is_after property."""
        trigger_vars.event = AFTER_CREATE
        self.assertTrue(self.trigger_state.is_after)

        trigger_vars.event = BEFORE_CREATE
        self.assertFalse(self.trigger_state.is_after)

    def test_is_create_property(self):
        """Test is_create property."""
        trigger_vars.event = BEFORE_CREATE
        self.assertTrue(self.trigger_state.is_create)

        trigger_vars.event = AFTER_UPDATE
        self.assertFalse(self.trigger_state.is_create)

    def test_is_update_property(self):
        """Test is_update property."""
        trigger_vars.event = BEFORE_UPDATE
        self.assertTrue(self.trigger_state.is_update)

        trigger_vars.event = AFTER_CREATE
        self.assertFalse(self.trigger_state.is_update)

    def test_new_property(self):
        """Test new property."""
        test_records = [TriggerModel(name="Test")]
        trigger_vars.new = test_records
        self.assertEqual(self.trigger_state.new, test_records)

    def test_old_property(self):
        """Test old property."""
        test_records = [TriggerModel(name="Test")]
        trigger_vars.old = test_records
        self.assertEqual(self.trigger_state.old, test_records)

    def test_model_property(self):
        """Test model property."""
        trigger_vars.model = TriggerModel
        self.assertEqual(self.trigger_state.model, TriggerModel)


class TestTriggerQueue(TestCase):
    """Test trigger queue functionality."""

    def test_get_trigger_queue_creates_new_queue(self):
        """Test that get_trigger_queue creates a new queue if none exists."""
        # Clear any existing queue by accessing the thread local directly
        if hasattr(_trigger_context, "queue"):
            delattr(_trigger_context, "queue")

        queue = get_trigger_queue()
        self.assertIsNotNone(queue)
        self.assertEqual(len(queue), 0)

    def test_get_trigger_queue_returns_existing_queue(self):
        """Test that get_trigger_queue returns existing queue."""
        queue1 = get_trigger_queue()
        queue1.append("test_item")

        queue2 = get_trigger_queue()
        self.assertEqual(queue1, queue2)
        self.assertEqual(len(queue2), 1)
        self.assertEqual(queue2[0], "test_item")


class TestTriggerMeta(TestCase):
    """Test TriggerMeta metaclass functionality."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_trigger_registration_via_metaclass(self):
        """Test that triggers are registered via metaclass."""
        tracker = TriggerTracker()

        class TestTriggerClass(Trigger):
            def __init__(self):
                self.tracker = tracker

            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify the trigger was registered
        from django_bulk_triggers.registry import get_triggers

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertGreater(len(triggers), 0)

        # Find our trigger
        found = False
        for handler_cls, method_name, condition, priority in triggers:
            if handler_cls == TestTriggerClass and method_name == "on_before_create":
                found = True
                break
        self.assertTrue(found)


class TestTriggerHandle(TestCase):
    """Test TriggerClass.handle method."""

    def setUp(self):
        self.tracker = TriggerTracker()
        self.test_instances = create_test_instances(TriggerModel, 2)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_handle_queues_trigger_call(self):
        """Test that handle queues the trigger call."""
        queue = get_trigger_queue()
        initial_length = len(queue)

        TriggerClass.handle(BEFORE_CREATE, TriggerModel, new_records=self.test_instances)

        # The queue should be empty after processing since depth == 0
        self.assertEqual(len(queue), 0)

    def test_handle_nested_calls(self):
        """Test that nested handle calls don't process immediately."""
        with patch.object(TriggerClass, "_process") as mock_process:
            # First call
            TriggerClass.handle(BEFORE_CREATE, TriggerModel, new_records=self.test_instances)
            # Second call (not nested since depth == 0)
            TriggerClass.handle(AFTER_CREATE, TriggerModel, new_records=self.test_instances)

            # Both calls should trigger processing since depth == 0
            self.assertEqual(mock_process.call_count, 2)

    def test_handle_processes_queue(self):
        """Test that handle processes the entire queue."""
        with patch.object(TriggerClass, "_process") as mock_process:
            TriggerClass.handle(BEFORE_CREATE, TriggerModel, new_records=self.test_instances)

            mock_process.assert_called_once()
            args = mock_process.call_args
            self.assertEqual(args[0][0], BEFORE_CREATE)  # event
            self.assertEqual(args[0][1], TriggerModel)  # model
            self.assertEqual(args[0][2], self.test_instances)  # new_records


class TestTriggerProcess(TestCase):
    """Test TriggerClass._process method."""

    def setUp(self):
        self.tracker = TriggerTracker()
        self.test_instances = create_test_instances(TriggerModel, 2)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_process_sets_trigger_vars(self):
        """Test that _process sets trigger_vars correctly."""
        initial_depth = trigger_vars.depth

        TriggerClass._process(BEFORE_CREATE, TriggerModel, self.test_instances, None)

        self.assertEqual(trigger_vars.depth, initial_depth)
        self.assertIsNone(trigger_vars.new)
        self.assertIsNone(trigger_vars.old)
        self.assertIsNone(trigger_vars.event)
        self.assertIsNone(trigger_vars.model)

    def test_process_increments_depth(self):
        """Test that _process increments and decrements depth."""
        initial_depth = trigger_vars.depth

        TriggerClass._process(BEFORE_CREATE, TriggerModel, self.test_instances, None)

        self.assertEqual(trigger_vars.depth, initial_depth)

    def test_process_with_transaction_commit(self):
        """Test that _process handles transaction commits correctly."""
        with patch("django.db.transaction.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.in_atomic_block = True
            mock_get_conn.return_value = mock_conn

            with patch("django.db.transaction.on_commit") as mock_on_commit:
                TriggerClass._process(AFTER_CREATE, TriggerModel, self.test_instances, None)

                mock_on_commit.assert_called_once()

    def test_process_without_transaction_commit(self):
        """Test that _process executes immediately when not in transaction."""
        with patch("django.db.transaction.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.in_atomic_block = False
            mock_get_conn.return_value = mock_conn

            with patch("django.db.transaction.on_commit") as mock_on_commit:
                TriggerClass._process(BEFORE_CREATE, TriggerModel, self.test_instances, None)

                mock_on_commit.assert_not_called()

    def test_process_handles_exceptions(self):
        """Test that _process handles exceptions gracefully."""
        with patch("django_bulk_triggers.handler.logger") as mock_logger:
            # Create a trigger that raises an exception
            class ExceptionTrigger(TriggerClass):
                @trigger(BEFORE_CREATE, model=TriggerModel)
                def on_before_create(self, new_records, old_records=None, **kwargs):
                    raise ValueError("Test exception")

            # This should not raise an exception
            TriggerClass._process(BEFORE_CREATE, TriggerModel, self.test_instances, None)

            # Should log the exception
            mock_logger.exception.assert_called()


class TestTriggerIntegration(TestCase):
    """Integration tests for Trigger functionality."""

    def setUp(self):
        self.tracker = TriggerTracker()
        self.test_instances = create_test_instances(TriggerModel, 3)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_full_trigger_cycle(self):
        """Test a complete trigger cycle."""

        class TestTriggerClass(TriggerClass):
            tracker = TriggerTracker()  # Class variable to persist across instances
            
            def __init__(self):
                pass  # No need to create instance tracker

            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                TestTriggerClass.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_after_create(self, new_records, old_records=None, **kwargs):
                TestTriggerClass.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Triggers are automatically registered by the metaclass when the class is defined

        # Create trigger instance
        trigger_instance = TestTriggerClass()

        # Trigger triggers
        TriggerClass.handle(BEFORE_CREATE, TriggerModel, new_records=self.test_instances)
        TriggerClass.handle(AFTER_CREATE, TriggerModel, new_records=self.test_instances)

        # Verify calls were tracked
        assert_trigger_called(TestTriggerClass.tracker, BEFORE_CREATE, 2)  # Both triggers are now BEFORE_CREATE

    def test_trigger_with_conditions(self):
        """Test triggers with conditions."""
        from django_bulk_triggers.conditions import IsEqual

        class ConditionalTrigger(TriggerClass):
            tracker = TriggerTracker()  # Class variable to persist across instances
            
            def __init__(self):
                pass  # No need to create instance tracker

            @trigger(BEFORE_CREATE, model=TriggerModel, condition=IsEqual("status", "active"))
            def on_before_create(self, new_records, old_records=None, **kwargs):
                ConditionalTrigger.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Triggers are automatically registered by the metaclass when the class is defined

        # Create instances with different statuses
        active_instance = TriggerModel(name="Active", status="active")
        inactive_instance = TriggerModel(name="Inactive", status="inactive")

        trigger_instance = ConditionalTrigger()

        # Trigger triggers
        TriggerClass.handle(
            BEFORE_CREATE, TriggerModel, new_records=[active_instance, inactive_instance]
        )

        # Only the active instance should trigger the trigger
        assert_trigger_called(ConditionalTrigger.tracker, BEFORE_CREATE, 1)
