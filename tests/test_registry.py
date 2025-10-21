"""
Tests for the registry module.
"""

from unittest.mock import patch

import pytest
from django.test import TestCase

from django_bulk_triggers.conditions import IsEqual
from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_triggers.enums import Priority
from django_bulk_triggers.registry import get_triggers, list_all_triggers, register_trigger
from tests.models import SimpleModel, TriggerModel, UserModel


class TestRegisterTrigger(TestCase):
    """Test the register_trigger function."""

    def setUp(self):
        # Clear any existing triggers before each test
        from django_bulk_triggers.registry import _triggers

        _triggers.clear()

    def test_register_trigger_basic(self):
        """Test basic trigger registration."""

        class TestHandler:
            def test_method(self):
                pass

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 1)

        handler_cls, method_name, condition, priority = triggers[0]
        self.assertEqual(handler_cls, TestHandler)
        self.assertEqual(method_name, "test_method")
        self.assertIsNone(condition)
        self.assertEqual(priority, Priority.NORMAL)

    def test_register_trigger_with_condition(self):
        """Test trigger registration with condition."""

        class TestHandler:
            def test_method(self):
                pass

        condition = IsEqual("status", "active")

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=condition,
            priority=Priority.HIGH,
        )

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 1)

        handler_cls, method_name, condition, priority = triggers[0]
        self.assertEqual(condition, condition)
        self.assertEqual(priority, Priority.HIGH)

    def test_register_trigger_multiple_triggers(self):
        """Test registering multiple triggers for the same model/event."""

        class Handler1:
            def method1(self):
                pass

        class Handler2:
            def method2(self):
                pass

        # Register first trigger
        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=Handler1,
            method_name="method1",
            condition=None,
            priority=Priority.LOW,
        )

        # Register second trigger
        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=Handler2,
            method_name="method2",
            condition=None,
            priority=Priority.HIGH,
        )

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 2)

        # Triggers should be sorted by priority
        priorities = [trigger[3] for trigger in triggers]
        self.assertEqual(priorities, [Priority.HIGH, Priority.LOW])

    def test_register_trigger_different_models(self):
        """Test registering triggers for different models."""

        class TestHandler:
            def test_method(self):
                pass

        # Register trigger for TriggerModel
        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Register trigger for User
        register_trigger(
            model=UserModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Check TriggerModel triggers
        test_model_triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(test_model_triggers), 1)

        # Check User triggers
        user_triggers = get_triggers(UserModel, BEFORE_CREATE)
        self.assertEqual(len(user_triggers), 1)

        # Check that they're separate
        # The triggers should be stored separately in the registry
        from django_bulk_triggers.registry import list_all_triggers
        all_triggers = list_all_triggers()
        
        # Check that TriggerModel and User have separate entries
        self.assertIn((TriggerModel, BEFORE_CREATE), all_triggers)
        self.assertIn((UserModel, BEFORE_CREATE), all_triggers)
        
        # Verify they have different keys in the registry
        test_model_key = (TriggerModel, BEFORE_CREATE)
        user_key = (UserModel, BEFORE_CREATE)
        self.assertNotEqual(test_model_key, user_key)

    def test_register_trigger_different_events(self):
        """Test registering triggers for different events."""

        class TestHandler:
            def test_method(self):
                pass

        # Register trigger for BEFORE_CREATE
        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Register trigger for AFTER_CREATE
        register_trigger(
            model=TriggerModel,
            event=AFTER_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Check BEFORE_CREATE triggers
        before_triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(before_triggers), 1)

        # Check AFTER_CREATE triggers
        after_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        self.assertEqual(len(after_triggers), 1)

        # Check that they're separate
        # The triggers should be stored separately in the registry
        from django_bulk_triggers.registry import list_all_triggers
        all_triggers = list_all_triggers()
        
        # Check that BEFORE_CREATE and AFTER_CREATE have separate entries
        self.assertIn((TriggerModel, BEFORE_CREATE), all_triggers)
        self.assertIn((TriggerModel, AFTER_CREATE), all_triggers)
        
        # Verify they have different keys in the registry
        before_key = (TriggerModel, BEFORE_CREATE)
        after_key = (TriggerModel, AFTER_CREATE)
        self.assertNotEqual(before_key, after_key)

    def test_register_trigger_priority_sorting(self):
        """Test that triggers are sorted by priority."""

        class Handler1:
            def method1(self):
                pass

        class Handler2:
            def method2(self):
                pass

        class Handler3:
            def method3(self):
                pass

        # Register triggers in random priority order
        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=Handler2,
            method_name="method2",
            condition=None,
            priority=Priority.NORMAL,
        )

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=Handler1,
            method_name="method1",
            condition=None,
            priority=Priority.LOW,
        )

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=Handler3,
            method_name="method3",
            condition=None,
            priority=Priority.HIGH,
        )

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 3)

        # Check priority order (high priority first - lower numbers)
        priorities = [trigger[3] for trigger in triggers]
        self.assertEqual(priorities, [Priority.HIGH, Priority.NORMAL, Priority.LOW])

        # Check handler order matches priority order
        handlers = [trigger[0] for trigger in triggers]
        self.assertEqual(handlers, [Handler3, Handler2, Handler1])


