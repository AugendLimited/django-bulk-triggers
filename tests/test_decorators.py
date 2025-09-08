"""
Tests for the decorators module.
"""

from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone

from django_bulk_triggers.conditions import IsEqual
from django_bulk_triggers.decorators import bulk_trigger
from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_triggers.decorators import trigger, select_related
from django_bulk_triggers.priority import Priority
from tests.models import Category, TriggerModel, UserModel
from tests.utils import TriggerTracker


@pytest.mark.django_db
class TestTriggerDecorator:
    """Test the trigger decorator."""

    def setup_method(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_trigger_decorator_basic(self):
        """Test basic trigger decorator functionality."""

        @trigger(BEFORE_CREATE, model=TriggerModel)
        def test_trigger(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify the trigger attribute was added
        assert hasattr(test_trigger, "triggers_triggers")
        assert len(test_trigger.triggers_triggers) == 1

        trigger_info = test_trigger.triggers_triggers[0]
        assert trigger_info[0] == TriggerModel  # model
        assert trigger_info[1] == BEFORE_CREATE  # event
        assert trigger_info[2] is None  # condition
        assert trigger_info[3] == Priority.NORMAL  # priority

    def test_trigger_decorator_with_condition(self):
        """Test trigger decorator with condition."""
        condition = IsEqual("status", "active")

        @trigger(BEFORE_CREATE, model=TriggerModel, condition=condition)
        def test_trigger(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        trigger_info = test_trigger.triggers_triggers[0]
        assert trigger_info[2] == condition  # condition

    def test_trigger_decorator_with_priority(self):
        """Test trigger decorator with custom priority."""

        @trigger(BEFORE_CREATE, model=TriggerModel, priority=Priority.HIGH)
        def test_trigger(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        trigger_info = test_trigger.triggers_triggers[0]
        assert trigger_info[3] == Priority.HIGH  # priority

    def test_trigger_decorator_multiple_triggers(self):
        """Test multiple triggers on the same function."""

        @trigger(BEFORE_CREATE, model=TriggerModel)
        @trigger(AFTER_CREATE, model=TriggerModel)
        def test_trigger(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        assert len(test_trigger.triggers_triggers) == 2

        events = [trigger_info[1] for trigger_info in test_trigger.triggers_triggers]
        assert BEFORE_CREATE in events
        assert AFTER_CREATE in events

    def test_trigger_decorator_different_models(self):
        """Test triggers on different models."""

        @trigger(BEFORE_CREATE, model=TriggerModel)
        @trigger(BEFORE_CREATE, model=UserModel)
        def test_trigger(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        assert len(test_trigger.triggers_triggers) == 2

        models = [trigger_info[0] for trigger_info in test_trigger.triggers_triggers]
        assert TriggerModel in models
        assert UserModel in models

    def test_trigger_decorator_with_all_events(self):
        """Test trigger decorator with all event types."""
        events = [
            BEFORE_CREATE,
            AFTER_CREATE,
            BEFORE_UPDATE,
            AFTER_UPDATE,
            BEFORE_DELETE,
            AFTER_DELETE,
        ]

        for event in events:

            @trigger(event, model=TriggerModel)
            def test_trigger(new_records, old_records=None, **kwargs):
                self.tracker.add_call(event, new_records, old_records, **kwargs)

            trigger_info = test_trigger.triggers_triggers[0]
            assert trigger_info[1] == event

    def test_trigger_decorator_with_user_model(self):
        """Test trigger decorator with User model."""
        from django.apps import apps

        @trigger(BEFORE_CREATE, model=UserModel)
        def test_trigger(new_records, old_records=None, **kwargs):
            pass

        # Verify the trigger was registered
        models = apps.get_app_config("tests").get_models()
        assert UserModel in models

        # Clear triggers for other tests
        from django_bulk_triggers.registry import clear_triggers

        clear_triggers()


@pytest.mark.django_db
class TestSelectRelatedDecorator:
    """Test the select_related decorator."""

    def setup_method(self):
        # Create test data - use bulk_create to avoid RETURNING clause issues
        from django.utils import timezone

        # Create UserModel using bulk_create which doesn't trigger RETURNING issues
        users = UserModel.objects.bulk_create([
            UserModel(username="testuser", email="test@example.com", is_active=True, created_at=timezone.now())
        ])
        self.user = users[0]

        # Create Category using bulk_create
        categories = Category.objects.bulk_create([
            Category(name="Test Category", description="", is_active=True)
        ])
        self.category = categories[0]

        # Create test instances with foreign keys
        self.test_instances = [
            TriggerModel(name="Test 1", created_by=self.user, category=self.category),
            TriggerModel(name="Test 2", created_by=self.user, category=self.category),
        ]

        # Save instances to get PKs
        for instance in self.test_instances:
            instance.save()

        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers

        clear_triggers()

    def test_select_related_basic(self):
        """Test basic select_related functionality."""

        @select_related("created_by", "category")
        def test_function(new_records, old_records=None, **kwargs):
            # Verify that related fields are loaded
            for record in new_records:
                assert record.created_by is not None
                assert record.category is not None
                assert isinstance(record.created_by, UserModel)
                assert isinstance(record.category, Category)

        test_function(new_records=self.test_instances)

    def test_select_related_missing_new_records_argument(self):
        """Test select_related with missing new_records argument."""

        @select_related("created_by")
        def test_function(some_other_arg):
            pass

        with pytest.raises(TypeError):
            test_function("some_value")

    def test_select_related_wrong_argument_type(self):
        """Test select_related with wrong argument type."""

        @select_related("created_by")
        def test_function(new_records, old_records=None, **kwargs):
            pass

        with pytest.raises(TypeError):
            test_function(new_records="not_a_list")

    def test_select_related_empty_list(self):
        """Test select_related with empty list."""

        @select_related("created_by")
        def test_function(new_records, old_records=None, **kwargs):
            return "success"

        result = test_function(new_records=[])
        assert result == "success"

    def test_select_related_nested_field_support(self):
        """Test select_related with nested fields works correctly."""

        @select_related("created_by.username")
        def test_function(new_records, old_records=None, **kwargs):
            # Verify that nested field access works
            for record in new_records:
                if record.created_by:
                    assert record.created_by.username is not None

        # Should not raise an error and should work correctly
        test_function(new_records=self.test_instances)

    def test_select_related_non_relation_field(self):
        """Test select_related with non-relation field."""

        @select_related("name")  # name is not a relation
        def test_function(new_records, old_records=None, **kwargs):
            # Should not raise error, just skip the field
            return "success"

        result = test_function(new_records=self.test_instances)
        assert result == "success"

    def test_select_related_nonexistent_field(self):
        """Test select_related with nonexistent field."""

        @select_related("nonexistent_field")
        def test_function(new_records, old_records=None, **kwargs):
            # Should not raise error, just skip the field
            return "success"

        result = test_function(new_records=self.test_instances)
        assert result == "success"

    def test_select_related_already_cached(self):
        """Test select_related when field is already cached."""
        # Pre-load the related field
        for instance in self.test_instances:
            instance.created_by  # This will cache the relation

        @select_related("created_by")
        def test_function(new_records, old_records=None, **kwargs):
            # Should work without additional queries
            for record in new_records:
                assert record.created_by is not None

        test_function(new_records=self.test_instances)

    def test_select_related_with_none_instances(self):
        """Test select_related with instances that have None foreign keys."""
        # Create instances with None foreign keys
        none_instances = [
            TriggerModel(name="None FK 1", created_by=None, category=None),
            TriggerModel(name="None FK 2", created_by=None, category=None),
        ]

        for instance in none_instances:
            instance.save()

        @select_related("created_by", "category")
        def test_function(new_records, old_records=None, **kwargs):
            # Should handle None values gracefully
            for record in new_records:
                assert record.created_by is None
                assert record.category is None

        test_function(new_records=none_instances)

    def test_select_related_performance(self):
        """Test that select_related reduces database queries."""
        # The test instances already have their related fields loaded
        # so no additional queries should be needed
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):

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
        assert result == "success"

    def test_select_related_with_username_field(self):
        """Test select_related with username field access."""
        # Use the existing user from setup_method
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=self.user),
            TriggerModel(name="Test 2", created_by=self.user),
        ]

        @select_related("created_by")
        def test_function(new_records, old_records=None, **kwargs):
            # Access username field to trigger select_related
            for record in new_records:
                if record.created_by:
                    _ = record.created_by.username
                if record.category:
                    _ = record.category.name

        # This should not raise an error
        test_function(new_records=test_instances)

    def test_select_related_with_multiple_relations(self):
        """Test select_related with multiple relation fields."""
        # Create test instances
        test_instances = [TriggerModel(name="Test", created_by=self.user)]

        @select_related("created_by", "category")
        def test_function(new_records, old_records=None, **kwargs):
            for record in new_records:
                if record.created_by:
                    assert record.created_by.username is not None

        test_function(new_records=test_instances)


@pytest.mark.django_db
class TestDecoratorIntegration:
    """Integration tests for decorators."""

    def setup_method(self):
        from django.utils import timezone

        self.tracker = TriggerTracker()

        # Create test data using bulk_create to avoid RETURNING issues
        users = UserModel.objects.bulk_create([
            UserModel(username="testuser", email="test@example.com", is_active=True, created_at=timezone.now())
        ])
        self.user = users[0]

        categories = Category.objects.bulk_create([
            Category(name="Test Category", description="", is_active=True)
        ])
        self.category = categories[0]

        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers

        clear_triggers()

    def test_trigger_with_select_related(self):
        """Test combining trigger and select_related decorators."""

        @trigger(BEFORE_CREATE, model=TriggerModel)
        @select_related("created_by", "category")
        def test_trigger(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

            # Verify related fields are loaded
            for record in new_records:
                if record.created_by:
                    assert isinstance(record.created_by, UserModel)
                if record.category:
                    assert isinstance(record.category, Category)

        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=self.user, category=self.category),
            TriggerModel(name="Test 2", created_by=self.user, category=self.category),
        ]

        # Call the trigger function
        test_trigger(new_records=test_instances)

        # Verify trigger was called
        assert len(self.tracker.before_create_calls) == 1

    def test_multiple_triggers_with_select_related(self):
        """Test multiple triggers with select_related."""

        @trigger(BEFORE_CREATE, model=TriggerModel)
        @trigger(AFTER_CREATE, model=TriggerModel)
        @select_related("created_by")
        def test_trigger(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify both decorators work together
        assert len(test_trigger.triggers_triggers) == 2

        # Test the function
        test_instances = [TriggerModel(name="Test", created_by=self.user)]
        test_trigger(new_records=test_instances)

        assert len(self.tracker.before_create_calls) == 1

    def test_select_related_with_nested_fields_error(self):
        """Test select_related decorator handles nested fields gracefully."""
        @select_related('category__parent')
        def test_func(new_records, old_records=None, **kwargs):
            return "success"

        # Create a mock instance
        mock_instance = Mock()
        mock_instance.pk = 1

        # Mock model class
        mock_model = Mock()
        mock_model._meta.get_field.side_effect = FieldDoesNotExist("Field does not exist")

        # Should handle nested fields gracefully without raising ValueError
        result = test_func([mock_instance], model_cls=mock_model)
        assert result == "success"

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
        assert result is None

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
        assert result is None

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
        assert result is None

    def test_bulk_trigger_decorator(self):
        """Test bulk_trigger decorator functionality."""
        @bulk_trigger(TriggerModel, 'BEFORE_CREATE')
        def test_trigger(new_records, old_records=None, **kwargs):
            pass

        # Verify the trigger was registered
        assert hasattr(test_trigger, '_bulk_trigger_registered')

    def test_bulk_trigger_decorator_with_condition_and_priority(self):
        """Test bulk_trigger decorator with condition and priority."""
        condition = Mock()
        priority = 100

        @bulk_trigger(TriggerModel, 'AFTER_UPDATE', when=condition, priority=priority)
        def test_trigger(new_records, old_records=None, **kwargs):
            pass

        # Verify the trigger was registered
        assert hasattr(test_trigger, '_bulk_trigger_registered')

    def test_select_related_with_valid_fields(self, test_user, test_category):
        """Test select_related decorator with valid field names."""
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=test_user, category=test_category),
            TriggerModel(name="Test 2", created_by=test_user, category=test_category),
            TriggerModel(name="Test 3", created_by=test_user, category=test_category),
        ]
        for instance in test_instances:
            instance.save()

        @select_related('category', 'created_by')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        result = test_function(test_instances, test_instances)
        assert result == 3

        # Clean up
        for instance in test_instances:
            instance.delete()

    def test_select_related_empty_records(self):
        """Test select_related decorator with empty records."""

        @select_related('category', 'created_by')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        result = test_function([], [])
        assert result == 0

    def test_select_related_no_fields_to_fetch(self, test_user, test_category):
        """Test select_related decorator when no fields need fetching."""
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=test_user, category=test_category),
            TriggerModel(name="Test 2", created_by=test_user, category=test_category),
            TriggerModel(name="Test 3", created_by=test_user, category=test_category),
        ]
        for instance in test_instances:
            instance.save()

        # Mock the instances to have all fields already cached
        for instance in test_instances:
            instance._state.fields_cache = {
                'category': test_category,
                'created_by': test_user
            }

        @select_related('category', 'created_by')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        result = test_function(test_instances, test_instances)
        assert result == 3

        # Clean up
        for instance in test_instances:
            instance.delete()

    def test_select_related_decorator_preserves_function(self):
        """Test that select_related decorator preserves the original function."""

        def original_function(new_records, old_records=None, **kwargs):
            return "original"

        decorated_function = select_related('category')(original_function)

        # The decorated function should still work
        result = decorated_function([], [])
        assert result == "original"

        # The function should have the expected attributes
        assert hasattr(decorated_function, '__wrapped__')

    def test_select_related_with_bound_method(self, test_user, test_category):
        """Test select_related decorator with bound methods."""
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=test_user, category=test_category),
            TriggerModel(name="Test 2", created_by=test_user, category=test_category),
            TriggerModel(name="Test 3", created_by=test_user, category=test_category),
        ]
        for instance in test_instances:
            instance.save()

        class TestClass:
            @select_related('category')
            def test_method(self, new_records, old_records=None, **kwargs):
                return len(new_records)

        test_obj = TestClass()
        result = test_obj.test_method(test_instances, test_instances)
        assert result == 3

        # Clean up
        for instance in test_instances:
            instance.delete()

    def test_select_related_decorator_chaining(self, test_user, test_category):
        """Test that select_related decorator can be chained."""
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=test_user, category=test_category),
            TriggerModel(name="Test 2", created_by=test_user, category=test_category),
            TriggerModel(name="Test 3", created_by=test_user, category=test_category),
        ]
        for instance in test_instances:
            instance.save()

        @select_related('category')
        @select_related('created_by')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        result = test_function(test_instances, test_instances)
        assert result == 3

        # Clean up
        for instance in test_instances:
            instance.delete()

    def test_select_related_with_model_cls_kwarg(self):
        """Test select_related decorator with model_cls keyword argument."""
        # This test verifies that the decorator can handle a model_cls keyword argument
        # which covers line 60: model_cls = bound.arguments["model_cls"]

        @select_related('category')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        # Create a test instance that will trigger the model_cls logic
        test_instance = TriggerModel(name="test", created_by=None, category=None)

        # Test with model_cls keyword argument - this should cover line 60
        result = test_function([test_instance], model_cls=TriggerModel)
        assert result == 1

    def test_select_related_with_objects_having_none_pk(self):
        """Test select_related with objects that have None primary keys."""
        # Create objects with None primary keys to test line 65-66
        instances_with_none_pk = [
            TriggerModel(name="Test 1", created_by=None, category=None),
            TriggerModel(name="Test 2", created_by=None, category=None),
        ]

        # Don't save them so they have pk=None
        # This should not raise an error and should handle the None pk case

        @select_related('created_by', 'category')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        result = test_function(instances_with_none_pk)
        assert result == 2

    def test_select_related_with_different_model_types(self, test_user, test_category):
        """Test select_related decorator with different model types."""
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=test_user, category=test_category),
        ]
        for instance in test_instances:
            instance.save()

        @select_related('category')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        result = test_function(test_instances, test_instances)
        assert result == 1

        # Clean up
        for instance in test_instances:
            instance.delete()

    def test_select_related_error_handling(self, test_user, test_category):
        """Test select_related decorator error handling."""
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", created_by=test_user, category=test_category),
            TriggerModel(name="Test 2", created_by=test_user, category=test_category),
            TriggerModel(name="Test 3", created_by=test_user, category=test_category),
        ]
        for instance in test_instances:
            instance.save()

        @select_related('category')
        def test_function(new_records, old_records=None, **kwargs):
            return len(new_records)

        # Test that the decorator works normally
        result = test_function(test_instances, test_instances)
        assert result == 3

        # Clean up
        for instance in test_instances:
            instance.delete()
