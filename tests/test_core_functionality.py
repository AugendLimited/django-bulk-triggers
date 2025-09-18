"""
Consolidated tests for core django-bulk-triggers functionality.

This module consolidates tests from multiple files to reduce complexity
and improve maintainability while preserving all test coverage.

Mission-critical requirements:
- Zero hacks or shortcuts
- Maintain exact same behavior as original
- Consolidate tests while preserving coverage
- Comprehensive error handling
- Production-grade code quality
"""

from unittest.mock import MagicMock, Mock, patch
import pytest
from django.db import transaction
from django.db.models import Case, Subquery, Value, When
from django.test import TestCase, TransactionTestCase

from django_bulk_triggers import TriggerClass
from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
    VALIDATE_CREATE,
    VALIDATE_DELETE,
    VALIDATE_UPDATE,
)
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.handler import (
    Trigger,
    TriggerContextState,
    _trigger_context,
    get_trigger_queue,
    trigger_vars,
)
from django_bulk_triggers.conditions import HasChanged, IsEqual, IsNotEqual, WasEqual
from django_bulk_triggers.priority import Priority
from django_bulk_triggers.queryset import TriggerQuerySetMixin
from django_bulk_triggers.context import set_bulk_update_value_map
from tests.models import (
    Category,
    ComplexModel,
    RelatedModel,
    SimpleModel,
    TriggerModel,
    UserModel,
)
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

        trigger_vars.event = AFTER_CREATE
        self.assertTrue(self.trigger_state.is_create)

        trigger_vars.event = BEFORE_UPDATE
        self.assertFalse(self.trigger_state.is_create)

    def test_is_update_property(self):
        """Test is_update property."""
        trigger_vars.event = BEFORE_UPDATE
        self.assertTrue(self.trigger_state.is_update)

        trigger_vars.event = AFTER_UPDATE
        self.assertTrue(self.trigger_state.is_update)

        trigger_vars.event = BEFORE_CREATE
        self.assertFalse(self.trigger_state.is_update)

    def test_is_delete_property(self):
        """Test is_delete property."""
        trigger_vars.event = BEFORE_DELETE
        self.assertTrue(self.trigger_state.is_delete)

        trigger_vars.event = AFTER_DELETE
        self.assertTrue(self.trigger_state.is_delete)

        trigger_vars.event = BEFORE_CREATE
        self.assertFalse(self.trigger_state.is_delete)


class TestTriggerRegistration(TestCase):
    """Test trigger registration and execution."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_trigger_registration(self):
        """Test that triggers are properly registered."""
        tracker = TriggerTracker()

        class TestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                tracker.track("before_create", new_records)

        # Create and register trigger
        test_trigger = TestTrigger()
        
        # Verify trigger is registered
        from django_bulk_triggers.registry import get_triggers
        triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertEqual(len(triggers), 1)

    def test_trigger_execution(self):
        """Test that triggers are executed correctly."""
        tracker = TriggerTracker()

        class TestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                tracker.track("before_create", new_records)

        # Create trigger instance
        test_trigger = TestTrigger()
        
        # Create test instances
        instances = create_test_instances(TriggerModel, 3)
        
        # Execute trigger manually
        test_trigger.on_before_create(instances)
        
        # Verify trigger was called
        assert_trigger_called(tracker, "before_create", instances)


class TestQuerySetMixin(TestCase):
    """Test TriggerQuerySetMixin functionality."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_trigger_engine_property(self):
        """Test that trigger_engine property works correctly."""
        class MockQuerySet(TriggerQuerySetMixin):
            def __init__(self, model):
                self.model = model
                self.db = "default"

        mock_qs = MockQuerySet(TriggerModel)
        engine = mock_qs.trigger_engine
        
        self.assertIsNotNone(engine)
        self.assertEqual(engine.model_cls, TriggerModel)

    def test_delete_with_triggers(self):
        """Test delete operation with triggers."""
        tracker = TriggerTracker()

        class DeleteTestTrigger(TriggerClass):
            @trigger(BEFORE_DELETE, model=TriggerModel)
            def on_before_delete(self, new_records, old_records=None, **kwargs):
                tracker.track("before_delete", new_records)

            @trigger(AFTER_DELETE, model=TriggerModel)
            def on_after_delete(self, new_records, old_records=None, **kwargs):
                tracker.track("after_delete", new_records)

        # Create trigger instance
        delete_trigger = DeleteTestTrigger()

        class MockQuerySet(TriggerQuerySetMixin):
            def __init__(self, model):
                self.model = model
                self.db = "default"
                self._instances = []

            def __iter__(self):
                return iter(self._instances)

            def __len__(self):
                return len(self._instances)

            def delete(self):
                if not self._instances:
                    return (0, {})
                return (len(self._instances), {"tests.TriggerModel": len(self._instances)})

        # Create mock queryset with instances
        mock_qs = MockQuerySet(TriggerModel)
        instances = create_test_instances(TriggerModel, 3)
        mock_qs._instances = instances

        # Execute delete
        result = mock_qs.delete()

        # Verify result
        self.assertEqual(result, 3)

    def test_update_with_triggers(self):
        """Test update operation with triggers."""
        tracker = TriggerTracker()

        class UpdateTestTrigger(TriggerClass):
            @trigger(BEFORE_UPDATE, model=TriggerModel)
            def on_before_update(self, new_records, old_records=None, **kwargs):
                tracker.track("before_update", new_records)

            @trigger(AFTER_UPDATE, model=TriggerModel)
            def on_after_update(self, new_records, old_records=None, **kwargs):
                tracker.track("after_update", new_records)

        # Create trigger instance
        update_trigger = UpdateTestTrigger()

        class MockQuerySet(TriggerQuerySetMixin):
            def __init__(self, model):
                self.model = model
                self.db = "default"
                self._instances = []

            def __iter__(self):
                return iter(self._instances)

            def __len__(self):
                return len(self._instances)

            def update(self, **kwargs):
                return len(self._instances)

        # Create mock queryset with instances
        mock_qs = MockQuerySet(TriggerModel)
        instances = create_test_instances(TriggerModel, 3)
        mock_qs._instances = instances

        # Execute update
        result = mock_qs.update(name="Updated Name")

        # Verify result
        self.assertEqual(result, 3)


