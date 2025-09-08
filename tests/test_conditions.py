"""
Tests for the conditions module.
"""

from unittest.mock import Mock

import pytest
from django.test import TestCase

from django_bulk_triggers.conditions import (
    AndCondition,
    HasChanged,
    TriggerCondition,
    IsEqual,
    IsNotEqual,
    NotCondition,
    OrCondition,
    WasEqual,
    resolve_dotted_attr,
)
from tests.models import Category, TriggerModel, UserModel


class TestResolveDottedAttr(TestCase):
    """Test the resolve_dotted_attr function."""

    def setUp(self):
        self.user = UserModel(username="testuser", email="test@example.com")
        self.category = Category(name="Test Category", description="Test Description")
        self.test_model = TriggerModel(
            name="Test Model",
            value=42,
            status="active",
            created_by=self.user,
            category=self.category,
        )
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_resolve_simple_attr(self):
        """Test resolving a simple attribute."""
        result = resolve_dotted_attr(self.test_model, "name")
        self.assertEqual(result, "Test Model")

    def test_resolve_nested_attr(self):
        """Test resolving a nested attribute."""
        result = resolve_dotted_attr(self.test_model, "created_by.username")
        self.assertEqual(result, "testuser")

    def test_resolve_deep_nested_attr(self):
        """Test resolving a deeply nested attribute."""
        # Create a more complex structure
        self.user.profile = Mock()
        self.user.profile.settings = Mock()
        self.user.profile.settings.theme = "dark"

        result = resolve_dotted_attr(
            self.test_model, "created_by.profile.settings.theme"
        )
        self.assertEqual(result, "dark")

    def test_resolve_none_instance(self):
        """Test resolving attribute on None instance."""
        result = resolve_dotted_attr(None, "some.attr")
        self.assertIsNone(result)

    def test_resolve_missing_attr(self):
        """Test resolving a missing attribute."""
        result = resolve_dotted_attr(self.test_model, "nonexistent")
        self.assertIsNone(result)

    def test_resolve_missing_nested_attr(self):
        """Test resolving a missing nested attribute."""
        result = resolve_dotted_attr(self.test_model, "created_by.nonexistent")
        self.assertIsNone(result)

    def test_resolve_empty_path(self):
        """Test resolving with empty path."""
        result = resolve_dotted_attr(self.test_model, "")
        self.assertIsNone(result)


class TestTriggerCondition(TestCase):
    """Test the base TriggerCondition class."""

    def test_trigger_condition_abstract(self):
        """Test that TriggerCondition check method raises NotImplementedError."""
        condition = TriggerCondition()
        with self.assertRaises(NotImplementedError):
            condition.check(None)

    def test_trigger_condition_callable(self):
        """Test that TriggerCondition instances are callable."""

        class TestCondition(TriggerCondition):
            def check(self, instance, original_instance=None):
                return True

        condition = TestCondition()
        self.assertTrue(condition(None))


class TestIsEqual(TestCase):
    """Test the IsEqual condition."""

    def setUp(self):
        self.condition = IsEqual("status", "active")
        self.test_model = TriggerModel(name="Test", status="active")
        self.old_model = TriggerModel(name="Test", status="inactive")
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_is_equal_basic(self):
        """Test basic IsEqual functionality."""
        self.assertTrue(self.condition.check(self.test_model))

    def test_is_equal_false(self):
        """Test IsEqual when value doesn't match."""
        test_model = TriggerModel(name="Test", status="inactive")
        self.assertFalse(self.condition.check(test_model))

    def test_is_equal_with_original_instance(self):
        """Test IsEqual with original instance."""
        # Should work the same with or without original instance
        self.assertTrue(self.condition.check(self.test_model, self.old_model))

    def test_is_equal_only_on_change_true(self):
        """Test IsEqual with only_on_change=True when change occurs."""
        condition = IsEqual("status", "active", only_on_change=True)

        # Old status was not 'active', new status is 'active'
        self.assertTrue(condition.check(self.test_model, self.old_model))

    def test_is_equal_only_on_change_false(self):
        """Test IsEqual with only_on_change=True when no change occurs."""
        condition = IsEqual("status", "active", only_on_change=True)

        # Both old and new status are 'active'
        old_model = TriggerModel(name="Test", status="active")
        self.assertFalse(condition.check(self.test_model, old_model))

    def test_is_equal_only_on_change_no_original(self):
        """Test IsEqual with only_on_change=True but no original instance."""
        condition = IsEqual("status", "active", only_on_change=True)
        self.assertFalse(condition.check(self.test_model))

    def test_is_equal_nested_field(self):
        """Test IsEqual with nested field."""
        user = UserModel(username="testuser")
        test_model = TriggerModel(name="Test", created_by=user)
        condition = IsEqual("created_by.username", "testuser")

        self.assertTrue(condition.check(test_model))


