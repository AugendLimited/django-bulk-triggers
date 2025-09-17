"""
Tests for trigger conditions.
"""

from unittest.mock import Mock

import pytest
from django.test import TestCase
from django_bulk_signals.conditions import (
    ChangesTo,
    CustomCondition,
    HasChanged,
    IsEqual,
    IsNotEqual,
    TriggerCondition,
    WasEqual,
    changes_to,
    has_changed,
    has_not_changed,
    is_equal,
    is_not_equal,
)


class TestTriggerConditions(TestCase):
    """Test trigger conditions."""

    def setUp(self):
        """Set up test data."""
        self.instance = Mock()
        self.original = Mock()

        # Set up mock attributes
        self.instance.field1 = "new_value"
        self.instance.field2 = "same_value"
        self.instance.field3 = 42

        self.original.field1 = "old_value"
        self.original.field2 = "same_value"
        self.original.field3 = 24

    def test_has_changed_true(self):
        """Test HasChanged condition when field has changed."""
        condition = HasChanged("field1")
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)

    def test_has_changed_false(self):
        """Test HasChanged condition when field has not changed."""
        condition = HasChanged("field2")
        result = condition.check(self.instance, self.original)
        self.assertFalse(result)

    def test_has_changed_no_original(self):
        """Test HasChanged condition when no original instance."""
        condition = HasChanged("field1")
        result = condition.check(self.instance, None)
        self.assertFalse(result)

    def test_has_changed_inverted(self):
        """Test HasChanged condition with has_changed=False."""
        condition = HasChanged("field2", has_changed=False)
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)  # Field has not changed

    def test_is_equal_true(self):
        """Test IsEqual condition when field equals value."""
        condition = IsEqual("field1", "new_value")
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)

    def test_is_equal_false(self):
        """Test IsEqual condition when field does not equal value."""
        condition = IsEqual("field1", "different_value")
        result = condition.check(self.instance, self.original)
        self.assertFalse(result)

    def test_is_equal_only_on_change(self):
        """Test IsEqual condition with only_on_change=True."""
        condition = IsEqual("field1", "new_value", only_on_change=True)
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)  # Changed from 'old_value' to 'new_value'

        # Test when field was already the target value
        self.original.field1 = "new_value"
        result = condition.check(self.instance, self.original)
        self.assertFalse(result)  # No change

    def test_is_not_equal_true(self):
        """Test IsNotEqual condition when field does not equal value."""
        condition = IsNotEqual("field1", "different_value")
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)

    def test_is_not_equal_false(self):
        """Test IsNotEqual condition when field equals value."""
        condition = IsNotEqual("field1", "new_value")
        result = condition.check(self.instance, self.original)
        self.assertFalse(result)

    def test_was_equal_true(self):
        """Test WasEqual condition when original field equals value."""
        condition = WasEqual("field1", "old_value")
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)

    def test_was_equal_false(self):
        """Test WasEqual condition when original field does not equal value."""
        condition = WasEqual("field1", "different_value")
        result = condition.check(self.instance, self.original)
        self.assertFalse(result)

    def test_was_equal_no_original(self):
        """Test WasEqual condition when no original instance."""
        condition = WasEqual("field1", "old_value")
        result = condition.check(self.instance, None)
        self.assertFalse(result)

    def test_changes_to_true(self):
        """Test ChangesTo condition when field changes to target value."""
        condition = ChangesTo("field1", "new_value")
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)  # Changed from 'old_value' to 'new_value'

    def test_changes_to_false(self):
        """Test ChangesTo condition when field does not change to target value."""
        condition = ChangesTo("field1", "different_value")
        result = condition.check(self.instance, self.original)
        self.assertFalse(result)

    def test_changes_to_no_change(self):
        """Test ChangesTo condition when field was already target value."""
        self.original.field1 = "new_value"
        condition = ChangesTo("field1", "new_value")
        result = condition.check(self.instance, self.original)
        self.assertFalse(result)  # No change

    def test_custom_condition(self):
        """Test CustomCondition with a callable."""

        def custom_check(instance, original):
            return instance.field3 > original.field3

        condition = CustomCondition(custom_check)
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)  # 42 > 24

    def test_condition_callable(self):
        """Test that conditions can be called directly."""
        condition = HasChanged("field1")
        result = condition(self.instance, self.original)
        self.assertTrue(result)

    def test_convenience_functions(self):
        """Test convenience functions for creating conditions."""
        # Test has_changed
        condition = has_changed("field1")
        self.assertIsInstance(condition, HasChanged)
        self.assertEqual(condition.field, "field1")
        self.assertTrue(condition.has_changed)

        # Test has_not_changed
        condition = has_not_changed("field1")
        self.assertIsInstance(condition, HasChanged)
        self.assertEqual(condition.field, "field1")
        self.assertFalse(condition.has_changed)

        # Test is_equal
        condition = is_equal("field1", "value")
        self.assertIsInstance(condition, IsEqual)
        self.assertEqual(condition.field, "field1")
        self.assertEqual(condition.value, "value")

        # Test is_not_equal
        condition = is_not_equal("field1", "value")
        self.assertIsInstance(condition, IsNotEqual)
        self.assertEqual(condition.field, "field1")
        self.assertEqual(condition.value, "value")

        # Test changes_to
        condition = changes_to("field1", "value")
        self.assertIsInstance(condition, ChangesTo)
        self.assertEqual(condition.field, "field1")
        self.assertEqual(condition.value, "value")

    def test_condition_with_missing_field(self):
        """Test conditions with missing fields."""
        # Create real objects without the missing field
        from types import SimpleNamespace

        instance = SimpleNamespace(field1="value1")
        original = SimpleNamespace(field1="value2")

        condition = HasChanged("missing_field")
        result = condition.check(instance, original)
        self.assertFalse(result)  # Should handle missing fields gracefully

    def test_condition_with_none_values(self):
        """Test conditions with None values."""
        self.instance.field1 = None
        self.original.field1 = "old_value"

        condition = HasChanged("field1")
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)  # None != 'old_value'

        condition = IsEqual("field1", None)
        result = condition.check(self.instance, self.original)
        self.assertTrue(result)  # None == None
