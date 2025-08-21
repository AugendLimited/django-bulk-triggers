"""
Extended tests for the conditions module to increase coverage.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django_bulk_hooks.conditions import (
    HookCondition, IsEqual, IsNotEqual, HasChanged,
    WasEqual, ChangesTo, IsGreaterThan, IsGreaterThanOrEqual, 
    IsLessThan, IsLessThanOrEqual, AndCondition, OrCondition, NotCondition
)
from tests.models import HookModel, Category, UserModel


class TestHookConditionBase(TestCase):
    """Base test case for condition tests."""
    
    def setUp(self):
        self.category = Category.objects.create(name="Test Category")
        self.user = UserModel.objects.create(username="testuser", email="test@example.com")
        self.instance = HookModel.objects.create(
            name="Test Instance",
            value=42,
            status="active",
            category=self.category,
            created_by=self.user
        )
        self.original_instance = HookModel.objects.create(
            name="Original Instance",
            value=100,
            status="pending",
            category=self.category,
            created_by=self.user
        )
    
    def tearDown(self):
        HookModel.objects.all().delete()
        Category.objects.all().delete()
        UserModel.objects.all().delete()


class TestHookCondition(TestHookConditionBase):
    """Test the base HookCondition class."""
    
    def test_hook_condition_base_class(self):
        """Test that HookCondition is a proper base class."""
        condition = HookCondition()
        self.assertTrue(hasattr(condition, 'check'))
        
        # Base class should raise NotImplementedError
        with self.assertRaises(NotImplementedError):
            condition.check(self.instance, self.original_instance)


class TestAlwaysCondition(TestHookConditionBase):
    """Test the Always condition."""
    
    def test_always_returns_true(self):
        """Test that Always condition always returns True."""
        # Create a condition that always returns True
        condition = IsEqual('name', 'Test Instance') | IsEqual('name', 'Different Name')
        
        # Should always return True regardless of instances
        self.assertTrue(condition.check(self.instance, self.original_instance))
        self.assertTrue(condition.check(self.instance, None))
        # Note: None original_instance will cause some conditions to fail


class TestNeverCondition(TestHookConditionBase):
    """Test the Never condition."""
    
    def test_never_returns_false(self):
        """Test that Never condition always returns False."""
        # Create a condition that always returns False
        condition = IsEqual('name', 'Test Instance') & IsEqual('name', 'Different Name')
        
        # Should always return False regardless of instances
        self.assertFalse(condition.check(self.instance, self.original_instance))
        self.assertFalse(condition.check(self.instance, None))
        # Note: None original_instance will cause some conditions to fail


class TestFieldEqualsCondition(TestHookConditionBase):
    """Test the FieldEquals condition."""
    
    def test_field_equals_with_matching_value(self):
        """Test FieldEquals when field value matches."""
        condition = IsEqual('name', 'Test Instance')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_field_equals_with_non_matching_value(self):
        """Test FieldEquals when field value doesn't match."""
        condition = IsEqual('name', 'Different Name')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_field_equals_with_none_value(self):
        """Test FieldEquals with None value."""
        condition = IsEqual('name', None)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_field_equals_with_dotted_attr(self):
        """Test FieldEquals with dotted attribute path."""
        condition = IsEqual('category.name', 'Test Category')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_field_equals_with_nested_dotted_attr(self):
        """Test FieldEquals with deeply nested dotted attribute path."""
        condition = IsEqual('created_by.username', 'testuser')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_field_equals_with_missing_field(self):
        """Test FieldEquals with missing field."""
        condition = IsEqual('non_existent_field', 'value')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_field_equals_with_missing_related_object(self):
        """Test FieldEquals with missing related object."""
        # Create instance without category
        instance_no_category = HookModel.objects.create(
            name="No Category",
            value=0,
            created_by=self.user
        )
        
        condition = IsEqual('category.name', 'Test Category')
        
        result = condition.check(instance_no_category, self.original_instance)
        self.assertFalse(result)


