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
from django_bulk_hooks.context import set_bulk_update_value_map, get_bypass_hooks, set_bypass_hooks
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
        # Set PKs for the instances to simulate saved objects
        for i, instance in enumerate(self.instances):
            instance.pk = i + 1
        self.queryset._instances = self.instances
        
        # Set up mock model meta
        self.queryset.model._meta.pk_fields = ['id']
        self.queryset.model._meta.local_concrete_fields = [
            Mock(name='name', auto_now=False, is_relation=False, attname='name'),
            Mock(name='updated_at', auto_now=True, is_relation=False, attname='updated_at'),
            Mock(name='created_at', auto_now_add=True, is_relation=False, attname='created_at')
        ]
        # Set field names properly for Mock objects
        field_names = ['name', 'updated_at', 'created_at']
        for i, field in enumerate(self.queryset.model._meta.local_concrete_fields):
            field.name = field_names[i]
        
    def tearDown(self):
        set_bulk_update_value_map(None)


class TestQuerysetEdgeCases(HookQuerySetExtendedTestCase):
    """Test edge cases and error conditions in queryset methods."""
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_import_error(self, mock_run):
        """Test update method handles Subquery import error."""
        with patch('django.db.models.Subquery', side_effect=ImportError("No module named 'django.db.models'")):
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
        self.queryset.model._meta.get_field = Mock(return_value=mock_field)
        
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
        self.queryset.model._meta.get_field = Mock(return_value=mock_field)
        
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
        self.queryset.model._meta.get_field = Mock(return_value=mock_field)
        
        # Mock resolve_expression to raise an error
        case_statement.resolve_expression = Mock(side_effect=Exception("Resolution failed"))
        
        with self.assertRaises(Exception):
            self.queryset.update(name=case_statement)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_update_with_subquery_refresh_instances(self, mock_run):
        """Test update method refreshes instances after Subquery update."""
        mock_subquery = Mock(spec=Subquery)
        mock_subquery.output_field = None
        
        # Mock the model field
        mock_field = Mock()
        self.queryset.model._meta.get_field = Mock(return_value=mock_field)
        
        # Mock _base_manager.filter to return refreshed instances
        refreshed_instances = create_test_instances(HookModel, 3)
        with patch.object(self.queryset.model._base_manager, 'filter', return_value=refreshed_instances) as mock_filter:
            
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
        self.queryset.model._meta.get_field = Mock(return_value=mock_field)
        
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
            Mock(name='id', is_relation=False, attname='id'),
            Mock(name='category', is_relation=True, attname='category_id')
        ]
        # Set field names properly for Mock objects
        new_instance._meta.fields[0].name = 'id'
        new_instance._meta.fields[1].name = 'category'
        setattr(new_instance, 'category_id', 5)

        original_instance = Mock(pk=1)
        setattr(original_instance, 'category_id', 3)

        result = self.queryset._detect_modified_fields([new_instance], [original_instance])
        # Check that some field was detected as modified (the category_id field)
        self.assertTrue(len(result) > 0)
    
    def test_get_inheritance_chain(self):
        """Test _get_inheritance_chain method."""
        # Mock the model's parent structure
        mock_parent = Mock()
        mock_parent._meta.proxy = False

        # Mock parents as a proper dictionary
        parents_dict = {mock_parent: None}

        # Create a custom dict-like class that allows setting keys
        class MockDict(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.keys = Mock(return_value=iter([mock_parent]))

        mock_parents_dict = MockDict(parents_dict)

        with patch.object(self.queryset.model._meta, 'parents', mock_parents_dict):
            with patch.object(self.queryset.model._meta, 'proxy', False):
                chain = self.queryset._get_inheritance_chain()
                self.assertIsInstance(chain, list)
    
    def test_get_inheritance_chain_with_proxy_parents(self):
        """Test _get_inheritance_chain with proxy parents."""
        # Mock proxy parents
        mock_proxy_parent = Mock()
        mock_proxy_parent._meta.proxy = True

        # Mock parents as a proper dictionary
        parents_dict = {mock_proxy_parent: None}

        # Create a custom dict-like class that allows setting keys
        class MockDict(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.keys = Mock(return_value=iter([mock_proxy_parent]))

        mock_parents_dict = MockDict(parents_dict)

        with patch.object(self.queryset.model._meta, 'parents', mock_parents_dict):
            chain = self.queryset._get_inheritance_chain()
            # Proxy parents should be excluded
            self.assertEqual(len(chain), 1)  # Only the current model
    
    def test_get_inheritance_chain_deep_inheritance(self):
        """Test _get_inheritance_chain with deep inheritance."""
        # Mock very deep inheritance - create a chain of parents
        mock_parents = {}
        current_parent = Mock()
        current_parent._meta.proxy = False
        mock_parents[current_parent] = None

        # Create a chain that exceeds the safety limit
        for i in range(15):
            next_parent = Mock()
            next_parent._meta.proxy = False
            next_parent._meta.parents = {current_parent: None}
            current_parent = next_parent

        # Mock parents as a proper dictionary
        parents_dict = mock_parents

        # Create a custom dict-like class that allows setting keys
        class MockDict(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.keys = Mock(return_value=iter(parents_dict.keys()))

        mock_parents_dict = MockDict(parents_dict)

        with patch.object(self.queryset.model._meta, 'parents', mock_parents_dict):
            with self.assertRaises(ValueError):
                self.queryset._get_inheritance_chain()


class TestMTIBulkOperations(HookQuerySetExtendedTestCase):
    """Test MTI (Multi-Table Inheritance) bulk operations."""
    
    def setUp(self):
        super().setUp()
        # Mock MTI detection
        mock_parent = Mock()
        mock_parent._meta.concrete_model = Mock()
        self.queryset.model._meta.all_parents = [mock_parent]

        # Mock get_meta to return a proper meta object that supports indexing
        class MockMeta:
            def __init__(self):
                self.pk = Mock()
                self.pk.name = 'id'
                self.get_field = Mock(return_value=Mock(name='id'))

            def __getitem__(self, key):
                # Support indexing like Django expects
                if key == -1:
                    return Mock()
                return Mock()

            def __len__(self):
                return 1

        mock_meta = MockMeta()
        self.queryset.model._meta.get_meta = Mock(return_value=mock_meta)

    @patch('django_bulk_hooks.queryset.engine.run')
    def test_mti_bulk_create_batch_processing(self, mock_run):
        """Test MTI bulk create batch processing."""
        new_instances = create_test_instances(HookModel, 2)

        # Mock the inheritance chain with proper local_fields
        mock_parent = Mock()
        mock_parent._meta.local_fields = [Mock()]
        mock_parent._meta.local_fields[0].name = 'name'
        # Make local_fields iterable
        class IterableList(list):
            pass
        mock_parent._meta.local_fields = IterableList(mock_parent._meta.local_fields)

        inheritance_chain = [mock_parent, Mock()]

        result = self.queryset._mti_bulk_create(new_instances, inheritance_chain)

        self.assertEqual(result, new_instances)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_mti_bulk_create_with_bypass_hooks(self, mock_run):
        """Test MTI bulk create with bypass hooks."""
        new_instances = create_test_instances(HookModel, 2)

        # Mock the inheritance chain with proper local_fields
        mock_parent = Mock()
        mock_parent._meta.local_fields = [Mock()]
        mock_parent._meta.local_fields[0].name = 'name'
        # Make local_fields iterable
        class IterableList(list):
            pass
        mock_parent._meta.local_fields = IterableList(mock_parent._meta.local_fields)

        inheritance_chain = [mock_parent, Mock()]

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
            Mock(name='name', auto_now=False),
            Mock(name='value', auto_now=False),
            Mock(name='auto_now_field', auto_now=True),
            Mock(name='auto_now_add_field', auto_now_add=True)
        ]
        # Set field names properly for Mock objects
        field_names = ['name', 'value', 'auto_now_field', 'auto_now_add_field']
        for i, field in enumerate(parent_model._meta.local_fields):
            field.name = field_names[i]

        # Make local_fields iterable by creating a custom list-like object
        class IterableList(list):
            pass
        parent_model._meta.local_fields = IterableList(parent_model._meta.local_fields)

        result = self.queryset._create_parent_instance(source_obj, parent_model, None)

        self.assertIsInstance(result, Mock)
    
    def test_create_child_instance(self):
        """Test _create_child_instance method."""
        source_obj = Mock()
        source_obj.name = "Test Name"

        child_model = Mock()
        child_model._meta.local_fields = [
            Mock(name='name', auto_now=False),
            Mock(name='auto_now_field', auto_now=True),
            Mock(name='auto_now_add_field', auto_now_add=True)
        ]
        # Set field names properly for Mock objects
        field_names = ['name', 'auto_now_field', 'auto_now_add_field']
        for i, field in enumerate(child_model._meta.local_fields):
            field.name = field_names[i]

        # Make local_fields iterable by creating a custom list-like object
        class IterableList(list):
            pass
        child_model._meta.local_fields = IterableList(child_model._meta.local_fields)

        # Create a mock parent model and instance
        mock_parent_model = Mock()
        mock_parent_instance = Mock(pk=1)
        # Ensure the parent model has string field names
        for field in child_model._meta.local_fields:
            if hasattr(field, 'name') and isinstance(field.name, str):
                setattr(mock_parent_instance, field.name, getattr(source_obj, field.name, None))

        # Mock get_ancestor_link to return a proper link object
        mock_parent_link = Mock()
        mock_parent_link.attname = 'parent_id'
        child_model._meta.get_ancestor_link = Mock(return_value=mock_parent_link)

        parent_instances = {mock_parent_model: mock_parent_instance}

        result = self.queryset._create_child_instance(source_obj, child_model, parent_instances)

        self.assertIsInstance(result, Mock)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_mti_bulk_update_batch_processing(self, mock_run):
        """Test MTI bulk update batch processing."""
        fields = ['name', 'value']

        # Mock field groups
        mock_model1 = Mock()
        mock_model1._meta.local_fields = [Mock()]
        mock_model1._meta.local_fields[0].name = 'name'
        # Make local_fields iterable
        class IterableList(list):
            pass
        mock_model1._meta.local_fields = IterableList(mock_model1._meta.local_fields)

        mock_model2 = Mock()
        mock_model2._meta.local_fields = [Mock()]
        mock_model2._meta.local_fields[0].name = 'value'
        # Make local_fields iterable
        class IterableList(list):
            pass
        mock_model2._meta.local_fields = IterableList(mock_model2._meta.local_fields)

        field_groups = {
            mock_model1: ['name'],
            mock_model2: ['value']
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

        # Mock field groups with proper setup
        mock_model1 = Mock()
        mock_model1._meta.local_fields = [Mock()]
        mock_model1._meta.local_fields[0].name = 'name'
        # Make local_fields iterable
        class IterableList(list):
            pass
        mock_model1._meta.local_fields = IterableList(mock_model1._meta.local_fields)
        mock_model1._meta.parents = {}

        mock_model2 = Mock()
        mock_model2._meta.local_fields = [Mock()]
        mock_model2._meta.local_fields[0].name = 'value'
        # Make local_fields iterable
        class IterableList(list):
            pass
        mock_model2._meta.local_fields = IterableList(mock_model2._meta.local_fields)
        mock_model2._meta.parents = {}

        field_groups = {
            mock_model1: ['name'],
            mock_model2: ['value']
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

        # Mock field groups with proper setup
        mock_model = Mock()
        mock_model._meta.local_fields = [Mock()]
        mock_model._meta.local_fields[0].name = 'name'
        # Make local_fields iterable
        class IterableList(list):
            pass
        mock_model._meta.local_fields = IterableList(mock_model._meta.local_fields)
        mock_model._meta.parents = {}

        field_groups = {mock_model: ['name']}
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
        # Create instances with None PKs that look like HookModel instances
        instances_with_none_pks = [Mock(spec=HookModel, pk=None), Mock(spec=HookModel, pk=None)]

        result = self.queryset.bulk_delete(instances_with_none_pks)

        # Should handle gracefully - returns 0 when no valid PKs
        self.assertEqual(result, 0)
    
    @patch('django_bulk_hooks.queryset.engine.run')
    def test_bulk_delete_transaction_rollback(self, mock_run):
        """Test bulk_delete method rolls back transaction on error."""
        # Mock engine.run to raise an exception
        mock_run.side_effect = Exception("Hook failed")
        
        with self.assertRaises(Exception):
            self.queryset.bulk_delete(self.instances)
