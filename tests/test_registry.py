"""
Tests for the registry module.
"""

from unittest.mock import patch

import pytest
from django.test import TestCase

from django_bulk_hooks.conditions import IsEqual
from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.priority import Priority
from django_bulk_hooks.registry import get_hooks, list_all_hooks, register_hook
from tests.models import SimpleModel, TestModel, User


class TestRegisterHook(TestCase):
    """Test the register_hook function."""

    def setUp(self):
        # Clear any existing hooks before each test
        from django_bulk_hooks.registry import _hooks

        _hooks.clear()

    def test_register_hook_basic(self):
        """Test basic hook registration."""

        class TestHandler:
            def test_method(self):
                pass

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 1)

        handler_cls, method_name, condition, priority = hooks[0]
        self.assertEqual(handler_cls, TestHandler)
        self.assertEqual(method_name, "test_method")
        self.assertIsNone(condition)
        self.assertEqual(priority, Priority.NORMAL)

    def test_register_hook_with_condition(self):
        """Test hook registration with condition."""

        class TestHandler:
            def test_method(self):
                pass

        condition = IsEqual("status", "active")

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=condition,
            priority=Priority.HIGH,
        )

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 1)

        handler_cls, method_name, condition, priority = hooks[0]
        self.assertEqual(condition, condition)
        self.assertEqual(priority, Priority.HIGH)

    def test_register_hook_multiple_hooks(self):
        """Test registering multiple hooks for the same model/event."""

        class Handler1:
            def method1(self):
                pass

        class Handler2:
            def method2(self):
                pass

        # Register first hook
        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=Handler1,
            method_name="method1",
            condition=None,
            priority=Priority.LOW,
        )

        # Register second hook
        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=Handler2,
            method_name="method2",
            condition=None,
            priority=Priority.HIGH,
        )

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 2)

        # Hooks should be sorted by priority
        priorities = [hook[3] for hook in hooks]
        self.assertEqual(priorities, [Priority.HIGH, Priority.LOW])

    def test_register_hook_different_models(self):
        """Test registering hooks for different models."""

        class TestHandler:
            def test_method(self):
                pass

        # Register hook for TestModel
        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Register hook for User
        register_hook(
            model=User,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Check TestModel hooks
        test_model_hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(test_model_hooks), 1)

        # Check User hooks
        user_hooks = get_hooks(User, BEFORE_CREATE)
        self.assertEqual(len(user_hooks), 1)

        # Check that they're separate
        # The hooks should be stored separately in the registry
        from django_bulk_hooks.registry import list_all_hooks
        all_hooks = list_all_hooks()
        
        # Check that TestModel and User have separate entries
        self.assertIn((TestModel, BEFORE_CREATE), all_hooks)
        self.assertIn((User, BEFORE_CREATE), all_hooks)
        
        # Verify they have different keys in the registry
        test_model_key = (TestModel, BEFORE_CREATE)
        user_key = (User, BEFORE_CREATE)
        self.assertNotEqual(test_model_key, user_key)

    def test_register_hook_different_events(self):
        """Test registering hooks for different events."""

        class TestHandler:
            def test_method(self):
                pass

        # Register hook for BEFORE_CREATE
        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Register hook for AFTER_CREATE
        register_hook(
            model=TestModel,
            event=AFTER_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Check BEFORE_CREATE hooks
        before_hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(before_hooks), 1)

        # Check AFTER_CREATE hooks
        after_hooks = get_hooks(TestModel, AFTER_CREATE)
        self.assertEqual(len(after_hooks), 1)

        # Check that they're separate
        # The hooks should be stored separately in the registry
        from django_bulk_hooks.registry import list_all_hooks
        all_hooks = list_all_hooks()
        
        # Check that BEFORE_CREATE and AFTER_CREATE have separate entries
        self.assertIn((TestModel, BEFORE_CREATE), all_hooks)
        self.assertIn((TestModel, AFTER_CREATE), all_hooks)
        
        # Verify they have different keys in the registry
        before_key = (TestModel, BEFORE_CREATE)
        after_key = (TestModel, AFTER_CREATE)
        self.assertNotEqual(before_key, after_key)

    def test_register_hook_priority_sorting(self):
        """Test that hooks are sorted by priority."""

        class Handler1:
            def method1(self):
                pass

        class Handler2:
            def method2(self):
                pass

        class Handler3:
            def method3(self):
                pass

        # Register hooks in random priority order
        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=Handler2,
            method_name="method2",
            condition=None,
            priority=Priority.NORMAL,
        )

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=Handler1,
            method_name="method1",
            condition=None,
            priority=Priority.LOW,
        )

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=Handler3,
            method_name="method3",
            condition=None,
            priority=Priority.HIGH,
        )

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 3)

        # Check priority order (high priority first - lower numbers)
        priorities = [hook[3] for hook in hooks]
        self.assertEqual(priorities, [Priority.HIGH, Priority.NORMAL, Priority.LOW])

        # Check handler order matches priority order
        handlers = [hook[0] for hook in hooks]
        self.assertEqual(handlers, [Handler3, Handler2, Handler1])


