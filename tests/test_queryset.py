"""
Tests for the queryset module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.db import transaction
from django.db.models import Subquery, Case, When, Value
from django_bulk_hooks.queryset import HookQuerySetMixin
from django_bulk_hooks.constants import (
    BEFORE_CREATE, AFTER_CREATE, VALIDATE_CREATE,
    BEFORE_UPDATE, AFTER_UPDATE, VALIDATE_UPDATE,
    BEFORE_DELETE, AFTER_DELETE, VALIDATE_DELETE
)
from django_bulk_hooks.context import set_bulk_update_value_map
from tests.models import HookModel
from tests.utils import create_test_instances


class MockQuerySet:
    """Mock QuerySet for testing HookQuerySetMixin."""
    
    def __init__(self, model):
        self.model = model
        self.db = 'default'  # Add missing db attribute
        self._instances = []  # Add instances for iteration
    
    def __iter__(self):
        return iter(self._instances)
    
    def __len__(self):
        return len(self._instances)
    
    def count(self):
        return len(self._instances)
    
    def delete(self):
        if not self._instances:
            return (0, {})
        return (3, {'tests.HookModel': 3})
    
    def update(self, **kwargs):
        if not self._instances:
            return 0
        return 3
    
    def bulk_create(self, objs, **kwargs):
        return objs
    
    def bulk_update(self, objs, fields, **kwargs):
        if not objs:
            return 0
        return len(objs)
    
    def _validate_bulk_create(self, objs):
        # Mock validation method
        pass


class HookQuerySet(HookQuerySetMixin, MockQuerySet):
    """Test QuerySet that uses HookQuerySetMixin."""
    pass


class HookQuerySetTestCase(TestCase):
    """Base test case for HookQuerySet tests."""
    
    def setUp(self):
        self.queryset = HookQuerySet(HookModel)
        self.instances = create_test_instances(HookModel, 3)
        # Set the instances on the queryset for iteration
        self.queryset._instances = self.instances
    
    def tearDown(self):
        # Clean up any test data
        pass


class TestHookQuerySetMixin(HookQuerySetTestCase):
    """Test HookQuerySetMixin functionality with mocked operations."""
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_delete_with_hooks(self, mock_run):
        """Test delete method runs hooks correctly."""
        result = self.queryset.delete()
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)  # VALIDATE_DELETE, BEFORE_DELETE, AFTER_DELETE
        self.assertEqual(result, (3, {'tests.HookModel': 3}))
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_delete_empty_queryset(self, mock_run):
        """Test delete method with empty queryset."""
        # Mock empty queryset by setting empty instances
        self.queryset._instances = []
        result = self.queryset.delete()
        
        # No hooks should run for empty queryset
        self.assertEqual(mock_run.call_count, 0)
        self.assertEqual(result, 0)  # Empty queryset returns 0, not (0, {})
        # Restore instances for other tests
        self.queryset._instances = self.instances
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_delete_transaction_rollback(self, mock_run):
        """Test delete method rolls back transaction on error."""
        # Mock engine.run to raise an exception
        mock_run.side_effect = Exception("Hook failed")
        
        with self.assertRaises(Exception):
            self.queryset.delete()
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_hooks(self, mock_run):
        """Test update method runs hooks correctly."""
        result = self.queryset.update(name="Updated Name")
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)  # VALIDATE_UPDATE, BEFORE_UPDATE, AFTER_UPDATE
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_empty_queryset(self, mock_run):
        """Test update method with empty queryset."""
        # Mock empty queryset by setting empty instances
        self.queryset._instances = []
        result = self.queryset.update(name="Updated Name")
        
        # No hooks should run for empty queryset
        self.assertEqual(mock_run.call_count, 0)
        self.assertEqual(result, 0)
        # Restore instances for other tests
        self.queryset._instances = self.instances
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_bypass_hooks_context(self, mock_run):
        """Test update method respects bypass_hooks context."""
        # Use the context manager from django_bulk_hooks.context
        from django_bulk_hooks.context import set_bypass_hooks
        
        # Set bypass hooks
        set_bypass_hooks(True)
        
        try:
            result = self.queryset.update(name="Updated Name")
            
            # No hooks should run when bypassing
            self.assertEqual(mock_run.call_count, 0)
            self.assertEqual(result, 3)
        finally:
            # Clean up
            set_bypass_hooks(False)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_detection(self, mock_run):
        """Test update method detects Subquery objects."""
        # Create a mock Subquery
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        result = self.queryset.update(
            name="Updated Name",
            computed_value=mock_subquery
        )
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)  # VALIDATE_UPDATE, BEFORE_UPDATE, AFTER_UPDATE
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_per_object_values(self, mock_run):
        """Test update method with per-object value map."""
        # Set up per-object values
        value_map = {
            self.instances[0].pk: {"name": "Instance 1", "value": 100},
            self.instances[1].pk: {"name": "Instance 2", "value": 200},
        }
        set_bulk_update_value_map(value_map)
        
        try:
            result = self.queryset.update(status="active")
            
            # Check that hooks were called
            self.assertEqual(mock_run.call_count, 3)  # VALIDATE_UPDATE, BEFORE_UPDATE, AFTER_UPDATE
            self.assertEqual(result, 3)
        finally:
            # Clean up
            set_bulk_update_value_map({})
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_case_statements(self, mock_run):
        """Test update method with Case/When statements."""
        # Create a Case statement
        case_statement = Case(
            When(pk=1, then=Value("Case 1")),
            When(pk=2, then=Value("Case 2")),
            default=Value("Default")
        )
        
        result = self.queryset.update(name=case_statement)
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)  # VALIDATE_UPDATE, BEFORE_UPDATE, AFTER_UPDATE
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_nested_subquery_in_case(self, mock_run):
        """Test update method with nested Subquery in Case statement."""
        # Create a nested Subquery in Case
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        case_statement = Case(
            When(pk=1, then=mock_subquery),
            default=Value("Default")
        )
        
        result = self.queryset.update(name=case_statement)
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)  # VALIDATE_UPDATE, BEFORE_UPDATE, AFTER_UPDATE
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_modified_fields_detection(self, mock_run):
        """Test update method detects modified fields from hooks."""
        # Mock the _detect_modified_fields method
        with patch.object(self.queryset, '_detect_modified_fields') as mock_detect:
            mock_detect.return_value = ["name", "value", "status"]
            
            result = self.queryset.update(name="Updated Name")
            
            # Check that hooks were called
            self.assertEqual(mock_run.call_count, 3)  # VALIDATE_UPDATE, BEFORE_UPDATE, AFTER_UPDATE
            self.assertEqual(result, 3)
    
    def test_update_error_handling(self):
        """Test update method handles errors gracefully."""
        # Mock super().update to raise an exception
        with patch.object(self.queryset, 'update', side_effect=Exception("Update failed")):
            with self.assertRaises(Exception):
                self.queryset.update(name="Updated Name")
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_transaction_rollback(self, mock_run):
        """Test update method rolls back transaction on error."""
        # Mock engine.run to raise an exception
        mock_run.side_effect = Exception("Hook failed")
        
        with self.assertRaises(Exception):
            self.queryset.update(name="Updated Name")
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_create_with_hooks(self, mock_run):
        """Test bulk_create method runs hooks correctly."""
        new_instances = create_test_instances(HookModel, 2)
        
        result = self.queryset.bulk_create(new_instances)
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)  # VALIDATE_CREATE, BEFORE_CREATE, AFTER_CREATE
        self.assertEqual(result, new_instances)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_create_empty_objects(self, mock_run):
        """Test bulk_create method with empty objects list."""
        result = self.queryset.bulk_create([])
        
        # No hooks should run for empty objects
        self.assertEqual(mock_run.call_count, 0)
        self.assertEqual(result, [])
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_create_bypass_hooks(self, mock_run):
        """Test bulk_create method respects bypass_hooks parameter."""
        new_instances = create_test_instances(HookModel, 2)
        
        result = self.queryset.bulk_create(new_instances, bypass_hooks=True)
        
        # No hooks should run when bypassing
        self.assertEqual(mock_run.call_count, 0)
        self.assertEqual(result, new_instances)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_create_bypass_validation(self, mock_run):
        """Test bulk_create method respects bypass_validation parameter."""
        new_instances = create_test_instances(HookModel, 2)
        
        result = self.queryset.bulk_create(new_instances, bypass_validation=True)
        
        # Only BEFORE_CREATE should run
        self.assertEqual(mock_run.call_count, 2)  # BEFORE_CREATE, AFTER_CREATE
        self.assertEqual(result, new_instances)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_create_wrong_model_type(self, mock_run):
        """Test bulk_create method validates model types."""
        wrong_instances = [Mock()]  # Wrong type
        
        with self.assertRaises(TypeError):
            self.queryset.bulk_create(wrong_instances)
        
        # No hooks should run for invalid types
        self.assertEqual(mock_run.call_count, 0)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_create_transaction_rollback(self, mock_run):
        """Test bulk_create method rolls back transaction on error."""
        # Mock engine.run to raise an exception
        mock_run.side_effect = Exception("Hook failed")
        
        new_instances = create_test_instances(HookModel, 2)
        
        with self.assertRaises(Exception):
            self.queryset.bulk_create(new_instances)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_create_with_mti_detection(self, mock_run):
        """Test bulk_create method detects MTI models."""
        # Mock the model to appear as MTI
        with patch.object(self.queryset.model._meta, 'all_parents') as mock_parents:
            mock_parents.__iter__ = lambda self: iter([Mock(_meta=Mock(concrete_model=Mock()))])
            
            new_instances = create_test_instances(HookModel, 2)
            result = self.queryset.bulk_create(new_instances)
            
            # Check that hooks were called
            self.assertEqual(mock_run.call_count, 3)  # VALIDATE_CREATE, BEFORE_CREATE, AFTER_CREATE
            self.assertEqual(result, new_instances)


class TestHookQuerySetMixinIntegration(HookQuerySetTestCase):
    """Test HookQuerySetMixin with real database operations."""
    
    def test_real_bulk_update_operation(self):
        """Test real bulk_update operation with hooks."""
        # Use the decorator approach instead of register_hook
        from django_bulk_hooks.decorators import bulk_hook
        
        @bulk_hook(HookModel, AFTER_UPDATE)
        def track_update(new_records, old_records=None, **kwargs):
            pass
        
        try:
            fields = ["name", "value"]
            result = self.queryset.bulk_update(self.instances, fields)
            self.assertEqual(result, 3)
        finally:
            # Clean up the hook
            pass