class TestIsNotEqual(TestCase):
    """Test the IsNotEqual condition."""

    def setUp(self):
        self.condition = IsNotEqual("status", "inactive")
        self.test_model = TriggerModel(name="Test", status="active")
        self.old_model = TriggerModel(name="Test", status="inactive")
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_is_not_equal_basic(self):
        """Test basic IsNotEqual functionality."""
        self.assertTrue(self.condition.check(self.test_model))

    def test_is_not_equal_false(self):
        """Test IsNotEqual when value matches."""
        test_model = TriggerModel(name="Test", status="inactive")
        self.assertFalse(self.condition.check(test_model))

    def test_is_not_equal_only_on_change_true(self):
        """Test IsNotEqual with only_on_change=True when change occurs."""
        condition = IsNotEqual("status", "inactive", only_on_change=True)

        # Old status was 'inactive', new status is not 'inactive'
        self.assertTrue(condition.check(self.test_model, self.old_model))

    def test_is_not_equal_only_on_change_false(self):
        """Test IsNotEqual with only_on_change=True when no change occurs."""
        condition = IsNotEqual("status", "inactive", only_on_change=True)

        # Both old and new status are not 'inactive'
        old_model = TriggerModel(name="Test", status="active")
        self.assertFalse(condition.check(self.test_model, old_model))


class TestHasChanged(TestCase):
    """Test the HasChanged condition."""

    def setUp(self):
        self.condition = HasChanged("status")
        self.test_model = TriggerModel(name="Test", status="active")
        self.old_model = TriggerModel(name="Test", status="inactive")
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_has_changed_true(self):
        """Test HasChanged when field has changed."""
        self.assertTrue(self.condition.check(self.test_model, self.old_model))

    def test_has_changed_false(self):
        """Test HasChanged when field hasn't changed."""
        old_model = TriggerModel(name="Test", status="active")
        self.assertFalse(self.condition.check(self.test_model, old_model))

    def test_has_changed_no_original(self):
        """Test HasChanged with no original instance."""
        self.assertFalse(self.condition.check(self.test_model))

    def test_has_changed_inverted(self):
        """Test HasChanged with has_changed=False."""
        condition = HasChanged("status", has_changed=False)

        # Field has changed, but we're looking for unchanged
        self.assertFalse(condition.check(self.test_model, self.old_model))

        # Field hasn't changed, and we're looking for unchanged
        old_model = TriggerModel(name="Test", status="active")
        self.assertTrue(condition.check(self.test_model, old_model))

    def test_has_changed_nested_field(self):
        """Test HasChanged with nested field."""
        user1 = UserModel(username="user1")
        user2 = UserModel(username="user2")
        test_model = TriggerModel(name="Test", created_by=user1)
        old_model = TriggerModel(name="Test", created_by=user2)

        condition = HasChanged("created_by.username")
        self.assertTrue(condition.check(test_model, old_model))


class TestWasEqual(TestCase):
    """Test the WasEqual condition."""

    def setUp(self):
        self.condition = WasEqual("status", "inactive")
        self.test_model = TriggerModel(name="Test", status="active")
        self.old_model = TriggerModel(name="Test", status="inactive")
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_was_equal_true(self):
        """Test WasEqual when original value matches."""
        self.assertTrue(self.condition.check(self.test_model, self.old_model))

    def test_was_equal_false(self):
        """Test WasEqual when original value doesn't match."""
        old_model = TriggerModel(name="Test", status="active")
        self.assertFalse(self.condition.check(self.test_model, old_model))

    def test_was_equal_no_original(self):
        """Test WasEqual with no original instance."""
        self.assertFalse(self.condition.check(self.test_model))

    def test_was_equal_only_on_change_true(self):
        """Test WasEqual with only_on_change=True when change occurs."""
        condition = WasEqual("status", "inactive", only_on_change=True)

        # Old status was 'inactive', new status is not 'inactive'
        self.assertTrue(condition.check(self.test_model, self.old_model))

    def test_was_equal_only_on_change_false(self):
        """Test WasEqual with only_on_change=True when no change occurs."""
        condition = WasEqual("status", "inactive", only_on_change=True)

        # Both old and new status are 'inactive'
        old_model = TriggerModel(name="Test", status="inactive")
        test_model = TriggerModel(name="Test", status="inactive")
        self.assertFalse(condition.check(test_model, old_model))


