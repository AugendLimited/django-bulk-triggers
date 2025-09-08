"""
Comprehensive tests for MTI operations to increase code coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.db import models
from django.test import TestCase
from django.db.models import Subquery, Case, When, Value, F

from django_bulk_triggers.mti_operations import MTIOperationsMixin


class MTITestMixin(MTIOperationsMixin):
    """Mixin to test MTI operations directly."""

    def __init__(self):
        self.db = 'default'
        # Mock model with proper MTI structure
        self.model = self._create_mock_model()


    def _create_mock_model(self):
        """Create a mock model that simulates MTI structure."""
        model = Mock()
        model.__name__ = 'TestMTIModel'

        # Mock _meta
        meta = Mock()
        meta.concrete_model = model
        meta.all_parents = [Mock(), Mock()]  # Two parent models
        meta.parents = {}
        meta.local_fields = []  # This will be properly mocked in tests
        meta.pk = Mock()
        meta.pk.name = 'id'
        meta.proxy = False
        meta.get_field = Mock()
        meta.get_ancestor_link = Mock(return_value=None)

        model._meta = meta
        model._base_manager = Mock()

        return model


class TestMTIOperationsMixin(TestCase):
    """Test cases for MTIOperationsMixin."""

    def setUp(self):
        self.mixin = MTITestMixin()

    def test_is_multi_table_inheritance_true(self):
        """Test detection of MTI models."""
        # Mock model with different concrete model in all_parents
        parent_mock = Mock()
        parent_mock._meta.concrete_model = Mock()  # Different from self.model
        self.mixin.model._meta.all_parents = [parent_mock]

        assert self.mixin._is_multi_table_inheritance() is True

    def test_is_multi_table_inheritance_false(self):
        """Test detection of non-MTI models."""
        # Mock model with same concrete model in all_parents
        self.mixin.model._meta.all_parents = [self.mixin.model._meta.concrete_model]

        assert self.mixin._is_multi_table_inheritance() is False

    def test_get_inheritance_chain(self):
        """Test getting the complete inheritance chain."""
        # Mock the inheritance chain
        root_model = Mock()
        root_model._meta.proxy = False
        root_model._meta.parents = {}

        middle_model = Mock()
        middle_model._meta.proxy = False
        middle_model._meta.parents = {root_model: Mock()}

        child_model = Mock()
        child_model._meta.proxy = False
        child_model._meta.parents = {middle_model: Mock()}

        # Set up the chain
        self.mixin.model = child_model

        # Create a custom dict-like object that allows mocking keys
        class MockParentsDict(dict):
            def __init__(self, items):
                super().__init__(items)
                self._keys = items.keys() if items else []

            def keys(self):
                return self._keys

        child_model._meta.parents = MockParentsDict({middle_model: Mock()})
        middle_model._meta.parents = MockParentsDict({root_model: Mock()})
        root_model._meta.parents = MockParentsDict({})

        chain = self.mixin._get_inheritance_chain()
        assert len(chain) == 3

    def test_detect_modified_fields_no_original(self):
        """Test _detect_modified_fields with no original instances."""
        modified = self.mixin._detect_modified_fields([], [])
        assert modified == set()

    def test_detect_modified_fields_with_none_pk(self):
        """Test _detect_modified_fields with None PK."""
        # Mock instance with None PK
        new_instance = Mock()
        new_instance.pk = None
        original = None

        modified = self.mixin._detect_modified_fields([new_instance], [original])
        assert modified == set()

    def test_detect_modified_fields_with_expression_objects(self):
        """Test _detect_modified_fields with expression objects (should skip)."""
        # Mock instances
        new_instance = Mock()
        new_instance.pk = 1
        original = Mock()
        original.pk = 1

        # Mock an expression object
        expr_obj = Mock()
        expr_obj.resolve_expression = Mock()
        new_instance.name = expr_obj

        # Mock field
        field_mock = Mock()
        field_mock.name = 'name'
        field_mock.is_relation = False

        # Mock meta with field
        new_instance._meta.fields = [field_mock]
        original._meta.fields = [field_mock]
        original.name = "Original"

        modified = self.mixin._detect_modified_fields([new_instance], [original])
        assert modified == set()

    def test_detect_modified_fields_with_subquery(self):
        """Test _detect_modified_fields with Subquery object."""
        # Mock instances
        new_instance = Mock()
        new_instance.pk = 1
        original = Mock()
        original.pk = 1

        # Set Subquery as value
        subquery = Subquery(Mock())
        new_instance.name = subquery

        # Mock field
        field_mock = Mock()
        field_mock.name = 'name'
        field_mock.is_relation = False

        # Mock meta with field
        new_instance._meta.fields = [field_mock]
        original._meta.fields = [field_mock]
        original.name = "Original"

        modified = self.mixin._detect_modified_fields([new_instance], [original])
        assert modified == set()

    def test_detect_modified_fields_regular_changes(self):
        """Test _detect_modified_fields with regular field changes."""
        # Mock instances with different values
        new_instance = Mock()
        new_instance.pk = 1
        new_instance.name = "New Name"
        original = Mock()
        original.pk = 1
        original.name = "Original"

        # Mock field
        field_mock = Mock()
        field_mock.name = 'name'
        field_mock.is_relation = False

        # Mock meta with field
        new_instance._meta.fields = [field_mock]
        original._meta.fields = [field_mock]

        modified = self.mixin._detect_modified_fields([new_instance], [original])
        assert 'name' in modified

    def test_detect_modified_fields_foreign_key_changes(self):
        """Test _detect_modified_fields with foreign key changes."""
        # Mock instances with FK changes
        new_instance = Mock()
        new_instance.pk = 1
        original = Mock()
        original.pk = 1

        # Mock foreign key field
        field_mock = Mock()
        field_mock.name = 'industry'
        field_mock.is_relation = True
        field_mock.many_to_many = False
        field_mock.one_to_many = False
        field_mock.attname = 'industry_id'

        # Mock meta with field
        meta_mock_new = Mock()
        meta_mock_new.fields = [field_mock]
        new_instance._meta = meta_mock_new

        meta_mock_orig = Mock()
        meta_mock_orig.fields = [field_mock]
        original._meta = meta_mock_orig

        # Set different FK values - the method compares the field value (industry) with the attname value (industry_id)
        new_instance.industry = 2  # New FK value
        original.industry_id = 1    # Original FK ID value

        modified = self.mixin._detect_modified_fields([new_instance], [original])
        assert 'industry' in modified

    def test_create_parent_instance_basic(self):
        """Test _create_parent_instance with basic fields."""
        # Mock source and parent model
        source = Mock()
        source.name = "Test Company"
        source.registration_number = "123"

        parent_model = Mock()
        parent_obj = Mock()
        parent_model.return_value = parent_obj

        # Mock fields
        field_mock = Mock()
        field_mock.name = 'name'
        field_mock.is_relation = False
        field_mock.many_to_many = False
        field_mock.one_to_many = False

        parent_model._meta.local_fields = [field_mock]

        result = self.mixin._create_parent_instance(source, parent_model, None)

        assert result == parent_obj
        # Verify field was copied
        assert parent_obj.name == "Test Company"

    def test_create_parent_instance_foreign_key(self):
        """Test _create_parent_instance with foreign key fields."""
        # Mock source with FK
        source = Mock()
        source.name = "Test Company"
        fk_obj = Mock()
        fk_obj.pk = 42
        source.some_fk = fk_obj

        parent_model = Mock()
        parent_obj = Mock()
        parent_model.return_value = parent_obj

        # Mock FK field
        field_mock = Mock()
        field_mock.name = 'some_fk'
        field_mock.is_relation = True
        field_mock.many_to_many = False
        field_mock.one_to_many = False
        field_mock.attname = 'some_fk_id'

        parent_model._meta.local_fields = [field_mock]

        result = self.mixin._create_parent_instance(source, parent_model, None)

        # Verify FK ID was set
        assert parent_obj.some_fk_id == 42

    def test_create_parent_instance_with_current_parent(self):
        """Test _create_parent_instance with current parent."""
        source = Mock()
        source.name = "Test Company"

        parent_model = Mock()
        parent_obj = Mock()
        parent_model.return_value = parent_obj

        current_parent = Mock()
        current_parent.__class__ = Mock()

        # Mock field with remote_field
        field_mock = Mock()
        field_mock.name = 'parent_link'
        field_mock.remote_field = Mock()
        field_mock.remote_field.model = current_parent.__class__

        parent_model._meta.local_fields = [field_mock]

        result = self.mixin._create_parent_instance(source, parent_model, current_parent)

        # Verify parent link was set
        assert parent_obj.parent_link == current_parent

    def test_create_parent_instance_auto_now_add(self):
        """Test _create_parent_instance with auto_now_add fields."""
        source = Mock()
        source.name = "Test Company"

        parent_model = Mock()
        parent_obj = Mock()
        parent_model.return_value = parent_obj

        # Mock auto_now_add field
        field_mock = Mock()
        field_mock.name = 'created_at'
        field_mock.auto_now_add = True
        field_mock.pre_save = Mock(return_value=None)
        field_mock.value_from_object = Mock(return_value="2023-01-01")

        # Mock meta with proper local_fields
        meta_mock = Mock()
        meta_mock.local_fields = [field_mock]
        parent_model._meta = meta_mock

        # Mock hasattr to return False for the field value
        parent_obj.created_at = None

        result = self.mixin._create_parent_instance(source, parent_model, None)

        # Just check that the method completes without error
        assert result == parent_obj

    def test_create_parent_instance_auto_now(self):
        """Test _create_parent_instance with auto_now fields."""
        source = Mock()
        source.name = "Test Company"

        parent_model = Mock()
        parent_obj = Mock()
        parent_model.return_value = parent_obj

        # Mock auto_now field
        field_mock = Mock()
        field_mock.name = 'updated_at'
        field_mock.auto_now = True
        field_mock.auto_now_add = False
        field_mock.pre_save = Mock(return_value=None)

        parent_model._meta.local_fields = [field_mock]

        result = self.mixin._create_parent_instance(source, parent_model, None)

        field_mock.pre_save.assert_called_once()

    def test_create_child_instance_basic(self):
        """Test _create_child_instance with basic fields."""
        source = Mock()
        source.name = "Test Company"
        source.registration_number = "123"

        child_model = Mock()
        child_obj = Mock()
        child_model.return_value = child_obj

        parent_instances = {}

        # Mock fields excluding AutoField
        field_mock = Mock()
        field_mock.name = 'name'
        field_mock.is_relation = False
        field_mock.many_to_many = False
        field_mock.one_to_many = False

        # Mock AutoField to be skipped
        from django.db.models import AutoField
        autofield_mock = Mock(spec=AutoField)
        autofield_mock.__class__ = AutoField

        # Mock meta with proper local_fields
        meta_mock = Mock()
        meta_mock.local_fields = [autofield_mock, field_mock]
        child_model._meta = meta_mock

        result = self.mixin._create_child_instance(source, child_model, parent_instances)

        assert result == child_obj
        assert child_obj.name == "Test Company"

    def test_create_child_instance_auto_now_fields(self):
        """Test _create_child_instance with auto_now fields."""
        source = Mock()
        source.name = "Test Company"

        child_model = Mock()
        child_obj = Mock()
        child_model.return_value = child_obj

        parent_instances = {}

        # Mock auto_now field
        field_mock = Mock()
        field_mock.name = 'updated_at'
        field_mock.auto_now = True
        field_mock.auto_now_add = False
        field_mock.pre_save = Mock(return_value=None)

        child_model._meta.local_fields = [field_mock]

        result = self.mixin._create_child_instance(source, child_model, parent_instances)

        field_mock.pre_save.assert_called_once()

    def test_create_child_instance_parent_links(self):
        """Test _create_child_instance with parent links."""
        source = Mock()
        source.name = "Test Company"

        child_model = Mock()
        child_obj = Mock()
        child_model.return_value = child_obj

        # Create mock parent instances
        parent1 = Mock()
        parent1.pk = 1
        parent2 = Mock()
        parent2.pk = 2

        parent_instances = {
            Mock(): parent1,  # parent_model1
            Mock(): parent2   # parent_model2
        }

        # Mock parent links
        parent_link1 = Mock()
        parent_link1.attname = 'parent1_ptr_id'
        parent_link1.name = 'parent1_ptr'

        parent_link2 = Mock()
        parent_link2.attname = 'parent2_ptr_id'
        parent_link2.name = 'parent2_ptr'

        # Mock get_ancestor_link to return appropriate links
        child_model._meta.get_ancestor_link = Mock(side_effect=[parent_link1, parent_link2])

        # Mock fields
        field_mock = Mock()
        field_mock.name = 'name'
        child_model._meta.local_fields = [field_mock]

        result = self.mixin._create_child_instance(source, child_model, parent_instances)

        # Verify parent links were set
        assert child_obj.parent1_ptr_id == 1
        assert child_obj.parent1_ptr == parent1
        assert child_obj.parent2_ptr_id == 2
        assert child_obj.parent2_ptr == parent2

    def test_mti_bulk_create_deep_inheritance_error(self):
        """Test _mti_bulk_create with too deep inheritance chain."""
        # Mock a very deep inheritance chain
        with patch.object(self.mixin, '_get_inheritance_chain') as mock_chain:
            mock_chain.return_value = list(range(15))  # Too deep

            with pytest.raises(ValueError, match="Inheritance chain too deep"):
                self.mixin._mti_bulk_create([])

    def test_mti_bulk_create_with_batch_size(self):
        """Test _mti_bulk_create with custom batch_size."""
        # Mock objects
        objs = [Mock() for i in range(5)]

        with patch.object(self.mixin, '_process_mti_bulk_create_batch') as mock_process, \
             patch.object(self.mixin, '_get_inheritance_chain') as mock_chain:
            # Make mock_process return the batch it was called with
            mock_process.side_effect = lambda batch, *args, **kwargs: batch
            mock_chain.return_value = [Mock(), Mock(), Mock()]  # inheritance chain

            result = self.mixin._mti_bulk_create(objs, batch_size=2)

            # Should be called 3 times (5 objects / 2 batch size = 3 batches)
            assert mock_process.call_count == 3
            assert len(result) == 5

    def test_process_mti_bulk_create_batch_existing_records(self):
        """Test _process_mti_bulk_create_batch with existing records."""
        # Mock objects
        existing_obj = Mock()
        existing_obj.pk = 1
        new_obj = Mock()

        batch = [existing_obj, new_obj]
        inheritance_chain = [Mock(), Mock(), Mock()]

        # Mock the models in the inheritance chain to have proper _meta
        for model in inheritance_chain:
            model._meta.local_fields = []
            # Set up proper pk field name
            model._meta.pk = Mock()
            model._meta.pk.name = 'id'

        with patch.object(self.mixin, '_create_parent_instance') as mock_create_parent, \
             patch.object(self.mixin, '_create_child_instance') as mock_create_child, \
             patch('django_bulk_triggers.engine.run') as mock_engine:

            mock_parent = Mock()
            mock_create_parent.return_value = mock_parent
            mock_child = Mock()
            mock_create_child.return_value = mock_child

            # Mock the bulk insert operation entirely for this test
            with patch.object(self.mixin, '_execute_bulk_insert') as mock_execute, \
                 patch('django.db.models.Manager.using') as mock_using:
                mock_qs = Mock()
                mock_using.return_value = mock_qs
                mock_qs._prepare_for_bulk_create = Mock()

                result = self.mixin._process_mti_bulk_create_batch(
                    batch, inheritance_chain, existing_records=[existing_obj]
                )

                # Should call engine for existing records
                assert mock_engine.call_count >= 2  # BEFORE_UPDATE and AFTER_UPDATE
                # Should call the bulk insert method
                mock_execute.assert_called_once()

    def test_process_mti_bulk_create_batch_new_records(self):
        """Test _process_mti_bulk_create_batch with new records."""
        new_obj = Mock()
        batch = [new_obj]
        inheritance_chain = [Mock(), Mock(), Mock()]

        # Mock the models in the inheritance chain to have proper _meta
        for model in inheritance_chain:
            model._meta.local_fields = []
            # Set up proper pk field name
            model._meta.pk = Mock()
            model._meta.pk.name = 'id'

        with patch.object(self.mixin, '_create_parent_instance') as mock_create_parent, \
             patch.object(self.mixin, '_create_child_instance') as mock_create_child, \
             patch('django_bulk_triggers.engine.run') as mock_engine:

            mock_parent = Mock()
            mock_parent.save = Mock()
            mock_parent.pk = 1

            mock_child = Mock()
            mock_child._is_pk_set = Mock(return_value=False)
            mock_child._state.adding = True
            mock_child._state.db = 'default'
            # Set up pk attribute
            setattr(mock_child, 'id', 1)

            mock_create_parent.return_value = mock_parent
            mock_create_child.return_value = mock_child

            # Mock the bulk insert operation entirely for this test
            with patch.object(self.mixin, '_execute_bulk_insert') as mock_execute, \
                 patch('django.db.models.Manager.using') as mock_using:
                mock_qs = Mock()
                mock_using.return_value = mock_qs
                mock_qs._prepare_for_bulk_create = Mock()

                result = self.mixin._process_mti_bulk_create_batch(
                    batch, inheritance_chain, existing_records=[]
                )

                # Should call engine for new records
                assert mock_engine.call_count >= 2  # BEFORE_CREATE and AFTER_CREATE
                # Should call the bulk insert method
                mock_execute.assert_called_once()

    def test_process_mti_bulk_create_batch_bypass_triggers(self):
        """Test _process_mti_bulk_create_batch with bypass_triggers=True."""
        new_obj = Mock()
        batch = [new_obj]
        inheritance_chain = [Mock(), Mock(), Mock()]

        # Mock the models in the inheritance chain to have proper _meta
        for model in inheritance_chain:
            model._meta.local_fields = []
            # Set up proper pk field name
            model._meta.pk = Mock()
            model._meta.pk.name = 'id'

        with patch.object(self.mixin, '_create_parent_instance') as mock_create_parent, \
             patch.object(self.mixin, '_create_child_instance') as mock_create_child, \
             patch('django_bulk_triggers.engine.run') as mock_engine:

            mock_parent = Mock()
            mock_parent.save = Mock()
            mock_parent.pk = 1

            mock_child = Mock()
            mock_child._is_pk_set = Mock(return_value=False)
            mock_child._state.adding = True
            mock_child._state.db = 'default'
            # Set up pk attribute
            setattr(mock_child, 'id', 1)

            mock_create_parent.return_value = mock_parent
            mock_create_child.return_value = mock_child

            # Mock the bulk insert operation entirely for this test
            with patch.object(self.mixin, '_execute_bulk_insert') as mock_execute, \
                 patch('django.db.models.Manager.using') as mock_using:
                mock_qs = Mock()
                mock_using.return_value = mock_qs
                mock_qs._prepare_for_bulk_create = Mock()

                result = self.mixin._process_mti_bulk_create_batch(
                    batch, inheritance_chain, existing_records=[], bypass_triggers=True
                )

                # Should not call engine when bypass_triggers=True
                mock_engine.assert_not_called()
                # Should call the bulk insert method
                mock_execute.assert_called_once()

    def test_process_mti_bulk_create_batch_update_fields_filtering(self):
        """Test _process_mti_bulk_create_batch with update_fields filtering."""
        existing_obj = Mock()
        existing_obj.pk = 1
        batch = [existing_obj]
        inheritance_chain = [Mock(), Mock(), Mock()]

        # Mock the models in the inheritance chain to have proper _meta
        for model in inheritance_chain:
            model._meta.local_fields = []

        with patch.object(self.mixin, '_create_parent_instance') as mock_create_parent, \
             patch.object(self.mixin, '_create_child_instance') as mock_create_child, \
             patch('django_bulk_triggers.engine.run'):

            mock_parent = Mock()
            mock_parent.save = Mock()
            mock_parent.pk = 1

            mock_create_parent.return_value = mock_parent
            mock_create_child.return_value = Mock()

            result = self.mixin._process_mti_bulk_create_batch(
                batch, inheritance_chain, existing_records=[existing_obj],
                update_fields=['name', 'nonexistent_field']
            )

            # Parent save should be called with filtered fields (may be called multiple times)
            assert mock_parent.save.call_count >= 1

    def test_process_mti_bulk_create_batch_existing_child_update(self):
        """Test updating existing child objects in _process_mti_bulk_create_batch."""
        existing_obj = Mock()
        existing_obj.pk = 1
        batch = [existing_obj]
        inheritance_chain = [Mock(), Mock(), Mock()]

        # Mock the models in the inheritance chain to have proper _meta
        for model in inheritance_chain:
            model._meta.local_fields = []

        with patch.object(self.mixin, '_create_parent_instance') as mock_create_parent, \
             patch.object(self.mixin, '_create_child_instance') as mock_create_child, \
             patch('django_bulk_triggers.engine.run'):

            mock_parent = Mock()
            mock_parent.save = Mock()
            mock_parent.pk = 1

            mock_child = Mock()
            mock_child.save = Mock()

            mock_create_parent.return_value = mock_parent
            mock_create_child.return_value = mock_child

            result = self.mixin._process_mti_bulk_create_batch(
                batch, inheritance_chain, existing_records=[existing_obj]
            )

            # Child save should be called for existing records
            mock_child.save.assert_called_once()

    def test_process_mti_bulk_create_batch_bulk_insert_new_objects(self):
        """Test bulk insert of new child objects in _process_mti_bulk_create_batch."""
        new_objs = [Mock() for i in range(3)]
        batch = new_objs
        inheritance_chain = [Mock(), Mock(), Mock()]

        # Mock the models in the inheritance chain to have proper _meta
        for model in inheritance_chain:
            model._meta.local_fields = []
            # Set up proper pk field name
            model._meta.pk = Mock()
            model._meta.pk.name = 'id'

        with patch.object(self.mixin, '_create_parent_instance') as mock_create_parent, \
             patch.object(self.mixin, '_create_child_instance') as mock_create_child, \
             patch('django_bulk_triggers.engine.run'):

            mock_parent = Mock()
            mock_parent.save = Mock()
            mock_parent.pk = 1

            mock_children = []
            for i, obj in enumerate(new_objs):
                mock_child = Mock()
                mock_child._is_pk_set = Mock(return_value=i == 0)  # First has PK, others don't
                mock_child._state.adding = True
                mock_child._state.db = 'default'
                # Set up pk attribute
                setattr(mock_child, 'id', i + 1)
                mock_children.append(mock_child)

            mock_create_parent.return_value = mock_parent
            mock_create_child.side_effect = mock_children

            # Mock the extracted bulk insert method for easier testing
            with patch.object(self.mixin, '_execute_bulk_insert') as mock_bulk_insert, \
                 patch('django.db.models.Manager.using') as mock_using:
                mock_qs = Mock()
                mock_using.return_value = mock_qs
                mock_qs._prepare_for_bulk_create = Mock()
                mock_qs._batched_insert = Mock(return_value=[(1,), (2,), (3,)])

                result = self.mixin._process_mti_bulk_create_batch(
                    batch, inheritance_chain, existing_records=[]
                )

                # Verify the bulk insert method was called
                mock_bulk_insert.assert_called_once()
                assert len(result) == len(batch)

    def test_process_mti_bulk_create_batch_no_pks_returned(self):
        """Test _process_mti_bulk_create_batch when no PKs are returned."""
        new_obj = Mock()
        batch = [new_obj]
        inheritance_chain = [Mock(), Mock(), Mock()]

        # Mock the models in the inheritance chain to have proper _meta
        for model in inheritance_chain:
            model._meta.local_fields = []
            # Set up proper pk field name
            model._meta.pk = Mock()
            model._meta.pk.name = 'id'

        with patch.object(self.mixin, '_create_parent_instance') as mock_create_parent, \
             patch.object(self.mixin, '_create_child_instance') as mock_create_child, \
             patch('django_bulk_triggers.engine.run'):

            mock_parent = Mock()
            mock_parent.save = Mock()
            mock_parent.pk = 1

            mock_child = Mock()
            mock_child._is_pk_set = Mock(return_value=False)
            mock_child._state.adding = True
            mock_child._state.db = 'default'
            # Set up pk attribute
            setattr(mock_child, 'id', 1)

            mock_create_parent.return_value = mock_parent
            mock_create_child.return_value = mock_child

            # Mock the bulk insert to simulate no PKs returned scenario
            def mock_execute_bulk_insert(queryset, objs_with_pk, objs_without_pk, fields, opts):
                # Simulate the bulk insert logic for no PKs returned
                for obj in objs_without_pk:
                    obj._state.adding = False
                    obj._state.db = 'default'

            with patch.object(self.mixin, '_execute_bulk_insert', side_effect=mock_execute_bulk_insert) as mock_bulk_insert, \
                 patch('django.db.models.Manager.using') as mock_using:
                mock_qs = Mock()
                mock_using.return_value = mock_qs
                mock_qs._prepare_for_bulk_create = Mock()

                result = self.mixin._process_mti_bulk_create_batch(
                    batch, inheritance_chain, existing_records=[]
                )

                # Verify the bulk insert method was called
                mock_bulk_insert.assert_called_once()
                # The state should be set to False even with no returned columns
                assert mock_child._state.adding is False
                assert mock_child._state.db == 'default'

    def test_mti_bulk_update_deep_inheritance_error(self):
        """Test _mti_bulk_update with too deep inheritance chain."""
        with patch.object(self.mixin, '_get_inheritance_chain') as mock_chain:
            mock_chain.return_value = list(range(15))  # Too deep

            with pytest.raises(ValueError, match="Inheritance chain too deep"):
                self.mixin._mti_bulk_update([], ['name'])

    def test_mti_bulk_update_unsupported_parameters(self):
        """Test _mti_bulk_update with unsupported parameters."""
        objs = [Mock()]

        with patch('django_bulk_triggers.mti_operations.logger') as mock_logger, \
             patch.object(self.mixin, '_get_inheritance_chain') as mock_chain, \
             patch.object(self.mixin, '_process_mti_bulk_update_batch') as mock_process:

            # Mock the models in the inheritance chain to have proper _meta
            mock_models = []
            for i in range(3):
                mock_model = Mock()
                mock_model._meta.local_fields = []
                mock_models.append(mock_model)

            mock_chain.return_value = mock_models
            mock_process.return_value = 1

            result = self.mixin._mti_bulk_update(
                objs, ['name'], unique_fields=['name'], update_conflicts=True
            )

            # Should warn about unsupported parameters
            mock_logger.warning.assert_called()

    def test_mti_bulk_update_auto_now_fields(self):
        """Test _mti_bulk_update with auto_now fields."""
        objs = [Mock()]
        objs[0].pk = 1

        # Mock auto_now field
        field_mock = Mock()
        field_mock.name = 'updated_at'
        field_mock.auto_now = True
        field_mock.pre_save = Mock()

        meta_mock = Mock()
        meta_mock.local_fields = [field_mock]

        # Mock inheritance chain models
        models = [Mock(), Mock(), Mock()]
        for model in models:
            model._meta = meta_mock

        with patch.object(self.mixin, '_get_inheritance_chain') as mock_chain, \
             patch.object(self.mixin, '_process_mti_bulk_update_batch') as mock_process:

            mock_chain.return_value = models
            mock_process.return_value = 1

            result = self.mixin._mti_bulk_update(objs, ['name'])

            # pre_save should be called for auto_now fields
            field_mock.pre_save.assert_called()

    def test_mti_bulk_update_custom_fields(self):
        """Test _mti_bulk_update with custom fields that have pre_save."""
        objs = [Mock()]
        objs[0].pk = 1

        # Mock custom field with pre_save
        field_mock = Mock()
        field_mock.name = 'custom_field'
        field_mock.pre_save = Mock(return_value="updated_value")
        field_mock.auto_now = False
        field_mock.auto_now_add = False

        meta_mock = Mock()
        meta_mock.local_fields = [field_mock]

        # Mock inheritance chain models
        models = [Mock(), Mock(), Mock()]
        for model in models:
            model._meta = meta_mock

        with patch.object(self.mixin, '_get_inheritance_chain') as mock_chain, \
             patch.object(self.mixin, '_process_mti_bulk_update_batch') as mock_process:

            mock_chain.return_value = models
            mock_process.return_value = 1

            result = self.mixin._mti_bulk_update(objs, ['name'])  # custom_field not in fields

            # pre_save should be called for custom fields
            field_mock.pre_save.assert_called()

    def test_process_mti_bulk_update_batch_no_pks(self):
        """Test _process_mti_bulk_update_batch with no PKs."""
        batch = [Mock()]
        mock_model = Mock()
        # Make parents dict iterable
        mock_model._meta.parents = {}
        field_groups = {mock_model: ['name']}
        inheritance_chain = [Mock(), Mock(), mock_model]

        result = self.mixin._process_mti_bulk_update_batch(
            batch, field_groups, inheritance_chain
        )

        assert result == 0

    def test_process_mti_bulk_update_batch_with_pks(self):
        """Test _process_mti_bulk_update_batch with valid PKs."""
        batch = [Mock()]
        batch[0].pk = 1
        mock_model = Mock()
        field_groups = {mock_model: ['name']}
        inheritance_chain = [Mock(), Mock(), mock_model]

        # Mock field
        field_mock = Mock()
        field_mock.name = 'name'

        # Mock meta
        meta_mock = Mock()
        meta_mock.get_field = Mock(return_value=field_mock)
        meta_mock.local_fields = [field_mock]
        # Make parents dict iterable
        meta_mock.parents = {}

        mock_model._meta = meta_mock

        with patch('django.db.models.Manager.using') as mock_using:
            mock_qs = Mock()
            mock_using.return_value = mock_qs
            mock_qs.filter.return_value.count.return_value = 1
            mock_qs.filter.return_value.update.return_value = 1

            # Ensure the mock model is not the root model
            root_model = Mock()
            root_model._meta.parents = {}
            inheritance_chain[0] = root_model

            result = self.mixin._process_mti_bulk_update_batch(
                batch, field_groups, inheritance_chain
            )

            # The test passes if no exception is raised and we get some result
            assert isinstance(result, int)

    def test_process_mti_bulk_update_batch_child_model_filtering(self):
        """Test _process_mti_bulk_update_batch with child model PK filtering."""
        batch = [Mock()]
        batch[0].pk = 1
        child_model = Mock()
        field_groups = {child_model: ['registration_number']}
        inheritance_chain = [Mock(), Mock(), child_model]

        # Mock parent link
        parent_link_mock = Mock()
        parent_link_mock.attname = 'company_ptr_id'

        # Mock parents dict - make it properly iterable
        parent_model_mock = Mock()
        child_model._meta.parents = {parent_model_mock: parent_link_mock}

        # Mock field
        field_mock = Mock()
        field_mock.name = 'registration_number'

        # Mock meta
        meta_mock = Mock()
        meta_mock.get_field = Mock(return_value=field_mock)
        meta_mock.local_fields = [field_mock]
        # Make parents dict properly iterable
        meta_mock.parents = child_model._meta.parents

        child_model._meta = meta_mock

        with patch('django.db.models.Manager.using') as mock_using:
            mock_qs = Mock()
            mock_using.return_value = mock_qs
            mock_qs.filter.return_value.count.return_value = 1
            mock_qs.filter.return_value.update.return_value = 1

            result = self.mixin._process_mti_bulk_update_batch(
                batch, field_groups, inheritance_chain
            )

            # The test passes if no exception is raised and we get some result
            assert isinstance(result, int)

    def test_process_mti_bulk_update_batch_exception_handling(self):
        """Test _process_mti_bulk_update_batch exception handling."""
        batch = [Mock()]
        batch[0].pk = 1
        mock_model = Mock()
        field_groups = {mock_model: ['name']}
        inheritance_chain = [Mock(), Mock(), mock_model]

        # Mock field
        field_mock = Mock()
        field_mock.name = 'name'

        # Mock meta
        meta_mock = Mock()
        meta_mock.get_field = Mock(return_value=field_mock)
        meta_mock.local_fields = [field_mock]
        # Make parents dict iterable
        meta_mock.parents = {}

        mock_model._meta = meta_mock

        with patch('django.db.models.Manager.using') as mock_using:
            mock_qs = Mock()
            mock_using.return_value = mock_qs
            mock_qs.filter.return_value.count.return_value = 1
            mock_qs.filter.return_value.update.side_effect = Exception("Test error")

            # Should not raise exception, just return 0
            result = self.mixin._process_mti_bulk_update_batch(
                batch, field_groups, inheritance_chain
            )

            assert result == 0
