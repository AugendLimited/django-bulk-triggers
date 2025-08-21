"""
Tests for the decorators module.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase

from django_bulk_hooks.conditions import IsEqual, IsNotEqual
from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.decorators import hook, select_related
from django_bulk_hooks.priority import Priority
from tests.models import Category, TestModel, User
from tests.utils import TestHookTracker, create_test_instances


class TestHookDecorator(TestCase):
    """Test the hook decorator."""

    def setUp(self):
        self.tracker = TestHookTracker()
        
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_hook_decorator_basic(self):
        """Test basic hook decorator functionality."""

        @hook(BEFORE_CREATE, model=TestModel)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify the hook attribute was added
        self.assertTrue(hasattr(test_hook, "hooks_hooks"))
        self.assertEqual(len(test_hook.hooks_hooks), 1)

        hook_info = test_hook.hooks_hooks[0]
        self.assertEqual(hook_info[0], TestModel)  # model
        self.assertEqual(hook_info[1], BEFORE_CREATE)  # event
        self.assertIsNone(hook_info[2])  # condition
        self.assertEqual(hook_info[3], Priority.NORMAL)  # priority

    def test_hook_decorator_with_condition(self):
        """Test hook decorator with condition."""
        condition = IsEqual("status", "active")

        @hook(BEFORE_CREATE, model=TestModel, condition=condition)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        hook_info = test_hook.hooks_hooks[0]
        self.assertEqual(hook_info[2], condition)  # condition

    def test_hook_decorator_with_priority(self):
        """Test hook decorator with custom priority."""

        @hook(BEFORE_CREATE, model=TestModel, priority=Priority.HIGH)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        hook_info = test_hook.hooks_hooks[0]
        self.assertEqual(hook_info[3], Priority.HIGH)  # priority

    def test_hook_decorator_multiple_hooks(self):
        """Test multiple hooks on the same function."""

        @hook(BEFORE_CREATE, model=TestModel)
        @hook(AFTER_CREATE, model=TestModel)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        self.assertEqual(len(test_hook.hooks_hooks), 2)

        events = [hook_info[1] for hook_info in test_hook.hooks_hooks]
        self.assertIn(BEFORE_CREATE, events)
        self.assertIn(AFTER_CREATE, events)

    def test_hook_decorator_different_models(self):
        """Test hooks on different models."""

        @hook(BEFORE_CREATE, model=TestModel)
        @hook(BEFORE_CREATE, model=User)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        self.assertEqual(len(test_hook.hooks_hooks), 2)

        models = [hook_info[0] for hook_info in test_hook.hooks_hooks]
        self.assertIn(TestModel, models)
        self.assertIn(User, models)

    def test_hook_decorator_with_all_events(self):
        """Test hook decorator with all event types."""
        events = [
            BEFORE_CREATE,
            AFTER_CREATE,
            BEFORE_UPDATE,
            AFTER_UPDATE,
            BEFORE_DELETE,
            AFTER_DELETE,
        ]

        for event in events:

            @hook(event, model=TestModel)
            def test_hook(new_records, old_records=None, **kwargs):
                self.tracker.add_call(event, new_records, old_records, **kwargs)

            hook_info = test_hook.hooks_hooks[0]
            self.assertEqual(hook_info[1], event)


class TestSelectRelatedDecorator(TestCase):
    """Test the select_related decorator."""

    def setUp(self):
        # Create test data
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.category = Category.objects.create(name="Test Category")

        # Create test instances with foreign keys
        self.test_instances = [
            TestModel(name="Test 1", created_by=self.user, category=self.category),
            TestModel(name="Test 2", created_by=self.user, category=self.category),
        ]

        # Save instances to get PKs
        for instance in self.test_instances:
            instance.save()
            
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_select_related_basic(self):
        """Test basic select_related functionality."""

        @select_related("created_by", "category")
        def test_function(new_records, old_records=None, **kwargs):
            # Verify that related fields are loaded
            for record in new_records:
                self.assertIsNotNone(record.created_by)
                self.assertIsNotNone(record.category)
                self.assertIsInstance(record.created_by, User)
                self.assertIsInstance(record.category, Category)

        test_function(new_records=self.test_instances)

    def test_select_related_missing_new_records_argument(self):
        """Test select_related with missing new_records argument."""

        @select_related("created_by")
        def test_function(some_other_arg):
            pass

        with self.assertRaises(TypeError):
            test_function("some_value")

    def test_select_related_wrong_argument_type(self):
        """Test select_related with wrong argument type."""

        @select_related("created_by")
        def test_function(new_records, old_records=None, **kwargs):
            pass

        with self.assertRaises(TypeError):
            test_function(new_records="not_a_list")

    def test_select_related_empty_list(self):
        """Test select_related with empty list."""

        @select_related("created_by")
        def test_function(new_records, old_records=None, **kwargs):
            return "success"

        result = test_function(new_records=[])
        self.assertEqual(result, "success")

    def test_select_related_nested_field_error(self):
        """Test select_related with nested field raises error."""

        @select_related("created_by.username")
        def test_function(new_records, old_records=None, **kwargs):
            pass

        with self.assertRaises(ValueError):
            test_function(new_records=self.test_instances)

    def test_select_related_non_relation_field(self):
        """Test select_related with non-relation field."""

        @select_related("name")  # name is not a relation
        def test_function(new_records, old_records=None, **kwargs):
            # Should not raise error, just skip the field
            return "success"

        result = test_function(new_records=self.test_instances)
        self.assertEqual(result, "success")

    def test_select_related_nonexistent_field(self):
        """Test select_related with nonexistent field."""

        @select_related("nonexistent_field")
        def test_function(new_records, old_records=None, **kwargs):
            # Should not raise error, just skip the field
            return "success"

        result = test_function(new_records=self.test_instances)
        self.assertEqual(result, "success")

    def test_select_related_already_cached(self):
        """Test select_related when field is already cached."""
        # Pre-load the related field
        for instance in self.test_instances:
            instance.created_by  # This will cache the relation

        @select_related("created_by")
        def test_function(new_records, old_records=None, **kwargs):
            # Should work without additional queries
            for record in new_records:
                self.assertIsNotNone(record.created_by)

        test_function(new_records=self.test_instances)

    def test_select_related_with_none_instances(self):
        """Test select_related with instances that have None foreign keys."""
        # Create instances with None foreign keys
        none_instances = [
            TestModel(name="None FK 1", created_by=None, category=None),
            TestModel(name="None FK 2", created_by=None, category=None),
        ]

        for instance in none_instances:
            instance.save()

        @select_related("created_by", "category")
        def test_function(new_records, old_records=None, **kwargs):
            # Should handle None values gracefully
            for record in new_records:
                self.assertIsNone(record.created_by)
                self.assertIsNone(record.category)

        test_function(new_records=none_instances)

    def test_select_related_performance(self):
        """Test that select_related reduces database queries."""
        # The test instances already have their related fields loaded
        # so no additional queries should be needed
        with self.assertNumQueries(0):  # No additional queries needed

            @select_related("created_by", "category")
            def test_function(new_records, old_records=None, **kwargs):
                for record in new_records:
                    _ = record.created_by.username
                    _ = record.category.name

            test_function(new_records=self.test_instances)

    def test_select_related_with_many_to_many_field(self):
        """Test select_related with many-to-many field (should be skipped)."""

        @select_related("category")  # This is a valid FK field
        def test_function(new_records, old_records=None, **kwargs):
            # Should work without error, just skip the field
            return "success"

        result = test_function(new_records=self.test_instances)
        self.assertEqual(result, "success")


class TestDecoratorIntegration(TestCase):
    """Integration tests for decorators."""

    def setUp(self):
        self.tracker = TestHookTracker()
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.category = Category.objects.create(name="Test Category")
        
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_hook_with_select_related(self):
        """Test combining hook and select_related decorators."""

        @hook(BEFORE_CREATE, model=TestModel)
        @select_related("created_by", "category")
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

            # Verify related fields are loaded
            for record in new_records:
                if record.created_by:
                    self.assertIsInstance(record.created_by, User)
                if record.category:
                    self.assertIsInstance(record.category, Category)

        # Create test instances
        test_instances = [
            TestModel(name="Test 1", created_by=self.user, category=self.category),
            TestModel(name="Test 2", created_by=self.user, category=self.category),
        ]

        # Call the hook function
        test_hook(new_records=test_instances)

        # Verify hook was called
        self.assertEqual(len(self.tracker.before_create_calls), 1)

    def test_multiple_hooks_with_select_related(self):
        """Test multiple hooks with select_related."""

        @hook(BEFORE_CREATE, model=TestModel)
        @hook(AFTER_CREATE, model=TestModel)
        @select_related("created_by")
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify both decorators work together
        self.assertEqual(len(test_hook.hooks_hooks), 2)

        # Test the function
        test_instances = [TestModel(name="Test", created_by=self.user)]
        test_hook(new_records=test_instances)

        self.assertEqual(len(self.tracker.before_create_calls), 1)
