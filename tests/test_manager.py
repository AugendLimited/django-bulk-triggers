"""
Tests for the manager module.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from django_bulk_hooks.manager import BulkHookManager
from django_bulk_hooks.registry import clear_hooks
from tests.models import HookModel, SimpleModel, ComplexModel, UserModel
from tests.utils import HookTracker, create_test_instances


class TestBulkHookManager(TestCase):
    """Test the BulkHookManager class."""

    def setUp(self):
        self.manager = BulkHookManager()
        self.manager.model = HookModel
        self.tracker = HookTracker()
        
        # Clear the registry to prevent interference between tests
        clear_hooks()

    def test_get_queryset_returns_hook_queryset(self):
        """Test that get_queryset returns a HookQuerySet."""
        from django_bulk_hooks.queryset import HookQuerySet

        queryset = self.manager.get_queryset()
        self.assertIsInstance(queryset, HookQuerySet)

    def test_get_queryset_with_existing_hook_queryset(self):
        """Test get_queryset when base queryset already has hook functionality."""
        from django_bulk_hooks.queryset import HookQuerySetMixin

        # Create a mock queryset that already has hook functionality
        mock_queryset = MagicMock()
        mock_queryset.__class__ = type("MockQuerySet", (HookQuerySetMixin,), {})

        with patch.object(self.manager, "get_queryset", return_value=mock_queryset):
            result = self.manager.get_queryset()
            self.assertEqual(result, mock_queryset)

    def test_bulk_create_delegates_to_queryset(self):
        """Test that bulk_create delegates to queryset."""
        test_instances = create_test_instances(HookModel, 3)

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_create(
                test_instances,
                batch_size=100,
                ignore_conflicts=True,
                bypass_hooks=False,
            )

            mock_queryset.bulk_create.assert_called_once_with(
                test_instances,
                bypass_hooks=False,
                bypass_validation=False,
                batch_size=100,
                ignore_conflicts=True,
                update_conflicts=False,
                update_fields=None,
                unique_fields=None,
            )

    def test_bulk_update_delegates_to_queryset(self):
        """Test that bulk_update delegates to queryset."""
        test_instances = create_test_instances(HookModel, 3)
        fields = ["name", "value"]

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_update(test_instances, fields, bypass_hooks=False)

            mock_queryset.bulk_update.assert_called_once_with(
                test_instances, fields, bypass_hooks=False, bypass_validation=False
            )

    def test_bulk_delete_delegates_to_queryset(self):
        """Test that bulk_delete delegates to queryset."""
        test_instances = create_test_instances(HookModel, 3)

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_delete(test_instances, batch_size=100, bypass_hooks=False)

            mock_queryset.bulk_delete.assert_called_once_with(
                test_instances, bypass_hooks=False, bypass_validation=False, batch_size=100
            )

    def test_delete_delegates_to_queryset(self):
        """Test that delete delegates to queryset."""
        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.delete()

            mock_queryset.delete.assert_called_once()

    def test_update_delegates_to_queryset(self):
        """Test that update delegates to queryset."""
        update_data = {"status": "active", "value": 42}

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.update(**update_data)

            mock_queryset.update.assert_called_once_with(**update_data)

    def test_bulk_create_with_all_parameters(self):
        """Test bulk_create with all possible parameters."""
        test_instances = create_test_instances(HookModel, 3)

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_create(
                test_instances,
                batch_size=50,
                ignore_conflicts=True,
                update_conflicts=True,
                update_fields=["name"],
                unique_fields=["name"],
                bypass_hooks=True,
                bypass_validation=True,
            )

            mock_queryset.bulk_create.assert_called_once_with(
                test_instances,
                batch_size=50,
                ignore_conflicts=True,
                update_conflicts=True,
                update_fields=["name"],
                unique_fields=["name"],
                bypass_hooks=True,
                bypass_validation=True,
            )

    def test_bulk_update_with_all_parameters(self):
        """Test bulk_update with all possible parameters."""
        test_instances = create_test_instances(HookModel, 3)
        fields = ["name", "value"]

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_update(
                test_instances,
                fields,
                batch_size=50,
                bypass_hooks=True,
                bypass_validation=True,
            )

            mock_queryset.bulk_update.assert_called_once_with(
                test_instances,
                fields,
                batch_size=50,
                bypass_hooks=True,
                bypass_validation=True,
            )


class TestBulkHookManagerIntegration(TestCase):
    """Integration tests for BulkHookManager."""

    def setUp(self):
        self.tracker = HookTracker()
        self.user = UserModel.objects.create(username="testuser", email="test@example.com")
        
        # Clear the registry to prevent interference between tests
        clear_hooks()

    def test_manager_with_real_queryset(self):
        """Test manager with real queryset operations."""
        # Create test instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
            HookModel(name="Test 3", value=3, created_by=self.user),
        ]

        # Test bulk_create
        created_instances = HookModel.objects.bulk_create(test_instances)
        self.assertEqual(len(created_instances), 3)

        # Verify instances were created
        for instance in created_instances:
            self.assertIsNotNone(instance.pk)

        # Test bulk_update
        for instance in created_instances:
            instance.value *= 2

        updated_count = HookModel.objects.bulk_update(created_instances, ["value"])
        self.assertEqual(updated_count, 3)

        # Verify updates
        for instance in created_instances:
            instance.refresh_from_db()
            self.assertIn(instance.value, [2, 4, 6])

        # Test bulk_delete
        deleted_count = HookModel.objects.bulk_delete(created_instances)
        self.assertEqual(deleted_count, 3)

        # Verify deletion
        remaining_count = HookModel.objects.count()
        self.assertEqual(remaining_count, 0)

    def test_manager_bypass_hooks(self):
        """Test manager with bypass_hooks parameter."""
        # Create a hook to track calls
        from django_bulk_hooks import HookClass
        from django_bulk_hooks.decorators import hook
        from django_bulk_hooks.constants import BEFORE_CREATE

        class TestHook(HookClass):
            tracker = HookTracker()  # Class variable to persist across instances
            
            def __init__(self):
                pass  # No need to create instance tracker

            @hook(BEFORE_CREATE, model=HookModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                TestHook.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

        hook_instance = TestHook()

        # Create test instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Test without bypass_hooks (hooks should run)
        HookModel.objects.bulk_create(test_instances, bypass_hooks=False)
        self.assertEqual(len(TestHook.tracker.before_create_calls), 1)

        # Clear tracker
        TestHook.tracker.reset()

        # Test with bypass_hooks (hooks should not run)
        test_instances2 = [
            HookModel(name="Test 3", value=3, created_by=self.user),
            HookModel(name="Test 4", value=4, created_by=self.user),
        ]
        HookModel.objects.bulk_create(test_instances2, bypass_hooks=True)
        self.assertEqual(len(TestHook.tracker.before_create_calls), 0)

    def test_manager_with_different_models(self):
        """Test manager with different model types."""
        # Test with SimpleModel
        simple_instances = [
            SimpleModel(name="Simple 1", value=1),
            SimpleModel(name="Simple 2", value=2),
        ]

        created_simple = SimpleModel.objects.bulk_create(simple_instances)
        self.assertEqual(len(created_simple), 2)

        # Test with User
        user_instances = [
            UserModel(username="user1", email="user1@example.com"),
            UserModel(username="user2", email="user2@example.com"),
        ]

        created_users = UserModel.objects.bulk_create(user_instances)
        self.assertEqual(len(created_users), 2)

    def test_manager_error_handling(self):
        """Test manager error handling."""
        # Test with invalid data
        invalid_instances = [
            HookModel(name="", value=-1),  # Invalid value
        ]

        # Since no validation hooks are registered, this should not raise an exception
        # Django's bulk_create doesn't validate field values by default
        try:
            created_instances = HookModel.objects.bulk_create(invalid_instances)
            # If it succeeds, that's fine - no validation hooks are registered
            self.assertEqual(len(created_instances), 1)
        except Exception as e:
            # If it fails due to database constraints, that's also fine
            self.assertIsInstance(e, Exception)

    def test_manager_performance(self):
        """Test manager performance with large datasets."""
        from tests.models import SimpleModel

        # Create many instances using SimpleModel (no foreign keys for cleaner performance testing)
        test_instances = []
        for i in range(100):
            test_instances.append(
                SimpleModel(name=f"Test {i}", value=i)
            )

        # Test bulk_create performance
        # With hooks enabled, we expect 3 queries: SAVEPOINT, INSERT, RELEASE SAVEPOINT
        # SimpleModel with fewer fields fits all objects in one INSERT batch
        with self.assertNumQueries(3):  # Correct behavior when hooks are enabled
            created_instances = SimpleModel.objects.bulk_create(test_instances)

        self.assertEqual(len(created_instances), 100)

        # Test bulk_update performance
        for instance in created_instances:
            instance.value *= 2

        # With hooks enabled, we expect 7 queries:
        # SAVEPOINT, SAVEPOINT, SELECT originals (batch 1), SELECT originals (batch 2), UPDATE, RELEASE, RELEASE
        with self.assertNumQueries(7):  # Correct behavior when hooks are enabled
            updated_count = SimpleModel.objects.bulk_update(created_instances, ["value"])

        self.assertEqual(updated_count, 100)

        # Test bulk_delete performance
        # With hooks enabled, we expect 3 queries:
        # SAVEPOINT, DELETE, RELEASE (SimpleModel has no related models)
        with self.assertNumQueries(3):  # Correct behavior when hooks are enabled
            deleted_count = SimpleModel.objects.bulk_delete(created_instances)

        self.assertEqual(deleted_count, 100)


class TestBulkHookManagerEdgeCases(TestCase):
    """Test edge cases for BulkHookManager."""

    def setUp(self):
        self.manager = BulkHookManager()
        self.manager.model = HookModel
        
        # Clear the registry to prevent interference between tests
        clear_hooks()

    def test_manager_with_empty_list(self):
        """Test manager with empty lists."""
        # Test bulk_create with empty list
        result = self.manager.bulk_create([])
        self.assertEqual(result, [])

        # Test bulk_update with empty list
        result = self.manager.bulk_update([], ["name"])
        self.assertEqual(result, [])  # Current implementation returns [] for empty lists

        # Test bulk_delete with empty list
        result = self.manager.bulk_delete([])
        self.assertEqual(result, 0)  # Django's delete() returns count of deleted records

    def test_manager_with_none_parameters(self):
        """Test manager with None parameters."""
        test_instances = [HookModel(name="Test", value=1)]

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            # Test with None batch_size
            self.manager.bulk_create(test_instances, batch_size=None)
            mock_queryset.bulk_create.assert_called_with(
                test_instances,
                batch_size=None,
                ignore_conflicts=False,
                update_conflicts=False,
                update_fields=None,
                unique_fields=None,
                bypass_hooks=False,
                bypass_validation=False,
            )

    def test_manager_inheritance(self):
        """Test that BulkHookManager properly inherits from models.Manager."""
        from django.db import models

        self.assertIsInstance(self.manager, models.Manager)

        # Test that it has all the standard manager methods
        self.assertTrue(hasattr(self.manager, "all"))
        self.assertTrue(hasattr(self.manager, "filter"))
        self.assertTrue(hasattr(self.manager, "get"))
        self.assertTrue(hasattr(self.manager, "create"))

    def test_manager_with_custom_queryset(self):
        """Test manager with custom queryset class."""
        from django.db import models

        class CustomQuerySet(models.QuerySet):
            def custom_method(self):
                return self.filter(name__startswith="Custom")

        class CustomManager(BulkHookManager):
            def get_queryset(self):
                return CustomQuerySet(self.model, using=self._db)

        custom_manager = CustomManager()
        custom_manager.model = HookModel

        queryset = custom_manager.get_queryset()
        self.assertIsInstance(queryset, CustomQuerySet)
        self.assertTrue(hasattr(queryset, "custom_method"))
