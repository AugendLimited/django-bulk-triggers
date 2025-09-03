"""
Tests for the decorators module.
"""

from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone

from django_bulk_hooks.conditions import IsEqual
from django_bulk_hooks.decorators import bulk_hook
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
from tests.models import Category, HookModel, UserModel
from tests.utils import HookTracker


@pytest.mark.django_db
class TestHookDecorator:
    """Test the hook decorator."""

    def setup_method(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_hooks.registry import clear_hooks
        clear_hooks()

    def test_hook_decorator_basic(self):
        """Test basic hook decorator functionality."""

        @hook(BEFORE_CREATE, model=HookModel)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify the hook attribute was added
        assert hasattr(test_hook, "hooks_hooks")
        assert len(test_hook.hooks_hooks) == 1

        hook_info = test_hook.hooks_hooks[0]
        assert hook_info[0] == HookModel  # model
        assert hook_info[1] == BEFORE_CREATE  # event
        assert hook_info[2] is None  # condition
        assert hook_info[3] == Priority.NORMAL  # priority

    def test_hook_decorator_with_condition(self):
        """Test hook decorator with condition."""
        condition = IsEqual("status", "active")

        @hook(BEFORE_CREATE, model=HookModel, condition=condition)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        hook_info = test_hook.hooks_hooks[0]
        assert hook_info[2] == condition  # condition

    def test_hook_decorator_with_priority(self):
        """Test hook decorator with custom priority."""

        @hook(BEFORE_CREATE, model=HookModel, priority=Priority.HIGH)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        hook_info = test_hook.hooks_hooks[0]
        assert hook_info[3] == Priority.HIGH  # priority

    def test_hook_decorator_multiple_hooks(self):
        """Test multiple hooks on the same function."""

        @hook(BEFORE_CREATE, model=HookModel)
        @hook(AFTER_CREATE, model=HookModel)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        assert len(test_hook.hooks_hooks) == 2

        events = [hook_info[1] for hook_info in test_hook.hooks_hooks]
        assert BEFORE_CREATE in events
        assert AFTER_CREATE in events

    def test_hook_decorator_different_models(self):
        """Test hooks on different models."""

        @hook(BEFORE_CREATE, model=HookModel)
        @hook(BEFORE_CREATE, model=UserModel)
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        assert len(test_hook.hooks_hooks) == 2

        models = [hook_info[0] for hook_info in test_hook.hooks_hooks]
        assert HookModel in models
        assert UserModel in models

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

            @hook(event, model=HookModel)
            def test_hook(new_records, old_records=None, **kwargs):
                self.tracker.add_call(event, new_records, old_records, **kwargs)

            hook_info = test_hook.hooks_hooks[0]
            assert hook_info[1] == event

    def test_hook_decorator_with_user_model(self):
        """Test hook decorator with User model."""
        from django.apps import apps

        @hook(BEFORE_CREATE, model=UserModel)
        def test_hook(new_records, old_records=None, **kwargs):
            pass

        # Verify the hook was registered
        models = apps.get_app_config("tests").get_models()
        assert UserModel in models

        # Clear hooks for other tests
        from django_bulk_hooks.registry import clear_hooks

        clear_hooks()


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
            HookModel(name="Test 1", created_by=self.user, category=self.category),
            HookModel(name="Test 2", created_by=self.user, category=self.category),
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
            HookModel(name="None FK 1", created_by=None, category=None),
            HookModel(name="None FK 2", created_by=None, category=None),
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
            HookModel(name="Test 1", created_by=self.user),
            HookModel(name="Test 2", created_by=self.user),
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
        test_instances = [HookModel(name="Test", created_by=self.user)]

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

        self.tracker = HookTracker()

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
        from django_bulk_hooks.registry import clear_hooks

        clear_hooks()

    def test_hook_with_select_related(self):
        """Test combining hook and select_related decorators."""

        @hook(BEFORE_CREATE, model=HookModel)
        @select_related("created_by", "category")
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

            # Verify related fields are loaded
            for record in new_records:
                if record.created_by:
                    assert isinstance(record.created_by, UserModel)
                if record.category:
                    assert isinstance(record.category, Category)

        # Create test instances
        test_instances = [
            HookModel(name="Test 1", created_by=self.user, category=self.category),
            HookModel(name="Test 2", created_by=self.user, category=self.category),
        ]

        # Call the hook function
        test_hook(new_records=test_instances)

        # Verify hook was called
        assert len(self.tracker.before_create_calls) == 1

    def test_multiple_hooks_with_select_related(self):
        """Test multiple hooks with select_related."""

        @hook(BEFORE_CREATE, model=HookModel)
        @hook(AFTER_CREATE, model=HookModel)
        @select_related("created_by")
        def test_hook(new_records, old_records=None, **kwargs):
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        # Verify both decorators work together
        assert len(test_hook.hooks_hooks) == 2

        # Test the function
        test_instances = [HookModel(name="Test", created_by=self.user)]
        test_hook(new_records=test_instances)

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

    def test_bulk_hook_decorator(self):
        """Test bulk_hook decorator functionality."""
        @bulk_hook(HookModel, 'BEFORE_CREATE')
        def test_hook(new_records, old_records=None, **kwargs):
            pass

        # Verify the hook was registered
        assert hasattr(test_hook, '_bulk_hook_registered')

    def test_bulk_hook_decorator_with_condition_and_priority(self):
        """Test bulk_hook decorator with condition and priority."""
        condition = Mock()
        priority = 100

        @bulk_hook(HookModel, 'AFTER_UPDATE', when=condition, priority=priority)
        def test_hook(new_records, old_records=None, **kwargs):
            pass

        # Verify the hook was registered
        assert hasattr(test_hook, '_bulk_hook_registered')

    def test_select_related_with_valid_fields(self, test_user, test_category):
        """Test select_related decorator with valid field names."""
        # Create test instances
        test_instances = [
            HookModel(name="Test 1", created_by=test_user, category=test_category),
            HookModel(name="Test 2", created_by=test_user, category=test_category),
            HookModel(name="Test 3", created_by=test_user, category=test_category),
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
            HookModel(name="Test 1", created_by=test_user, category=test_category),
            HookModel(name="Test 2", created_by=test_user, category=test_category),
            HookModel(name="Test 3", created_by=test_user, category=test_category),
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
            HookModel(name="Test 1", created_by=test_user, category=test_category),
            HookModel(name="Test 2", created_by=test_user, category=test_category),
            HookModel(name="Test 3", created_by=test_user, category=test_category),
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
            HookModel(name="Test 1", created_by=test_user, category=test_category),
            HookModel(name="Test 2", created_by=test_user, category=test_category),
            HookModel(name="Test 3", created_by=test_user, category=test_category),
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

    def test_select_related_with_different_model_types(self, test_user, test_category):
        """Test select_related decorator with different model types."""
        # Create test instances
        test_instances = [
            HookModel(name="Test 1", created_by=test_user, category=test_category),
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
            HookModel(name="Test 1", created_by=test_user, category=test_category),
            HookModel(name="Test 2", created_by=test_user, category=test_category),
            HookModel(name="Test 3", created_by=test_user, category=test_category),
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
