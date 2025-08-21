"""
Additional tests for decorators module to increase coverage.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.exceptions import FieldDoesNotExist
from django_bulk_hooks.decorators import select_related, bulk_hook
from django_bulk_hooks.registry import register_hook
from tests.models import HookModel


class TestDecoratorsCoverage(TestCase):
    """Test uncovered functionality in decorators module."""
    
    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()
    
    def test_select_related_with_nested_fields_error(self):
        """Test select_related decorator raises error for nested fields."""
        @select_related('category__parent')
        def test_func(new_records, old_records=None, **kwargs):
            pass
        
        # Create a mock instance
        mock_instance = Mock()
        mock_instance.pk = 1
        
        # Mock model class
        mock_model = Mock()
        mock_model._meta.get_field.side_effect = FieldDoesNotExist("Field does not exist")
        
        with self.assertRaises(ValueError):
            test_func([mock_instance], model_cls=mock_model)
    
    def test_select_related_with_invalid_field_type(self):
        """Test select_related decorator skips non-relation fields."""
        @select_related('name')  # 'name' is not a relation field
        def test_func(new_records, old_records=None, **kwargs):
            pass
        
        # Create mock instances
        mock_instances = [Mock(pk=1), Mock(pk=2)]
        
        # Mock model class with field that's not a relation
        mock_model = Mock()
        mock_field = Mock()
        mock_field.is_relation = False
        mock_field.many_to_many = False
        mock_field.one_to_many = False
        mock_model._meta.get_field.return_value = mock_field
        
        # Mock base manager
        mock_model._base_manager = Mock()
        mock_model._base_manager.select_related.return_value.in_bulk.return_value = {}
        
        # Should not raise an error, just skip the field
        result = test_func(mock_instances, model_cls=mock_model)
        self.assertIsNone(result)
    
    def test_select_related_with_field_does_not_exist(self):
        """Test select_related decorator handles FieldDoesNotExist gracefully."""
        @select_related('nonexistent_field')
        def test_func(new_records, old_records=None, **kwargs):
            pass
        
        # Create mock instances
        mock_instances = [Mock(pk=1), Mock(pk=2)]
        
        # Mock model class that raises FieldDoesNotExist
        mock_model = Mock()
        mock_model._meta.get_field.side_effect = FieldDoesNotExist("Field does not exist")
        
        # Mock base manager
        mock_model._base_manager = Mock()
        mock_model._base_manager.select_related.return_value.in_bulk.return_value = {}
        
        # Should not raise an error, just skip the field
        result = test_func(mock_instances, model_cls=mock_model)
        self.assertIsNone(result)
    
    def test_select_related_with_attribute_error(self):
        """Test select_related decorator handles AttributeError gracefully."""
        @select_related('category')
        def test_func(new_records, old_records=None, **kwargs):
            pass
        
        # Create mock instances
        mock_instances = [Mock(pk=1), Mock(pk=2)]
        
        # Mock model class
        mock_model = Mock()
        mock_field = Mock()
        mock_field.is_relation = True
        mock_field.many_to_many = False
        mock_field.one_to_many = False
        mock_model._meta.get_field.return_value = mock_field
        
        # Mock base manager
        mock_base_manager = Mock()
        mock_base_manager.select_related.return_value.in_bulk.return_value = {
            1: Mock(category=Mock()),
            2: Mock()  # This one doesn't have category attribute
        }
        mock_model._base_manager = mock_base_manager
        
        # Should not raise an error, just skip the problematic instance
        result = test_func(mock_instances, model_cls=mock_model)
        self.assertIsNone(result)
    
    def test_bulk_hook_decorator(self):
        """Test bulk_hook decorator functionality."""
        @bulk_hook(HookModel, 'BEFORE_CREATE')
        def test_hook(new_records, old_records=None, **kwargs):
            pass
        
        # Verify the hook was registered
        self.assertTrue(hasattr(test_hook, '_bulk_hook_registered'))
    
    def test_bulk_hook_decorator_with_condition_and_priority(self):
        """Test bulk_hook decorator with condition and priority."""
        condition = Mock()
        priority = 100
        
        @bulk_hook(HookModel, 'AFTER_UPDATE', when=condition, priority=priority)
        def test_hook(new_records, old_records=None, **kwargs):
            pass
        
        # Verify the hook was registered
        self.assertTrue(hasattr(test_hook, '_bulk_hook_registered'))