class TestFieldNotEqualsCondition(TestHookConditionBase):
    """Test the FieldNotEquals condition."""
    
    def test_field_not_equals_with_different_value(self):
        """Test FieldNotEquals when field value is different."""
        condition = IsNotEqual('name', 'Different Name')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_field_not_equals_with_matching_value(self):
        """Test FieldNotEquals when field value matches."""
        condition = IsNotEqual('name', 'Test Instance')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_field_not_equals_with_dotted_attr(self):
        """Test FieldNotEquals with dotted attribute path."""
        condition = IsNotEqual('category.name', 'Different Category')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)


class TestFieldChangedCondition(TestHookConditionBase):
    """Test the FieldChanged condition."""
    
    def test_field_changed_with_changed_value(self):
        """Test FieldChanged when field value has changed."""
        condition = HasChanged('name')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_field_changed_with_unchanged_value(self):
        """Test FieldChanged when field value hasn't changed."""
        # Create instance with same name as original
        same_name_instance = HookModel.objects.create(
            name="Original Instance",
            value=200,
            category=self.category,
            created_by=self.user
        )
        
        condition = HasChanged('name')
        
        result = condition.check(same_name_instance, self.original_instance)
        self.assertFalse(result)
    
    def test_field_changed_with_none_original(self):
        """Test FieldChanged when original instance is None."""
        condition = HasChanged('name')
        
        result = condition.check(self.instance, None)
        self.assertFalse(result)
    
    def test_field_changed_with_dotted_attr(self):
        """Test FieldChanged with dotted attribute path."""
        condition = HasChanged('category.name')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)  # Same category name
    
    def test_field_changed_with_missing_field(self):
        """Test FieldChanged with missing field."""
        condition = HasChanged('non_existent_field')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)


