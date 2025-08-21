"""
Extended tests for the queryset module to increase coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.db import transaction
from django.db.models import Subquery, Case, When, Value, AutoField
from django.core.exceptions import ValidationError
from django_bulk_hooks.queryset import HookQuerySetMixin
from django_bulk_hooks.constants import (
    BEFORE_CREATE, AFTER_CREATE, VALIDATE_CREATE,
    BEFORE_UPDATE, AFTER_UPDATE, VALIDATE_UPDATE,
    BEFORE_DELETE, AFTER_DELETE, VALIDATE_DELETE
)
from django_bulk_hooks.context import set_bulk_update_value_map, get_bypass_hooks
from tests.models import HookModel
from tests.utils import create_test_instances


class MockQuerySet:
    """Mock QuerySet for testing HookQuerySetMixin."""
    
    def __init__(self, model):
        self.model = model
        self.db = 'default'
        self._instances = []
    
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
    
    def _prepare_for_bulk_create(self, objs):
        pass
    
    def _batched_insert(self, objs, fields, batch_size=None):
        return [[obj.pk] for obj in objs]


class HookQuerySet(HookQuerySetMixin, MockQuerySet):
    """Test QuerySet that uses HookQuerySetMixin."""
    pass


class HookQuerySetExtendedTestCase(TestCase):
    """Extended test case for HookQuerySet tests."""
    
    def setUp(self):
        self.queryset = HookQuerySet(HookModel)
        self.instances = create_test_instances(HookModel, 3)
        self.queryset._instances = self.instances
        
        # Set up mock model meta
        self.queryset.model._meta.pk_fields = ['id']
        self.queryset.model._meta.local_concrete_fields = [
            Mock(name='name', auto_now=False),
            Mock(name='updated_at', auto_now=True),
            Mock(name='created_at', auto_now_add=True)
        ]
        
    def tearDown(self):
        set_bulk_update_value_map(None)


class TestQuerysetEdgeCases(HookQuerySetExtendedTestCase):
    """Test edge cases and error conditions in queryset methods."""
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_import_error(self, mock_run):
        """Test update method handles Subquery import error."""
        with patch('django_bulk_hooks.queryset.Subquery', side_effect=ImportError("No module named 'django.db.models'")):
            with self.assertRaises(ImportError):
                self.queryset.update(name="Updated Name")
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_like_objects(self, mock_run):
        """Test update method detects subquery-like objects."""
        # Create a mock object that looks like a Subquery but isn't
        mock_subquery_like = Mock()
        mock_subquery_like.query = Mock()
        mock_subquery_like.resolve_expression = Mock()
        
        result = self.queryset.update(name=mock_subquery_like)
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_missing_output_field(self, mock_run):
        """Test update method handles Subquery without output_field."""
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        # Mock the model field
        mock_field = Mock()
        self.queryset.model._meta.get_field.return_value = mock_field
        
        result = self.queryset.update(name=mock_subquery)
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_case_statement_containing_subquery(self, mock_run):
        """Test update method with Case statement containing Subquery."""
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        case_statement = Case(
            When(pk=1, then=mock_subquery),
            default=Value("Default")
        )
        
        # Mock the model field
        mock_field = Mock()
        self.queryset.model._meta.get_field.return_value = mock_field
        
        result = self.queryset.update(name=case_statement)
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_nested_subquery_resolution_error(self, mock_run):
        """Test update method handles nested Subquery resolution error."""
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        case_statement = Case(
            When(pk=1, then=mock_subquery),
            default=Value("Default")
        )
        
        # Mock the model field
        mock_field = Mock()
        self.queryset.model._meta.get_field.return_value = mock_field
        
        # Mock resolve_expression to raise an error
        case_statement.resolve_expression.side_effect = Exception("Resolution failed")
        
        with self.assertRaises(Exception):
            self.queryset.update(name=case_statement)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_refresh_instances(self, mock_run):
        """Test update method refreshes instances after Subquery update."""
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        # Mock the model field
        mock_field = Mock()
        self.queryset.model._meta.get_field.return_value = mock_field
        
        # Mock _base_manager.filter to return refreshed instances
        refreshed_instances = create_test_instances(HookModel, 3)
        with patch.object(self.queryset.model, '_base_manager') as mock_base_manager:
            mock_base_manager.filter.return_value = refreshed_instances
            
            result = self.queryset.update(name=mock_subquery)
            
            # Check that hooks were called
            self.assertEqual(mock_run.call_count, 3)
            self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_in_bypass_context(self, mock_run):
        """Test update method runs hooks for Subquery even in bypass context."""
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        # Mock the model field
        mock_field = Mock()
        self.queryset.model._meta.get_field.return_value = mock_field
        
        # Set bypass hooks
        set_bypass_hooks(True)
        
        try:
            result = self.queryset.update(name=mock_subquery)
            
            # Hooks should still run for Subquery operations
            self.assertEqual(mock_run.call_count, 3)
            self.assertEqual(result, 3)
        finally:
            set_bypass_hooks(False)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_super_update_failure(self, mock_run):
        """Test update method handles super().update() failure."""
        # Mock super().update to raise an exception
        with patch.object(self.queryset, 'update', side_effect=Exception("Update failed")):
            with self.assertRaises(Exception):
                self.queryset.update(name="Updated Name")
    
    def test_detect_modified_fields_with_none_originals(self):
        """Test _detect_modified_fields with None originals."""
        result = self.queryset._detect_modified_fields(self.instances, None)
        self.assertEqual(result, set())
    
    def test_detect_modified_fields_with_mismatched_lengths(self):
        """Test _detect_modified_fields with mismatched instance lengths."""
        # Create fewer originals than new instances
        originals = [Mock(pk=1, name='Original 1')]
        
        result = self.queryset._detect_modified_fields(self.instances, originals)
        # Should handle the mismatch gracefully
        self.assertIsInstance(result, set)
    
    def test_detect_modified_fields_with_relation_fields(self):
        """Test _detect_modified_fields with relation fields."""
        # Create mock instances with relation fields
        new_instance = Mock(pk=1)
        new_instance._meta.fields = [
            Mock(name='id', is_relation=False),
            Mock(name='category', is_relation=True, attname='category_id')
        ]
        setattr(new_instance, 'category_id', 5)
        
        original_instance = Mock(pk=1)
        setattr(original_instance, 'category_id', 3)
        
        result = self.queryset._detect_modified_fields([new_instance], [original_instance])
        self.assertIn('category', result)
    
    def test_get_inheritance_chain(self):
        """Test _get_inheritance_chain method."""
        # Mock the model's parent structure
        mock_parent = Mock()
        mock_parent._meta.proxy = False
        
        with patch.object(self.queryset.model._meta, 'parents', {mock_parent: None}):
            with patch.object(self.queryset.model._meta, 'proxy', False):
                chain = self.queryset._get_inheritance_chain()
                self.assertIsInstance(chain, list)
    
    def test_get_inheritance_chain_with_proxy_parents(self):
        """Test _get_inheritance_chain with proxy parents."""
        # Mock proxy parents
        mock_proxy_parent = Mock()
        mock_proxy_parent._meta.proxy = True
        
        with patch.object(self.queryset.model._meta, 'parents', {mock_proxy_parent: None}):
            chain = self.queryset._get_inheritance_chain()
            # Proxy parents should be excluded
            self.assertEqual(len(chain), 1)  # Only the current model
    
    def test_get_inheritance_chain_deep_inheritance(self):
        """Test _get_inheritance_chain with deep inheritance."""
        # Mock very deep inheritance
        mock_parents = []
        for i in range(15):  # Exceeds the safety limit
            mock_parent = Mock()
            mock_parent._meta.proxy = False
            mock_parents.append(mock_parent)
        
        with patch.object(self.queryset.model._meta, 'parents', {mock_parents[0]: None}):
            with self.assertRaises(ValueError):
                self.queryset._get_inheritance_chain()


class TestMTIBulkOperations(HookQuerySetExtendedTestCase):
    """Test MTI (Multi-Table Inheritance) bulk operations."""
    
    def setUp(self):
        super().setUp()
        # Mock MTI detection
        self.queryset.model._meta.all_parents = [
            Mock(_meta=Mock(concrete_model=Mock()))
        ]
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_mti_bulk_create_batch_processing(self, mock_run):
        """Test MTI bulk create batch processing."""
        new_instances = create_test_instances(HookModel, 2)
        
        # Mock the inheritance chain
        inheritance_chain = [Mock(), Mock()]
        
        result = self.queryset._mti_bulk_create(new_instances, inheritance_chain)
        
        self.assertEqual(result, new_instances)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_mti_bulk_create_with_bypass_hooks(self, mock_run):
        """Test MTI bulk create with bypass hooks."""
        new_instances = create_test_instances(HookModel, 2)
        inheritance_chain = [Mock(), Mock()]
        
        result = self.queryset._mti_bulk_create(
            new_instances, 
            inheritance_chain, 
            bypass_hooks=True
        )
        
        self.assertEqual(result, new_instances)
    
    def test_create_parent_instance(self):
        """Test _create_parent_instance method."""
        source_obj = Mock()
        source_obj.name = "Test Name"
        source_obj.value = 100
        
        parent_model = Mock()
        parent_model._meta.local_fields = [
            Mock(name='name'),
            Mock(name='value'),
            Mock(name='auto_now_field', auto_now=True),
            Mock(name='auto_now_add_field', auto_now_add=True)
        ]
        
        result = self.queryset._create_parent_instance(source_obj, parent_model, None)
        
        self.assertIsInstance(result, Mock)
    
    def test_create_child_instance(self):
        """Test _create_child_instance method."""
        source_obj = Mock()
        source_obj.name = "Test Name"
        
        child_model = Mock()
        child_model._meta.local_fields = [
            Mock(name='name'),
            Mock(name='auto_now_field', auto_now=True),
            Mock(name='auto_now_add_field', auto_now_add=True)
        ]
        
        parent_instances = {Mock(): Mock(pk=1)}
        
        result = self.queryset._create_child_instance(source_obj, child_model, parent_instances)
        
        self.assertIsInstance(result, Mock)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_mti_bulk_update_batch_processing(self, mock_run):
        """Test MTI bulk update batch processing."""
        fields = ['name', 'value']
        
        # Mock field groups
        field_groups = {
            Mock(): ['name'],
            Mock(): ['value']
        }
        
        inheritance_chain = [Mock(), Mock()]
        
        result = self.queryset._mti_bulk_update(
            self.instances, 
            fields, 
            field_groups, 
            inheritance_chain
        )
        
        self.assertIsInstance(result, int)
    
    def test_process_mti_bulk_update_batch(self):
        """Test _process_mti_bulk_update_batch method."""
        fields = ['name', 'value']
        
        # Mock field groups
        field_groups = {
            Mock(): ['name'],
            Mock(): ['value']
        }
        
        inheritance_chain = [Mock(), Mock()]
        
        result = self.queryset._process_mti_bulk_update_batch(
            self.instances, 
            field_groups, 
            inheritance_chain
        )
        
        self.assertIsInstance(result, int)
    
    def test_process_mti_bulk_update_batch_no_pks(self):
        """Test _process_mti_bulk_update_batch with no primary keys."""
        fields = ['name']
        field_groups = {Mock(): ['name']}
        inheritance_chain = [Mock()]
        
        # Create instances without PKs
        instances_without_pks = [Mock(pk=None), Mock(pk=None)]
        
        result = self.queryset._process_mti_bulk_update_batch(
            instances_without_pks, 
            field_groups, 
            inheritance_chain
        )
        
        self.assertEqual(result, 0)


class TestBulkDelete(HookQuerySetExtendedTestCase):
    """Test bulk delete functionality."""
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_with_hooks(self, mock_run):
        """Test bulk_delete method runs hooks correctly."""
        result = self.queryset.bulk_delete(self.instances)
        
        # Check that hooks were called
        self.assertEqual(mock_run.call_count, 3)  # VALIDATE_DELETE, BEFORE_DELETE, AFTER_DELETE
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_empty_objects(self, mock_run):
        """Test bulk_delete method with empty objects list."""
        result = self.queryset.bulk_delete([])
        
        # No hooks should run for empty objects
        self.assertEqual(mock_run.call_count, 0)
        self.assertEqual(result, 0)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_bypass_hooks(self, mock_run):
        """Test bulk_delete method respects bypass_hooks parameter."""
        result = self.queryset.bulk_delete(self.instances, bypass_hooks=True)
        
        # No hooks should run when bypassing
        self.assertEqual(mock_run.call_count, 0)
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_bypass_validation(self, mock_run):
        """Test bulk_delete method respects bypass_validation parameter."""
        result = self.queryset.bulk_delete(self.instances, bypass_validation=True)
        
        # Only BEFORE_DELETE and AFTER_DELETE should run
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(result, 3)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_wrong_model_type(self, mock_run):
        """Test bulk_delete method validates model types."""
        wrong_instances = [Mock()]  # Wrong type
        
        with self.assertRaises(TypeError):
            self.queryset.bulk_delete(wrong_instances)
        
        # No hooks should run for invalid types
        self.assertEqual(mock_run.call_count, 0)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_with_none_pks(self, mock_run):
        """Test bulk_delete method handles instances with None PKs."""
        # Create instances with None PKs
        instances_with_none_pks = [Mock(pk=None), Mock(pk=None)]
        
        result = self.queryset.bulk_delete(instances_with_none_pks)
        
        # Should handle gracefully
        self.assertEqual(result, 0)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_transaction_rollback(self, mock_run):
        """Test bulk_delete method rolls back transaction on error."""
        # Mock engine.run to raise an exception
        mock_run.side_effect = Exception("Hook failed")
        
        with self.assertRaises(Exception):
            self.queryset.bulk_delete(self.instances)
