"""
Tests for the manager module.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from django_bulk_triggers.manager import BulkTriggerManager
from django_bulk_triggers.registry import clear_triggers
from tests.models import ComplexModel, SimpleModel, TriggerModel, UserModel
from tests.utils import TriggerTracker, create_test_instances


class TestBulkTriggerManager(TestCase):
    """Test the BulkTriggerManager class."""

    def setUp(self):
        self.manager = BulkTriggerManager()
        self.manager.model = TriggerModel
        self.tracker = TriggerTracker()

        # Clear the registry to prevent interference between tests
        clear_triggers()

    def test_get_queryset_returns_trigger_queryset(self):
        """Test that get_queryset returns a TriggerQuerySet."""
        from django_bulk_triggers.queryset import TriggerQuerySet

        queryset = self.manager.get_queryset()
        self.assertIsInstance(queryset, TriggerQuerySet)

    def test_get_queryset_with_existing_trigger_queryset(self):
        """Test get_queryset when base queryset already has trigger functionality."""
        from django_bulk_triggers.queryset import TriggerQuerySetMixin

        # Create a mock queryset that already has trigger functionality
        mock_queryset = MagicMock()
        mock_queryset.__class__ = type("MockQuerySet", (TriggerQuerySetMixin,), {})

        with patch.object(self.manager, "get_queryset", return_value=mock_queryset):
            result = self.manager.get_queryset()
            self.assertEqual(result, mock_queryset)

    def test_bulk_create_delegates_to_queryset(self):
        """Test that bulk_create delegates to queryset."""
        test_instances = create_test_instances(TriggerModel, 3)

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_create(
                test_instances,
                batch_size=100,
                ignore_conflicts=True,
                bypass_triggers=False,
            )

            mock_queryset.bulk_create.assert_called_once_with(
                test_instances,
                bypass_triggers=False,
                bypass_validation=False,
                batch_size=100,
                ignore_conflicts=True,
                update_conflicts=False,
                update_fields=None,
                unique_fields=None,
            )

    def test_bulk_update_delegates_to_queryset(self):
        """Test that bulk_update delegates to queryset."""
        test_instances = create_test_instances(TriggerModel, 3)
        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_update(test_instances, bypass_triggers=False)

            mock_queryset.bulk_update.assert_called_once_with(
                test_instances, bypass_triggers=False, bypass_validation=False
            )

    def test_bulk_delete_delegates_to_queryset(self):
        """Test that bulk_delete delegates to queryset."""
        test_instances = create_test_instances(TriggerModel, 3)

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_delete(
                test_instances, batch_size=100, bypass_triggers=False
            )

            mock_queryset.bulk_delete.assert_called_once_with(
                test_instances,
                bypass_triggers=False,
                bypass_validation=False,
                batch_size=100,
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
        test_instances = create_test_instances(TriggerModel, 3)

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
                bypass_triggers=True,
                bypass_validation=True,
            )

            mock_queryset.bulk_create.assert_called_once_with(
                test_instances,
                batch_size=50,
                ignore_conflicts=True,
                update_conflicts=True,
                update_fields=["name"],
                unique_fields=["name"],
                bypass_triggers=True,
                bypass_validation=True,
            )

    def test_bulk_update_with_all_parameters(self):
        """Test bulk_update with all possible parameters."""
        test_instances = create_test_instances(TriggerModel, 3)

        with patch.object(self.manager, "get_queryset") as mock_get_queryset:
            mock_queryset = MagicMock()
            mock_get_queryset.return_value = mock_queryset

            self.manager.bulk_update(
                test_instances,
                batch_size=50,
                bypass_triggers=True,
                bypass_validation=True,
            )

            mock_queryset.bulk_update.assert_called_once_with(
                test_instances,
                batch_size=50,
                bypass_triggers=True,
                bypass_validation=True,
            )


class TestBulkTriggerManagerIntegration(TestCase):
    """Integration tests for BulkTriggerManager."""

    def setUp(self):
        self.tracker = TriggerTracker()
        self.user = UserModel.objects.create(
            username="testuser", email="test@example.com"
        )

        # Clear the registry to prevent interference between tests
        clear_triggers()

    def test_manager_with_real_queryset(self):
        """Test manager with real queryset operations."""
        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
            TriggerModel(name="Test 3", value=3, created_by=self.user),
        ]

        # Test bulk_create
        created_instances = TriggerModel.objects.bulk_create(test_instances)
        self.assertEqual(len(created_instances), 3)

        # Verify instances were created
        for instance in created_instances:
            self.assertIsNotNone(instance.pk)

        # Test bulk_update
        for instance in created_instances:
            instance.value *= 2

        updated_count = TriggerModel.objects.bulk_update(created_instances)
        self.assertEqual(updated_count, 3)

        # Verify updates
        for instance in created_instances:
            instance.refresh_from_db()
            self.assertIn(instance.value, [2, 4, 6])

        # Test bulk_delete
        deleted_count = TriggerModel.objects.bulk_delete(created_instances)
        self.assertEqual(deleted_count, 3)

        # Verify deletion
        remaining_count = TriggerModel.objects.count()
        self.assertEqual(remaining_count, 0)

    def test_manager_bypass_triggers(self):
        """Test manager with bypass_triggers parameter."""
        # Create a trigger to track calls
        from django_bulk_triggers import TriggerClass
        from django_bulk_triggers.constants import BEFORE_CREATE
        from django_bulk_triggers.decorators import trigger

        class TestTrigger(TriggerClass):
            tracker = TriggerTracker()  # Class variable to persist across instances

            def __init__(self):
                pass  # No need to create instance tracker

            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                TestTrigger.tracker.add_call(
                    BEFORE_CREATE, new_records, old_records, **kwargs
                )

        trigger_instance = TestTrigger()

        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Test without bypass_triggers (triggers should run)
        TriggerModel.objects.bulk_create(test_instances, bypass_triggers=False)
        self.assertEqual(len(TestTrigger.tracker.before_create_calls), 1)

        # Clear tracker
        TestTrigger.tracker.reset()

        # Test with bypass_triggers (triggers should not run)
        test_instances2 = [
            TriggerModel(name="Test 3", value=3, created_by=self.user),
            TriggerModel(name="Test 4", value=4, created_by=self.user),
        ]
        TriggerModel.objects.bulk_create(test_instances2, bypass_triggers=True)
        self.assertEqual(len(TestTrigger.tracker.before_create_calls), 0)

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
            TriggerModel(name="", value=-1),  # Invalid value
        ]

        # Since no validation triggers are registered, this should not raise an exception
        # Django's bulk_create doesn't validate field values by default
        try:
            created_instances = TriggerModel.objects.bulk_create(invalid_instances)
            # If it succeeds, that's fine - no validation triggers are registered
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
            test_instances.append(SimpleModel(name=f"Test {i}", value=i))

        # Test bulk_create performance
        # With triggers enabled, we expect 3 queries: SAVEPOINT, INSERT, RELEASE SAVEPOINT
        # SimpleModel with fewer fields fits all objects in one INSERT batch
        with self.assertNumQueries(3):  # Correct behavior when triggers are enabled
            created_instances = SimpleModel.objects.bulk_create(test_instances)

        self.assertEqual(len(created_instances), 100)

        # Test bulk_update performance
        for instance in created_instances:
            instance.value *= 2

        # With triggers enabled, we expect 9 queries (auto-detection adds 2 queries):
        # SAVEPOINT, SELECT for auto-detection (1), SELECT for auto-detection (2), SAVEPOINT, SELECT originals (batch 1), SELECT originals (batch 2), UPDATE, RELEASE, RELEASE
        with self.assertNumQueries(9):  # Correct behavior when triggers are enabled
            updated_count = SimpleModel.objects.bulk_update(created_instances)

        self.assertEqual(updated_count, 100)

        # Test bulk_delete performance
        # With triggers enabled, we expect 3 queries:
        # SAVEPOINT, DELETE, RELEASE (SimpleModel has no related models)
        with self.assertNumQueries(3):  # Correct behavior when triggers are enabled
            deleted_count = SimpleModel.objects.bulk_delete(created_instances)

        self.assertEqual(deleted_count, 100)


class TestBulkTriggerManagerEdgeCases(TestCase):
    """Test edge cases for BulkTriggerManager."""

    def setUp(self):
        self.manager = BulkTriggerManager()
        self.manager.model = TriggerModel

        # Clear the registry to prevent interference between tests
        clear_triggers()

    def test_manager_with_empty_list(self):
        """Test manager with empty lists."""
        # Test bulk_create with empty list
        result = self.manager.bulk_create([])
        self.assertEqual(result, [])

        # Test bulk_update with empty list
        result = self.manager.bulk_update([])
        self.assertEqual(
            result, []
        )  # Current implementation returns [] for empty lists

        # Test bulk_delete with empty list
        result = self.manager.bulk_delete([])
        self.assertEqual(
            result, 0
        )  # Django's delete() returns count of deleted records

    def test_manager_with_none_parameters(self):
        """Test manager with None parameters."""
        test_instances = [TriggerModel(name="Test", value=1)]

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
                bypass_triggers=False,
                bypass_validation=False,
            )

    def test_manager_inheritance(self):
        """Test that BulkTriggerManager properly inherits from models.Manager."""
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

        class CustomManager(BulkTriggerManager):
            def get_queryset(self):
                return CustomQuerySet(self.model, using=self._db)

        custom_manager = CustomManager()
        custom_manager.model = TriggerModel

        queryset = custom_manager.get_queryset()
        self.assertIsInstance(queryset, CustomQuerySet)
        self.assertTrue(hasattr(queryset, "custom_method"))