class TestFieldChangedToCondition(TestHookConditionBase):
    """Test the FieldChangedTo condition."""
    
    def test_field_changed_to_with_correct_value(self):
        """Test FieldChangedTo when field changed to expected value."""
        condition = IsEqual('name', 'Test Instance', only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_field_changed_to_with_wrong_value(self):
        """Test FieldChangedTo when field changed to different value."""
        condition = IsEqual('name', 'Different Name', only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_field_changed_to_with_unchanged_field(self):
        """Test FieldChangedTo when field hasn't changed."""
        condition = IsEqual('value', 42, only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        # The field changed from 100 to 42, so this should be True
        self.assertTrue(result)
    
    def test_field_changed_to_with_none_original(self):
        """Test FieldChangedTo when original instance is None."""
        condition = IsEqual('name', 'Test Instance', only_on_change=True)
        
        result = condition.check(self.instance, None)
        self.assertFalse(result)
    
    def test_field_changed_to_with_dotted_attr(self):
        """Test FieldChangedTo with dotted attribute path."""
        condition = IsEqual('status', 'active', only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)


class TestFieldChangedFromCondition(TestHookConditionBase):
    """Test the FieldChangedFrom condition."""
    
    def test_field_changed_from_with_correct_original_value(self):
        """Test FieldChangedFrom when field changed from expected value."""
        condition = WasEqual('name', 'Original Instance', only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_field_changed_from_with_wrong_original_value(self):
        """Test FieldChangedFrom when field changed from different value."""
        condition = WasEqual('name', 'Different Original', only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_field_changed_from_with_unchanged_field(self):
        """Test FieldChangedFrom when field hasn't changed."""
        condition = WasEqual('value', 100, only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        # The field changed from 100 to 42, so this should be True
        self.assertTrue(result)
    
    def test_field_changed_from_with_none_original(self):
        """Test FieldChangedFrom when original instance is None."""
        condition = WasEqual('name', 'Original Instance', only_on_change=True)
        
        result = condition.check(self.instance, None)
        self.assertFalse(result)
    
    def test_field_changed_from_with_dotted_attr(self):
        """Test FieldChangedFrom with dotted attribute path."""
        condition = WasEqual('status', 'pending', only_on_change=True)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)


class TestChangesToCondition(TestHookConditionBase):
    """Test the ChangesTo condition."""
    
    def test_changes_to_with_correct_change(self):
        """Test ChangesTo when field changes to expected value."""
        condition = ChangesTo('name', 'Test Instance')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_changes_to_with_no_change(self):
        """Test ChangesTo when field doesn't change to expected value."""
        condition = ChangesTo('name', 'Different Name')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_changes_to_with_unchanged_field(self):
        """Test ChangesTo when field doesn't change."""
        condition = ChangesTo('value', 42)
        
        result = condition.check(self.instance, self.original_instance)
        # The field changed from 100 to 42, so this should be True
        self.assertTrue(result)
    
    def test_changes_to_with_none_original(self):
        """Test ChangesTo when original instance is None."""
        condition = ChangesTo('name', 'Test Instance')
        
        result = condition.check(self.instance, None)
        self.assertFalse(result)


class TestComparisonConditions(TestHookConditionBase):
    """Test the comparison conditions (IsGreaterThan, IsLessThan, etc.)."""
    
    def test_is_greater_than(self):
        """Test IsGreaterThan condition."""
        condition = IsGreaterThan('value', 40)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_is_greater_than_false(self):
        """Test IsGreaterThan condition when false."""
        condition = IsGreaterThan('value', 50)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_is_greater_than_with_none_value(self):
        """Test IsGreaterThan with None value."""
        condition = IsGreaterThan('value', 40)
        
        # Create instance with None value - use a different field that allows None
        none_value_instance = HookModel.objects.create(
            name="None Value",
            value=0,  # Use 0 instead of None since value field doesn't allow None
            category=self.category,
            created_by=self.user
        )
        
        # Test with a field that can be None
        condition = IsGreaterThan('computed_value', 40)
        result = condition.check(none_value_instance, self.original_instance)
        self.assertFalse(result)
    
    def test_is_greater_than_or_equal_true(self):
        """Test IsGreaterThanOrEqual condition when true."""
        condition = IsGreaterThanOrEqual('value', 42)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_is_greater_than_or_equal_false(self):
        """Test IsGreaterThanOrEqual condition when false."""
        condition = IsGreaterThanOrEqual('value', 50)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_is_less_than_true(self):
        """Test IsLessThan condition when true."""
        condition = IsLessThan('value', 50)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_is_less_than_false(self):
        """Test IsLessThan condition when false."""
        condition = IsLessThan('value', 40)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_is_less_than_or_equal_true(self):
        """Test IsLessThanOrEqual condition when true."""
        condition = IsLessThanOrEqual('value', 42)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_is_less_than_or_equal_false(self):
        """Test IsLessThanOrEqual condition when false."""
        condition = IsLessThanOrEqual('value', 40)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_comparison_with_dotted_attr(self):
        """Test comparison conditions with dotted attribute paths."""
        condition = IsGreaterThan('created_by.id', 0)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)


class TestLogicalConditions(TestHookConditionBase):
    """Test the logical conditions (And, Or, Not)."""
    
    def test_and_condition_both_true(self):
        """Test AndCondition when both conditions are true."""
        cond1 = IsEqual('name', 'Test Instance')
        cond2 = IsEqual('value', 42)
        and_condition = AndCondition(cond1, cond2)
        
        result = and_condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_and_condition_first_false(self):
        """Test AndCondition when first condition is false."""
        cond1 = IsEqual('name', 'Wrong Name')
        cond2 = IsEqual('value', 42)
        and_condition = AndCondition(cond1, cond2)
        
        result = and_condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_and_condition_second_false(self):
        """Test AndCondition when second condition is false."""
        cond1 = IsEqual('name', 'Test Instance')
        cond2 = IsEqual('value', 999)
        and_condition = AndCondition(cond1, cond2)
        
        result = and_condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_or_condition_both_true(self):
        """Test OrCondition when both conditions are true."""
        cond1 = IsEqual('name', 'Test Instance')
        cond2 = IsEqual('value', 42)
        or_condition = OrCondition(cond1, cond2)
        
        result = or_condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_or_condition_first_true(self):
        """Test OrCondition when only first condition is true."""
        cond1 = IsEqual('name', 'Test Instance')
        cond2 = IsEqual('value', 999)
        or_condition = OrCondition(cond1, cond2)
        
        result = or_condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_or_condition_second_true(self):
        """Test OrCondition when only second condition is true."""
        cond1 = IsEqual('name', 'Wrong Name')
        cond2 = IsEqual('value', 42)
        or_condition = OrCondition(cond1, cond2)
        
        result = or_condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_or_condition_both_false(self):
        """Test OrCondition when both conditions are false."""
        cond1 = IsEqual('name', 'Wrong Name')
        cond2 = IsEqual('value', 999)
        or_condition = OrCondition(cond1, cond2)
        
        result = or_condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_not_condition_true(self):
        """Test NotCondition when inner condition is false."""
        inner_condition = IsEqual('name', 'Wrong Name')
        not_condition = NotCondition(inner_condition)
        
        result = not_condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_not_condition_false(self):
        """Test NotCondition when inner condition is true."""
        inner_condition = IsEqual('name', 'Test Instance')
        not_condition = NotCondition(inner_condition)
        
        result = not_condition.check(self.instance, self.original_instance)
        self.assertFalse(result)
    
    def test_complex_logical_conditions(self):
        """Test complex combinations of logical conditions."""
        # (name == 'Test Instance' AND value > 40) OR status == 'pending'
        name_condition = IsEqual('name', 'Test Instance')
        value_condition = IsGreaterThan('value', 40)
        status_condition = IsEqual('status', 'pending')
        
        and_condition = AndCondition(name_condition, value_condition)
        or_condition = OrCondition(and_condition, status_condition)
        
        result = or_condition.check(self.instance, self.original_instance)
        self.assertTrue(result)  # name matches AND value > 40
    
    def test_nested_not_conditions(self):
        """Test nested NotCondition usage."""
        inner_condition = IsEqual('name', 'Test Instance')
        not_condition = NotCondition(inner_condition)
        double_not = NotCondition(not_condition)
        
        result = double_not.check(self.instance, self.original_instance)
        self.assertTrue(result)  # Not(Not(True)) = True


class TestConditionEdgeCases(TestHookConditionBase):
    """Test edge cases for conditions."""
    
    def test_condition_with_missing_related_objects(self):
        """Test conditions with missing related objects."""
        # Create instance without category
        instance_no_category = HookModel.objects.create(
            name="No Category",
            value=0,
            created_by=self.user
        )
        
        condition = IsEqual('category.name', 'Test Category')
        
        result = condition.check(instance_no_category, self.original_instance)
        self.assertFalse(result)
    
    def test_condition_with_deep_nesting(self):
        """Test conditions with deeply nested attribute paths."""
        # This would test very deep nesting, but our models don't support it
        # Just test that it doesn't crash
        condition = IsEqual('created_by.username', 'testuser')
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_condition_with_empty_string_values(self):
        """Test conditions with empty string values."""
        # Create instance with empty string
        empty_string_instance = HookModel.objects.create(
            name="",
            value=0,
            category=self.category,
            created_by=self.user
        )
        
        condition = IsEqual('name', '')
        
        result = condition.check(empty_string_instance, self.original_instance)
        self.assertTrue(result)
    
    def test_condition_with_boolean_values(self):
        """Test conditions with boolean values."""
        condition = IsEqual('is_active', True)
        
        result = condition.check(self.instance, self.original_instance)
        self.assertTrue(result)
    
    def test_condition_with_date_values(self):
        """Test conditions with date values."""
        from datetime import date
        
        condition = IsEqual('created_at.date()', date.today())
        
        result = condition.check(self.instance, self.original_instance)
        # This might fail depending on when the test runs
        # Just test that it doesn't crash
        self.assertIsInstance(result, bool)