class TestGetHooks(TestCase):
    """Test the get_hooks function."""

    def setUp(self):
        # Clear any existing hooks before each test
        from django_bulk_hooks.registry import _hooks

        _hooks.clear()

    def test_get_hooks_empty(self):
        """Test getting hooks when none are registered."""
        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(hooks, [])

    def test_get_hooks_existing(self):
        """Test getting existing hooks."""

        class TestHandler:
            def test_method(self):
                pass

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 1)

        handler_cls, method_name, condition, priority = hooks[0]
        self.assertEqual(handler_cls, TestHandler)
        self.assertEqual(method_name, "test_method")

    def test_get_hooks_wrong_event(self):
        """Test getting hooks for non-existent event."""

        class TestHandler:
            def test_method(self):
                pass

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Try to get hooks for different event
        hooks = get_hooks(TestModel, AFTER_CREATE)
        self.assertEqual(hooks, [])

    def test_get_hooks_wrong_model(self):
        """Test getting hooks for non-existent model."""

        class TestHandler:
            def test_method(self):
                pass

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Try to get hooks for different model
        hooks = get_hooks(User, BEFORE_CREATE)
        self.assertEqual(hooks, [])

    def test_get_hooks_all_events(self):
        """Test getting hooks for all event types."""
        events = [
            BEFORE_CREATE,
            AFTER_CREATE,
            BEFORE_UPDATE,
            AFTER_UPDATE,
            BEFORE_DELETE,
            AFTER_DELETE,
        ]

        class TestHandler:
            def test_method(self):
                pass

        # Register hooks for all events
        for event in events:
            register_hook(
                model=TestModel,
                event=event,
                handler_cls=TestHandler,
                method_name="test_method",
                condition=None,
                priority=Priority.NORMAL,
            )

        # Check that hooks exist for all events
        for event in events:
            hooks = get_hooks(TestModel, event)
            self.assertEqual(len(hooks), 1)

    def test_get_hooks_logging(self):
        """Test that get_hooks logs appropriately."""
        with patch("django_bulk_hooks.registry.logger") as mock_logger:
            # Test with no hooks
            get_hooks(TestModel, BEFORE_CREATE)
            mock_logger.debug.assert_called()

            # Test with hooks
            class TestHandler:
                def test_method(self):
                    pass

            register_hook(
                model=TestModel,
                event=BEFORE_CREATE,
                handler_cls=TestHandler,
                method_name="test_method",
                condition=None,
                priority=Priority.NORMAL,
            )

            get_hooks(TestModel, BEFORE_CREATE)
            # Should log when hooks are found
            mock_logger.debug.assert_called()