class TestAndCondition(TestCase):
    """Test the AndCondition class."""

    def setUp(self):
        self.condition1 = IsEqual("status", "active")
        self.condition2 = IsEqual("value", 42)
        self.and_condition = self.condition1 & self.condition2

        self.test_model = TriggerModel(name="Test", status="active", value=42)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_and_condition_both_true(self):
        """Test AndCondition when both conditions are true."""
        self.assertTrue(self.and_condition.check(self.test_model))

    def test_and_condition_first_false(self):
        """Test AndCondition when first condition is false."""
        test_model = TriggerModel(name="Test", status="inactive", value=42)
        self.assertFalse(self.and_condition.check(test_model))

    def test_and_condition_second_false(self):
        """Test AndCondition when second condition is false."""
        test_model = TriggerModel(name="Test", status="active", value=0)
        self.assertFalse(self.and_condition.check(test_model))

    def test_and_condition_both_false(self):
        """Test AndCondition when both conditions are false."""
        test_model = TriggerModel(name="Test", status="inactive", value=0)
        self.assertFalse(self.and_condition.check(test_model))

    def test_and_condition_with_original_instance(self):
        """Test AndCondition with original instance."""
        old_model = TriggerModel(name="Test", status="inactive", value=0)
        self.assertTrue(self.and_condition.check(self.test_model, old_model))


class TestOrCondition(TestCase):
    """Test the OrCondition class."""

    def setUp(self):
        self.condition1 = IsEqual("status", "active")
        self.condition2 = IsEqual("value", 42)
        self.or_condition = self.condition1 | self.condition2
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_or_condition_both_true(self):
        """Test OrCondition when both conditions are true."""
        test_model = TriggerModel(name="Test", status="active", value=42)
        self.assertTrue(self.or_condition.check(test_model))

    def test_or_condition_first_true(self):
        """Test OrCondition when first condition is true."""
        test_model = TriggerModel(name="Test", status="active", value=0)
        self.assertTrue(self.or_condition.check(test_model))

    def test_or_condition_second_true(self):
        """Test OrCondition when second condition is true."""
        test_model = TriggerModel(name="Test", status="inactive", value=42)
        self.assertTrue(self.or_condition.check(test_model))

    def test_or_condition_both_false(self):
        """Test OrCondition when both conditions are false."""
        test_model = TriggerModel(name="Test", status="inactive", value=0)
        self.assertFalse(self.or_condition.check(test_model))


class TestNotCondition(TestCase):
    """Test the NotCondition class."""

    def setUp(self):
        self.condition = IsEqual("status", "active")
        self.not_condition = ~self.condition
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_not_condition_true_becomes_false(self):
        """Test NotCondition when original condition is true."""
        test_model = TriggerModel(name="Test", status="active")
        self.assertFalse(self.not_condition.check(test_model))

    def test_not_condition_false_becomes_true(self):
        """Test NotCondition when original condition is false."""
        test_model = TriggerModel(name="Test", status="inactive")
        self.assertTrue(self.not_condition.check(test_model))


class TestComplexConditions(TestCase):
    """Test complex condition combinations."""

    def setUp(self):
        self.test_model = TriggerModel(name="Test", status="active", value=42)
        self.old_model = TriggerModel(name="Test", status="inactive", value=0)
        
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_complex_and_or_combination(self):
        """Test complex AND/OR condition combination."""
        condition = IsEqual("status", "active") & (
            IsEqual("value", 42) | IsEqual("value", 100)
        )

        self.assertTrue(condition.check(self.test_model))

        # Test with different value
        test_model2 = TriggerModel(name="Test", status="active", value=100)
        self.assertTrue(condition.check(test_model2))

        # Test with wrong status
        test_model3 = TriggerModel(name="Test", status="inactive", value=42)
        self.assertFalse(condition.check(test_model3))

    def test_complex_not_combination(self):
        """Test complex NOT condition combination."""
        condition = ~(IsEqual("status", "inactive") | IsEqual("value", 0))

        self.assertTrue(condition.check(self.test_model))

        # Test with inactive status
        test_model2 = TriggerModel(name="Test", status="inactive", value=42)
        self.assertFalse(condition.check(test_model2))

    def test_complex_change_detection(self):
        """Test complex change detection conditions."""
        condition = (
            HasChanged("status")
            & WasEqual("status", "inactive")
            & IsEqual("status", "active")
        )

        self.assertTrue(condition.check(self.test_model, self.old_model))

        # Test without change
        old_model2 = TriggerModel(name="Test", status="active", value=0)
        self.assertFalse(condition.check(self.test_model, old_model2))


class TestConditionEdgeCases(TestCase):
    """Test edge cases for conditions."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_condition_with_none_values(self):
        """Test conditions with None values."""
        test_model = TriggerModel(name="Test", created_by=None)
        condition = IsEqual("created_by", None)

        self.assertTrue(condition.check(test_model))

    def test_condition_with_empty_string(self):
        """Test conditions with empty string values."""
        test_model = TriggerModel(name="", status="active")
        condition = IsEqual("name", "")

        self.assertTrue(condition.check(test_model))

    def test_condition_with_zero_values(self):
        """Test conditions with zero values."""
        test_model = TriggerModel(name="Test", value=0)
        condition = IsEqual("value", 0)

        self.assertTrue(condition.check(test_model))

    def test_condition_with_boolean_values(self):
        """Test conditions with boolean values."""
        test_model = TriggerModel(name="Test", is_active=True)
        condition = IsEqual("is_active", True)

        self.assertTrue(condition.check(test_model))