class TestGetTriggers(TestCase):
    """Test the get_triggers function."""

    def setUp(self):
        # Clear any existing triggers before each test
        from django_bulk_triggers.registry import _triggers

        _triggers.clear()

    def test_get_triggers_empty(self):
        """Test getting triggers when none are registered."""
        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(triggers, [])

    def test_get_triggers_existing(self):
        """Test getting existing triggers."""

        class TestHandler:
            def test_method(self):
                pass

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 1)

        handler_cls, method_name, condition, priority = triggers[0]
        self.assertEqual(handler_cls, TestHandler)
        self.assertEqual(method_name, "test_method")

    def test_get_triggers_wrong_event(self):
        """Test getting triggers for non-existent event."""

        class TestHandler:
            def test_method(self):
                pass

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Try to get triggers for different event
        triggers = get_triggers(TriggerModel, AFTER_CREATE)
        self.assertEqual(triggers, [])

    def test_get_triggers_wrong_model(self):
        """Test getting triggers for non-existent model."""

        class TestHandler:
            def test_method(self):
                pass

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Try to get triggers for different model
        triggers = get_triggers(UserModel, BEFORE_CREATE)
        self.assertEqual(triggers, [])

    def test_get_triggers_all_events(self):
        """Test getting triggers for all event types."""
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

        # Register triggers for all events
        for event in events:
            register_trigger(
                model=TriggerModel,
                event=event,
                handler_cls=TestHandler,
                method_name="test_method",
                condition=None,
                priority=Priority.NORMAL,
            )

        # Check that triggers exist for all events
        for event in events:
            triggers = get_triggers(TriggerModel, event)
            self.assertEqual(len(triggers), 1)

    def test_get_triggers_logging(self):
        """Test that get_triggers logs appropriately."""
        with patch("django_bulk_triggers.registry.logger") as mock_logger:
            # Test with no triggers
            get_triggers(TriggerModel, BEFORE_CREATE)
            mock_logger.debug.assert_called()

            # Test with triggers
            class TestHandler:
                def test_method(self):
                    pass

            register_trigger(
                model=TriggerModel,
                event=BEFORE_CREATE,
                handler_cls=TestHandler,
                method_name="test_method",
                condition=None,
                priority=Priority.NORMAL,
            )

            get_triggers(TriggerModel, BEFORE_CREATE)
            # Should log when triggers are found
            mock_logger.debug.assert_called()