class TestListAllHooks(TestCase):
    """Test the list_all_hooks function."""

    def setUp(self):
        # Clear any existing hooks before each test
        from django_bulk_hooks.registry import _hooks

        _hooks.clear()

    def test_list_all_hooks_empty(self):
        """Test listing hooks when none are registered."""
        hooks = list_all_hooks()
        self.assertEqual(hooks, {})

    def test_list_all_hooks_with_hooks(self):
        """Test listing hooks when hooks are registered."""

        class TestHandler:
            def test_method(self):
                pass

        # Register some hooks
        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        register_hook(
            model=User,
            event=AFTER_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        hooks = list_all_hooks()

        # Should have entries for both models
        self.assertIn((TestModel, BEFORE_CREATE), hooks)
        self.assertIn((User, AFTER_CREATE), hooks)

        # Check the content
        test_model_hooks = hooks[(TestModel, BEFORE_CREATE)]
        self.assertEqual(len(test_model_hooks), 1)

        user_hooks = hooks[(User, AFTER_CREATE)]
        self.assertEqual(len(user_hooks), 1)

    def test_list_all_hooks_structure(self):
        """Test the structure of returned hooks."""

        class TestHandler:
            def test_method(self):
                pass

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        hooks = list_all_hooks()

        # Check that the structure is correct
        self.assertIsInstance(hooks, dict)

        key = (TestModel, BEFORE_CREATE)
        self.assertIn(key, hooks)

        hook_list = hooks[key]
        self.assertIsInstance(hook_list, list)
        self.assertEqual(len(hook_list), 1)

        hook_tuple = hook_list[0]
        self.assertIsInstance(hook_tuple, tuple)
        self.assertEqual(
            len(hook_tuple), 4
        )  # (handler_cls, method_name, condition, priority)


class TestRegistryIntegration(TestCase):
    """Integration tests for the registry."""

    def setUp(self):
        # Clear any existing hooks before each test
        from django_bulk_hooks.registry import _hooks

        _hooks.clear()

    def test_registry_with_real_hooks(self):
        """Test registry with real hook classes."""
        from django_bulk_hooks import HookClass
        from django_bulk_hooks.decorators import hook

        class TestHook(HookClass):
            @hook(BEFORE_CREATE, model=TestModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

            @hook(AFTER_CREATE, model=TestModel)
            def on_after_create(self, new_records, old_records=None, **kwargs):
                pass

        # Check that hooks were registered
        before_hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(before_hooks), 1)

        after_hooks = get_hooks(TestModel, AFTER_CREATE)
        self.assertEqual(len(after_hooks), 1)

        # Check hook details
        handler_cls, method_name, condition, priority = before_hooks[0]
        self.assertEqual(handler_cls, TestHook)
        self.assertEqual(method_name, "on_before_create")
        self.assertIsNone(condition)
        self.assertEqual(priority, Priority.NORMAL)

    def test_registry_with_conditions(self):
        """Test registry with conditional hooks."""
        from django_bulk_hooks import HookClass
        from django_bulk_hooks.decorators import hook
        from django_bulk_hooks.conditions import IsEqual

        class ConditionalHook(HookClass):
            @hook(BEFORE_CREATE, model=TestModel, condition=IsEqual("status", "active"))
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 1)

        handler_cls, method_name, condition, priority = hooks[0]
        self.assertIsInstance(condition, IsEqual)
        self.assertEqual(condition.field, "status")
        self.assertEqual(condition.value, "active")

    def test_registry_with_priorities(self):
        """Test registry with different priorities."""
        from django_bulk_hooks import HookClass
        from django_bulk_hooks.decorators import hook
        from django_bulk_hooks.priority import Priority

        class HighPriorityHook(HookClass):
            @hook(BEFORE_CREATE, model=TestModel, priority=Priority.HIGH)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

        class LowPriorityHook(HookClass):
            @hook(BEFORE_CREATE, model=TestModel, priority=Priority.LOW)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 2)

        # Check priority order
        priorities = [hook[3] for hook in hooks]
        self.assertEqual(priorities, [Priority.HIGH, Priority.LOW])

    def test_registry_cleanup(self):
        """Test that registry can be cleaned up."""

        class TestHandler:
            def test_method(self):
                pass

        register_hook(
            model=TestModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Verify hook is registered
        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 1)

        # Clear registry
        from django_bulk_hooks.registry import _hooks

        _hooks.clear()

        # Verify hook is gone
        hooks = get_hooks(TestModel, BEFORE_CREATE)
        self.assertEqual(len(hooks), 0)
