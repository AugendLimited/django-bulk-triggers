"""
Tests for the handler module.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.db import transaction
from django.test import TestCase

from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.decorators import hook
from django_bulk_hooks.handler import (
    Hook,
    HookContextState,
    _hook_context,
    get_hook_queue,
    hook_vars,
)
from django_bulk_hooks import HookClass
from tests.models import SimpleModel, TestModel
from tests.utils import TestHookTracker, assert_hook_called, create_test_instances


class TestHookContextState(TestCase):
    """Test HookContextState properties."""

    def setUp(self):
        self.hook_state = HookContextState()
        
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_is_before_property(self):
        """Test is_before property."""
        hook_vars.event = BEFORE_CREATE
        self.assertTrue(self.hook_state.is_before)

        hook_vars.event = AFTER_CREATE
        self.assertFalse(self.hook_state.is_before)

    def test_is_after_property(self):
        """Test is_after property."""
        hook_vars.event = AFTER_CREATE
        self.assertTrue(self.hook_state.is_after)

        hook_vars.event = BEFORE_CREATE
        self.assertFalse(self.hook_state.is_after)

    def test_is_create_property(self):
        """Test is_create property."""
        hook_vars.event = BEFORE_CREATE
        self.assertTrue(self.hook_state.is_create)

        hook_vars.event = AFTER_UPDATE
        self.assertFalse(self.hook_state.is_create)

    def test_is_update_property(self):
        """Test is_update property."""
        hook_vars.event = BEFORE_UPDATE
        self.assertTrue(self.hook_state.is_update)

        hook_vars.event = AFTER_CREATE
        self.assertFalse(self.hook_state.is_update)

    def test_new_property(self):
        """Test new property."""
        test_records = [TestModel(name="Test")]
        hook_vars.new = test_records
        self.assertEqual(self.hook_state.new, test_records)

    def test_old_property(self):
        """Test old property."""
        test_records = [TestModel(name="Test")]
        hook_vars.old = test_records
        self.assertEqual(self.hook_state.old, test_records)

    def test_model_property(self):
        """Test model property."""
        hook_vars.model = TestModel
        self.assertEqual(self.hook_state.model, TestModel)


class TestHookQueue(TestCase):
    """Test hook queue functionality."""

    def test_get_hook_queue_creates_new_queue(self):
        """Test that get_hook_queue creates a new queue if none exists."""
        # Clear any existing queue by accessing the thread local directly
        if hasattr(_hook_context, "queue"):
            delattr(_hook_context, "queue")

        queue = get_hook_queue()
        self.assertIsNotNone(queue)
        self.assertEqual(len(queue), 0)

    def test_get_hook_queue_returns_existing_queue(self):
        """Test that get_hook_queue returns existing queue."""
        queue1 = get_hook_queue()
        queue1.append("test_item")

        queue2 = get_hook_queue()
        self.assertEqual(queue1, queue2)
        self.assertEqual(len(queue2), 1)
        self.assertEqual(queue2[0], "test_item")


class TestHookMeta(TestCase):
    """Test HookMeta metaclass functionality."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_hook_registration_via_metaclass(self):
        """Test that hooks are registered via metaclass."""
        tracker = TestHookTracker()

        class TestHookClass(Hook):
            def __init__(self):
                self.tracker = tracker

            @hook(BEFORE_CREATE, model=TestModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify the hook was registered
        from django_bulk_hooks.registry import get_hooks

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertGreater(len(hooks), 0)

        # Find our hook
        found = False
        for handler_cls, method_name, condition, priority in hooks:
            if handler_cls == TestHookClass and method_name == "on_before_create":
                found = True
                break
        self.assertTrue(found)


class TestHookHandle(TestCase):
    """Test HookClass.handle method."""

    def setUp(self):
        self.tracker = TestHookTracker()
        self.test_instances = create_test_instances(TestModel, 2)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_handle_queues_hook_call(self):
        """Test that handle queues the hook call."""
        queue = get_hook_queue()
        initial_length = len(queue)

        HookClass.handle(BEFORE_CREATE, TestModel, new_records=self.test_instances)

        # The queue should be empty after processing since depth == 0
        self.assertEqual(len(queue), 0)

    def test_handle_nested_calls(self):
        """Test that nested handle calls don't process immediately."""
        with patch.object(HookClass, "_process") as mock_process:
            # First call
            HookClass.handle(BEFORE_CREATE, TestModel, new_records=self.test_instances)
            # Second call (not nested since depth == 0)
            HookClass.handle(AFTER_CREATE, TestModel, new_records=self.test_instances)

            # Both calls should trigger processing since depth == 0
            self.assertEqual(mock_process.call_count, 2)

    def test_handle_processes_queue(self):
        """Test that handle processes the entire queue."""
        with patch.object(HookClass, "_process") as mock_process:
            HookClass.handle(BEFORE_CREATE, TestModel, new_records=self.test_instances)

            mock_process.assert_called_once()
            args = mock_process.call_args
            self.assertEqual(args[0][0], BEFORE_CREATE)  # event
            self.assertEqual(args[0][1], TestModel)  # model
            self.assertEqual(args[0][2], self.test_instances)  # new_records


class TestHookProcess(TestCase):
    """Test HookClass._process method."""

    def setUp(self):
        self.tracker = TestHookTracker()
        self.test_instances = create_test_instances(TestModel, 2)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_process_sets_hook_vars(self):
        """Test that _process sets hook_vars correctly."""
        initial_depth = hook_vars.depth

        HookClass._process(BEFORE_CREATE, TestModel, self.test_instances, None)

        self.assertEqual(hook_vars.depth, initial_depth)
        self.assertIsNone(hook_vars.new)
        self.assertIsNone(hook_vars.old)
        self.assertIsNone(hook_vars.event)
        self.assertIsNone(hook_vars.model)

    def test_process_increments_depth(self):
        """Test that _process increments and decrements depth."""
        initial_depth = hook_vars.depth

        HookClass._process(BEFORE_CREATE, TestModel, self.test_instances, None)

        self.assertEqual(hook_vars.depth, initial_depth)

    def test_process_with_transaction_commit(self):
        """Test that _process handles transaction commits correctly."""
        with patch("django.db.transaction.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.in_atomic_block = True
            mock_get_conn.return_value = mock_conn

            with patch("django.db.transaction.on_commit") as mock_on_commit:
                HookClass._process(AFTER_CREATE, TestModel, self.test_instances, None)

                mock_on_commit.assert_called_once()

    def test_process_without_transaction_commit(self):
        """Test that _process executes immediately when not in transaction."""
        with patch("django.db.transaction.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.in_atomic_block = False
            mock_get_conn.return_value = mock_conn

            with patch("django.db.transaction.on_commit") as mock_on_commit:
                HookClass._process(BEFORE_CREATE, TestModel, self.test_instances, None)

                mock_on_commit.assert_not_called()

    def test_process_handles_exceptions(self):
        """Test that _process handles exceptions gracefully."""
        with patch("django_bulk_hooks.handler.logger") as mock_logger:
            # Create a hook that raises an exception
            class ExceptionHook(HookClass):
                @hook(BEFORE_CREATE, model=TestModel)
                def on_before_create(self, new_records, old_records=None, **kwargs):
                    raise ValueError("Test exception")

            # This should not raise an exception
            HookClass._process(BEFORE_CREATE, TestModel, self.test_instances, None)

            # Should log the exception
            mock_logger.exception.assert_called()


class TestHookIntegration(TestCase):
    """Integration tests for Hook functionality."""

    def setUp(self):
        self.tracker = TestHookTracker()
        self.test_instances = create_test_instances(TestModel, 3)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_full_hook_cycle(self):
        """Test a complete hook cycle."""

        class TestHookClass(HookClass):
            tracker = TestHookTracker()  # Class variable to persist across instances
            
            def __init__(self):
                pass  # No need to create instance tracker

            @hook(BEFORE_CREATE, model=TestModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                TestHookClass.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

            @hook(BEFORE_CREATE, model=TestModel)
            def on_after_create(self, new_records, old_records=None, **kwargs):
                TestHookClass.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Hooks are automatically registered by the metaclass when the class is defined

        # Create hook instance
        hook_instance = TestHookClass()

        # Trigger hooks
        HookClass.handle(BEFORE_CREATE, TestModel, new_records=self.test_instances)
        HookClass.handle(AFTER_CREATE, TestModel, new_records=self.test_instances)

        # Verify calls were tracked
        assert_hook_called(TestHookClass.tracker, BEFORE_CREATE, 2)  # Both hooks are now BEFORE_CREATE

    def test_hook_with_conditions(self):
        """Test hooks with conditions."""
        from django_bulk_hooks.conditions import IsEqual

        class ConditionalHook(HookClass):
            tracker = TestHookTracker()  # Class variable to persist across instances
            
            def __init__(self):
                pass  # No need to create instance tracker

            @hook(BEFORE_CREATE, model=TestModel, condition=IsEqual("status", "active"))
            def on_before_create(self, new_records, old_records=None, **kwargs):
                ConditionalHook.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Hooks are automatically registered by the metaclass when the class is defined

        # Create instances with different statuses
        active_instance = TestModel(name="Active", status="active")
        inactive_instance = TestModel(name="Inactive", status="inactive")

        hook_instance = ConditionalHook()

        # Trigger hooks
        HookClass.handle(
            BEFORE_CREATE, TestModel, new_records=[active_instance, inactive_instance]
        )

        # Only the active instance should trigger the hook
        assert_hook_called(ConditionalHook.tracker, BEFORE_CREATE, 1)