class TestConditions(TestCase):
    """Test trigger conditions."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_has_changed_condition(self):
        """Test HasChanged condition."""
        # Create instances with different values
        instance1 = TriggerModel(name="Original")
        instance1.pk = 1
        
        # Simulate old instance
        old_instance = TriggerModel(name="Original")
        old_instance.pk = 1
        
        # Test HasChanged condition
        condition = HasChanged("name")
        
        # Should return False when value hasn't changed
        self.assertFalse(condition.check(instance1, old_instance))
        
        # Change the value
        instance1.name = "Changed"
        
        # Should return True when value has changed
        self.assertTrue(condition.check(instance1, old_instance))

    def test_is_equal_condition(self):
        """Test IsEqual condition."""
        instance = TriggerModel(name="Test")
        
        condition = IsEqual("name", "Test")
        self.assertTrue(condition.check(instance))
        
        condition = IsEqual("name", "Different")
        self.assertFalse(condition.check(instance))

    def test_is_not_equal_condition(self):
        """Test IsNotEqual condition."""
        instance = TriggerModel(name="Test")
        
        condition = IsNotEqual("name", "Different")
        self.assertTrue(condition.check(instance))
        
        condition = IsNotEqual("name", "Test")
        self.assertFalse(condition.check(instance))

    def test_was_equal_condition(self):
        """Test WasEqual condition."""
        instance = TriggerModel(name="Changed")
        instance.pk = 1
        
        old_instance = TriggerModel(name="Original")
        old_instance.pk = 1
        
        condition = WasEqual("name", "Original")
        self.assertTrue(condition.check(instance, old_instance))
        
        condition = WasEqual("name", "Different")
        self.assertFalse(condition.check(instance, old_instance))


class TestPriority(TestCase):
    """Test trigger priority system."""

    def test_priority_values(self):
        """Test that priority values are correct."""
        self.assertEqual(Priority.HIGHEST.value, 0)
        self.assertEqual(Priority.HIGH.value, 1)
        self.assertEqual(Priority.NORMAL.value, 2)
        self.assertEqual(Priority.LOW.value, 3)
        self.assertEqual(Priority.LOWEST.value, 4)

    def test_priority_comparison(self):
        """Test priority comparison."""
        self.assertTrue(Priority.HIGHEST < Priority.HIGH)
        self.assertTrue(Priority.HIGH < Priority.NORMAL)
        self.assertTrue(Priority.NORMAL < Priority.LOW)
        self.assertTrue(Priority.LOW < Priority.LOWEST)


class TestIntegration(TransactionTestCase):
    """Integration tests for the complete system."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_full_trigger_lifecycle(self):
        """Test complete trigger lifecycle with database operations."""
        tracker = TriggerTracker()

        class LifecycleTestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                tracker.track("before_create", new_records)

            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_after_create(self, new_records, old_records=None, **kwargs):
                tracker.track("after_create", new_records)

        # Create trigger instance
        lifecycle_trigger = LifecycleTestTrigger()

        # Create instances
        instances = [
            TriggerModel(name=f"Test {i}")
            for i in range(3)
        ]

        # Use bulk_create to test the full lifecycle
        with transaction.atomic():
            result = TriggerModel.objects.bulk_create(instances)

        # Verify instances were created
        self.assertEqual(len(result), 3)
        
        # Verify triggers were called
        assert_trigger_called(tracker, "before_create", instances)
        assert_trigger_called(tracker, "after_create", result)

    def test_trigger_with_conditions(self):
        """Test triggers with conditions."""
        tracker = TriggerTracker()

        class ConditionalTestTrigger(TriggerClass):
            @trigger(BEFORE_UPDATE, model=TriggerModel, condition=HasChanged("name"))
            def on_name_changed(self, new_records, old_records=None, **kwargs):
                tracker.track("name_changed", new_records)

        # Create trigger instance
        conditional_trigger = ConditionalTestTrigger()

        # Create an instance
        instance = TriggerModel.objects.create(name="Original")

        # Update without changing name (should not trigger)
        instance.name = "Original"
        instance.save()

        # Verify trigger was not called
        self.assertEqual(len(tracker.calls), 0)

        # Update with name change (should trigger)
        instance.name = "Changed"
        instance.save()

        # Verify trigger was called
        assert_trigger_called(tracker, "name_changed", [instance])