class TestListAllTriggers(TestCase):
    """Test the list_all_triggers function."""

    def setUp(self):
        # Clear any existing triggers before each test
        from django_bulk_triggers.registry import _triggers

        _triggers.clear()

    def test_list_all_triggers_empty(self):
        """Test listing triggers when none are registered."""
        triggers = list_all_triggers()
        self.assertEqual(triggers, {})

    def test_list_all_triggers_with_triggers(self):
        """Test listing triggers when triggers are registered."""

        class TestHandler:
            def test_method(self):
                pass

        # Register some triggers
        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        register_trigger(
            model=UserModel,
            event=AFTER_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        triggers = list_all_triggers()

        # Should have entries for both models
        self.assertIn((TriggerModel, BEFORE_CREATE), triggers)
        self.assertIn((UserModel, AFTER_CREATE), triggers)

        # Check the content
        test_model_triggers = triggers[(TriggerModel, BEFORE_CREATE)]
        self.assertEqual(len(test_model_triggers), 1)

        user_triggers = triggers[(UserModel, AFTER_CREATE)]
        self.assertEqual(len(user_triggers), 1)

    def test_list_all_triggers_structure(self):
        """Test the structure of returned triggers."""

        class TestHandler:
            def test_method(self):
                pass

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        triggers = list_all_triggers()

        # Check that the structure is correct
        self.assertIsInstance(triggers, dict)

        key = (TriggerModel, BEFORE_CREATE)
        self.assertIn(key, triggers)

        trigger_list = triggers[key]
        self.assertIsInstance(trigger_list, list)
        self.assertEqual(len(trigger_list), 1)

        trigger_tuple = trigger_list[0]
        self.assertIsInstance(trigger_tuple, tuple)
        self.assertEqual(
            len(trigger_tuple), 4
        )  # (handler_cls, method_name, condition, priority)


class TestRegistryIntegration(TestCase):
    """Integration tests for the registry."""

    def setUp(self):
        # Clear any existing triggers before each test
        from django_bulk_triggers.registry import _triggers

        _triggers.clear()

    def test_registry_with_real_triggers(self):
        """Test registry with real trigger classes."""
        from django_bulk_triggers import TriggerClass
        from django_bulk_triggers.decorators import trigger

        class TestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_after_create(self, new_records, old_records=None, **kwargs):
                pass

        # Check that triggers were registered
        before_triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(before_triggers), 1)

        after_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        self.assertEqual(len(after_triggers), 1)

        # Check trigger details
        handler_cls, method_name, condition, priority = before_triggers[0]
        self.assertEqual(handler_cls, TestTrigger)
        self.assertEqual(method_name, "on_before_create")
        self.assertIsNone(condition)
        self.assertEqual(priority, Priority.NORMAL)

    def test_registry_with_conditions(self):
        """Test registry with conditional triggers."""
        from django_bulk_triggers import TriggerClass
        from django_bulk_triggers.decorators import trigger
        from django_bulk_triggers.conditions import IsEqual

        class ConditionalTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel, condition=IsEqual("status", "active"))
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 1)

        handler_cls, method_name, condition, priority = triggers[0]
        self.assertIsInstance(condition, IsEqual)
        self.assertEqual(condition.field, "status")
        self.assertEqual(condition.value, "active")

    def test_registry_with_priorities(self):
        """Test registry with different priorities."""
        from django_bulk_triggers import TriggerClass
        from django_bulk_triggers.decorators import trigger
        from django_bulk_triggers.enums import Priority

        class HighPriorityTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel, priority=Priority.HIGH)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

        class LowPriorityTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel, priority=Priority.LOW)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                pass

        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 2)

        # Check priority order
        priorities = [trigger[3] for trigger in triggers]
        self.assertEqual(priorities, [Priority.HIGH, Priority.LOW])

    def test_registry_cleanup(self):
        """Test that registry can be cleaned up."""

        class TestHandler:
            def test_method(self):
                pass

        register_trigger(
            model=TriggerModel,
            event=BEFORE_CREATE,
            handler_cls=TestHandler,
            method_name="test_method",
            condition=None,
            priority=Priority.NORMAL,
        )

        # Verify trigger is registered
        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 1)

        # Clear registry
        from django_bulk_triggers.registry import _triggers

        _triggers.clear()

        # Verify trigger is gone
        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 0)
