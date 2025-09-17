"""
Tests for bulk trigger decorators.
"""

from unittest.mock import Mock, patch

import pytest
from django.test import TestCase
from django_bulk_signals.conditions import HasChanged, IsEqual
from django_bulk_signals.decorators import (
    after_create,
    after_delete,
    after_update,
    before_create,
    before_delete,
    before_update,
    bulk_trigger,
    process_instances,
)
from django_bulk_signals.signals import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)


class TestModel(Mock):
    """Mock model for testing."""

    pass


class TestBulkTriggerDecorators(TestCase):
    """Test bulk trigger decorators."""

    def setUp(self):
        """Set up test data."""
        self.instances = [
            Mock(field1="value1", field2="value2"),
            Mock(field1="value3", field2="value4"),
        ]
        self.originals = [
            Mock(field1="old1", field2="old2"),
            Mock(field1="old3", field2="old4"),
        ]

    def test_bulk_trigger_without_condition(self):
        """Test bulk_trigger decorator without condition."""
        handler_called = False

        @bulk_trigger(bulk_pre_create, TestModel)
        def test_handler(sender, instances, **kwargs):
            nonlocal handler_called
            handler_called = True
            self.assertEqual(sender, TestModel)
            self.assertEqual(instances, self.instances)

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances)

        self.assertTrue(handler_called)

    def test_bulk_trigger_with_condition(self):
        """Test bulk_trigger decorator with condition."""
        handler_called = False
        filtered_instances = []

        @bulk_trigger(bulk_pre_update, TestModel, condition=HasChanged("field1"))
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called, filtered_instances
            handler_called = True
            filtered_instances = instances

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        self.assertTrue(handler_called)
        # Should only include instances where field1 changed
        self.assertEqual(len(filtered_instances), 2)  # Both changed

    def test_bulk_trigger_condition_filters_instances(self):
        """Test that conditions filter instances correctly."""
        handler_called = False
        filtered_instances = []

        # Set up instances where only one has field1 changed
        self.instances[0].field1 = "new_value"  # Changed
        self.instances[1].field1 = "old3"  # Same as original

        @bulk_trigger(bulk_pre_update, TestModel, condition=HasChanged("field1"))
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called, filtered_instances
            handler_called = True
            filtered_instances = instances

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        self.assertTrue(handler_called)
        # Should only include the instance where field1 changed
        self.assertEqual(len(filtered_instances), 1)
        self.assertEqual(filtered_instances[0], self.instances[0])

    def test_bulk_trigger_no_matching_instances(self):
        """Test bulk_trigger when no instances match condition."""
        handler_called = False

        # Set up instances where field1 doesn't change
        self.instances[0].field1 = "old1"  # Same as original
        self.instances[1].field1 = "old3"  # Same as original

        @bulk_trigger(bulk_pre_update, TestModel, condition=HasChanged("field1"))
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        # Handler should not be called
        self.assertFalse(handler_called)

    def test_convenience_decorators(self):
        """Test convenience decorators for specific trigger types."""
        handlers_called = {
            "before_create": False,
            "after_create": False,
            "before_update": False,
            "after_update": False,
            "before_delete": False,
            "after_delete": False,
        }

        @before_create(TestModel)
        def before_create_handler(sender, instances, **kwargs):
            handlers_called["before_create"] = True

        @after_create(TestModel)
        def after_create_handler(sender, instances, **kwargs):
            handlers_called["after_create"] = True

        @before_update(TestModel)
        def before_update_handler(sender, instances, originals, **kwargs):
            handlers_called["before_update"] = True

        @after_update(TestModel)
        def after_update_handler(sender, instances, originals, **kwargs):
            handlers_called["after_update"] = True

        @before_delete(TestModel)
        def before_delete_handler(sender, instances, **kwargs):
            handlers_called["before_delete"] = True

        @after_delete(TestModel)
        def after_delete_handler(sender, instances, **kwargs):
            handlers_called["after_delete"] = True

        # Test that all handlers are properly registered
        self.assertTrue(callable(before_create_handler))
        self.assertTrue(callable(after_create_handler))
        self.assertTrue(callable(before_update_handler))
        self.assertTrue(callable(after_update_handler))
        self.assertTrue(callable(before_delete_handler))
        self.assertTrue(callable(after_delete_handler))

    def test_convenience_decorators_with_condition(self):
        """Test convenience decorators with conditions."""
        handler_called = False

        @before_update(TestModel, condition=HasChanged("field1"))
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        self.assertTrue(handler_called)

    def test_convenience_decorators_with_dispatch_uid(self):
        """Test convenience decorators with dispatch_uid."""
        handler_called = False

        @before_update(TestModel, dispatch_uid="test_handler")
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        self.assertTrue(handler_called)

    def test_process_instances_decorator(self):
        """Test process_instances decorator."""
        handler_called = False
        processed_instances = []

        @process_instances(HasChanged("field1"))
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called, processed_instances
            handler_called = True
            processed_instances = instances

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        self.assertTrue(handler_called)
        # Should process all instances since they all have field1 changed
        self.assertEqual(len(processed_instances), 2)

    def test_process_instances_without_condition(self):
        """Test process_instances decorator without condition."""
        handler_called = False
        processed_instances = []

        @process_instances()
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called, processed_instances
            handler_called = True
            processed_instances = instances

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        self.assertTrue(handler_called)
        # Should process all instances
        self.assertEqual(len(processed_instances), 2)

    def test_decorator_preserves_function_metadata(self):
        """Test that decorators preserve function metadata."""

        @bulk_trigger(bulk_pre_create, TestModel)
        def test_handler(sender, instances, **kwargs):
            """Test handler docstring."""
            pass

        # Check that metadata is preserved
        self.assertEqual(test_handler.__name__, "test_handler")
        self.assertEqual(test_handler.__doc__, "Test handler docstring.")

    def test_multiple_decorators(self):
        """Test using multiple decorators together."""
        handler_called = False

        @before_update(TestModel, condition=HasChanged("field1"))
        @process_instances(IsEqual("field2", "value2"))
        def test_handler(sender, instances, originals, **kwargs):
            nonlocal handler_called
            handler_called = True

        # Simulate signal firing
        test_handler(TestModel, instances=self.instances, originals=self.originals)

        self.assertTrue(handler_called)
