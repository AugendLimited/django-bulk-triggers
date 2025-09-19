"""
Tests for django_bulk_signals.queryset module.
"""

from unittest.mock import Mock, patch

from django.db import models
from django.dispatch import receiver
from django.test import TestCase
from django_bulk_signals.models import BulkSignalModel
from django_bulk_signals.queryset import BulkSignalQuerySet
from django_bulk_signals.signals import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)

from tests.models import QuerySetTestModel, TestModelWithAutoNow


class TestBulkSignalQuerySet(TestCase):
    """Test cases for BulkSignalQuerySet."""

    def setUp(self):
        """Set up test data."""
        self.model = QuerySetTestModel
        self.queryset = self.model.objects.get_queryset()

        # Create test instances
        self.instance1 = QuerySetTestModel(name="test1", value=10)
        self.instance1.pk = 1
        self.instance2 = QuerySetTestModel(name="test2", value=20)
        self.instance2.pk = 2

        self.instances = [self.instance1, self.instance2]

    def test_bulk_create_with_empty_objects(self):
        """Test bulk_create with empty objects list."""
        from django_bulk_signals.queryset import BulkSignalQuerySet

        # Create a queryset instance
        qs = BulkSignalQuerySet(self.model)

        # Test with empty objects list - should return empty list (not 0)
        result = qs.bulk_create([])
        self.assertEqual(result, [])

    def test_bulk_update_with_empty_objects(self):
        """Test bulk_update with empty objects list."""
        from django_bulk_signals.queryset import BulkSignalQuerySet

        # Create a queryset instance
        qs = BulkSignalQuerySet(self.model)

        # Test with empty objects list - should return 0
        result = qs.bulk_update([], fields=["name"])
        self.assertEqual(result, 0)

    def test_bulk_delete_with_empty_objects(self):
        """Test bulk_delete with empty objects list."""
        from django_bulk_signals.queryset import BulkSignalQuerySet

        # Create a queryset instance
        qs = BulkSignalQuerySet(self.model)

        # Test with empty objects list
        result = qs.bulk_delete([])
        self.assertEqual(result, 0)

    def test_bulk_delete_with_objects_without_pks(self):
        """Test bulk_delete with objects that have no primary keys."""
        from django_bulk_signals.queryset import BulkSignalQuerySet

        # Create a queryset instance
        qs = BulkSignalQuerySet(self.model)

        # Create instances without primary keys
        instance1 = QuerySetTestModel(name="test1", value=10)
        instance1.pk = None
        instance2 = QuerySetTestModel(name="test2", value=20)
        instance2.pk = None

        instances = [instance1, instance2]

        with patch("django_bulk_signals.queryset.logger") as mock_logger:
            result = qs.bulk_delete(instances)

            # Should log warning about no objects with primary keys
            mock_logger.warning.assert_called_with(
                "bulk_delete: No objects with primary keys to delete"
            )
            self.assertEqual(result, 0)

    def test_bulk_update_with_missing_original_warning(self):
        """Test bulk_update logs warning when original instance is missing."""
        from unittest.mock import MagicMock, patch

        # Create a queryset instance
        qs = BulkSignalQuerySet(self.model)

        # Create an instance with a primary key that doesn't exist in DB
        instance = QuerySetTestModel(name="test", value=10)
        instance.pk = 999  # Non-existent PK

        instances = [instance]

        # Mock the model.objects.filter to return empty queryset and super().bulk_update
        with (
            patch.object(self.model.objects, "filter") as mock_filter,
            patch("django_bulk_signals.queryset.logger") as mock_logger,
            patch.object(
                qs.__class__.__bases__[0], "bulk_update"
            ) as mock_super_bulk_update,
        ):
            # Mock the filter to return empty queryset (no originals found)
            mock_filter.return_value = []
            # Mock the super().bulk_update to return 0
            mock_super_bulk_update.return_value = 0

            result = qs.bulk_update(instances, ["name"])

            # Should log warning about missing original
            mock_logger.warning.assert_called_with(
                "bulk_update: No original found for object 999"
            )
            self.assertEqual(result, 0)


class TestBulkSignalReceivers(TestCase):
    """Test that signal receivers actually work."""

    def setUp(self):
        """Set up test data and receivers."""
        self.model = QuerySetTestModel
        self.queryset = self.model.objects.get_queryset()

        # Track signal calls
        self.pre_create_calls = []
        self.post_create_calls = []
        self.pre_update_calls = []
        self.post_update_calls = []
        self.pre_delete_calls = []
        self.post_delete_calls = []

        # Store receiver references to prevent garbage collection
        self.receivers = []

        # Connect receivers
        self._connect_receivers()

    def _connect_receivers(self):
        """Connect test receivers to signals."""

        def test_pre_create_receiver(sender, instances, **kwargs):
            self.pre_create_calls.append(
                {"sender": sender, "instances": instances, "kwargs": kwargs}
            )

        def test_post_create_receiver(sender, instances, **kwargs):
            self.post_create_calls.append(
                {"sender": sender, "instances": instances, "kwargs": kwargs}
            )

        def test_pre_update_receiver(sender, instances, originals, fields, **kwargs):
            self.pre_update_calls.append(
                {
                    "sender": sender,
                    "instances": instances,
                    "originals": originals,
                    "fields": fields,
                    "kwargs": kwargs,
                }
            )

        def test_post_update_receiver(sender, instances, originals, fields, **kwargs):
            self.post_update_calls.append(
                {
                    "sender": sender,
                    "instances": instances,
                    "originals": originals,
                    "fields": fields,
                    "kwargs": kwargs,
                }
            )

        def test_pre_delete_receiver(sender, instances, **kwargs):
            self.pre_delete_calls.append(
                {"sender": sender, "instances": instances, "kwargs": kwargs}
            )

        def test_post_delete_receiver(sender, instances, **kwargs):
            self.post_delete_calls.append(
                {"sender": sender, "instances": instances, "kwargs": kwargs}
            )

        # Store receiver references to prevent garbage collection
        self.receivers = [
            test_pre_create_receiver,
            test_post_create_receiver,
            test_pre_update_receiver,
            test_post_update_receiver,
            test_pre_delete_receiver,
            test_post_delete_receiver,
        ]

        # Connect receivers
        bulk_pre_create.connect(test_pre_create_receiver, sender=self.model)
        bulk_post_create.connect(test_post_create_receiver, sender=self.model)
        bulk_pre_update.connect(test_pre_update_receiver, sender=self.model)
        bulk_post_update.connect(test_post_update_receiver, sender=self.model)
        bulk_pre_delete.connect(test_pre_delete_receiver, sender=self.model)
        bulk_post_delete.connect(test_post_delete_receiver, sender=self.model)

    def test_bulk_create_signals(self):
        """Test that bulk_create fires pre and post signals."""
        # Create test objects
        obj1 = QuerySetTestModel(name="test1", value=10)
        obj2 = QuerySetTestModel(name="test2", value=20)
        objs = [obj1, obj2]

        # Clear previous calls
        self.pre_create_calls.clear()
        self.post_create_calls.clear()

        # Perform bulk_create
        result = self.queryset.bulk_create(objs)

        # Assert signals were fired
        self.assertEqual(len(self.pre_create_calls), 1)
        self.assertEqual(len(self.post_create_calls), 1)

        # Check pre_create signal
        pre_call = self.pre_create_calls[0]
        self.assertEqual(pre_call["sender"], self.model)
        self.assertEqual(len(pre_call["instances"]), 2)
        self.assertEqual(pre_call["instances"][0].name, "test1")
        self.assertEqual(pre_call["instances"][1].name, "test2")

        # Check post_create signal
        post_call = self.post_create_calls[0]
        self.assertEqual(post_call["sender"], self.model)
        self.assertEqual(len(post_call["instances"]), 2)
        # Objects should have PKs after creation
        self.assertIsNotNone(post_call["instances"][0].pk)
        self.assertIsNotNone(post_call["instances"][1].pk)

    def test_bulk_update_signals(self):
        """Test that bulk_update fires pre and post signals."""
        # Create objects in database first
        obj1 = QuerySetTestModel.objects.create(name="test1", value=10)
        obj2 = QuerySetTestModel.objects.create(name="test2", value=20)

        # Modify objects
        obj1.value = 100
        obj2.value = 200
        objs = [obj1, obj2]

        # Clear previous calls
        self.pre_update_calls.clear()
        self.post_update_calls.clear()

        # Perform bulk_update
        result = self.queryset.bulk_update(objs, fields=["value"])

        # Assert signals were fired
        self.assertEqual(len(self.pre_update_calls), 1)
        self.assertEqual(len(self.post_update_calls), 1)

        # Check pre_update signal
        pre_call = self.pre_update_calls[0]
        self.assertEqual(pre_call["sender"], self.model)
        self.assertEqual(len(pre_call["instances"]), 2)
        self.assertEqual(len(pre_call["originals"]), 2)
        self.assertEqual(pre_call["fields"], ["value"])
        self.assertEqual(pre_call["instances"][0].value, 100)
        self.assertEqual(pre_call["instances"][1].value, 200)

        # Check post_update signal
        post_call = self.post_update_calls[0]
        self.assertEqual(post_call["sender"], self.model)
        self.assertEqual(len(post_call["instances"]), 2)
        self.assertEqual(len(post_call["originals"]), 2)
        self.assertEqual(post_call["fields"], ["value"])

    def test_bulk_delete_signals(self):
        """Test that bulk_delete fires pre and post signals."""
        # Create objects in database first
        obj1 = QuerySetTestModel.objects.create(name="test1", value=10)
        obj2 = QuerySetTestModel.objects.create(name="test2", value=20)
        objs = [obj1, obj2]

        # Clear previous calls
        self.pre_delete_calls.clear()
        self.post_delete_calls.clear()

        # Perform bulk_delete
        result = self.queryset.bulk_delete(objs)

        # Assert signals were fired
        self.assertEqual(len(self.pre_delete_calls), 1)
        self.assertEqual(len(self.post_delete_calls), 1)

        # Check pre_delete signal
        pre_call = self.pre_delete_calls[0]
        self.assertEqual(pre_call["sender"], self.model)
        self.assertEqual(len(pre_call["instances"]), 2)

        # Check post_delete signal
        post_call = self.post_delete_calls[0]
        self.assertEqual(post_call["sender"], self.model)
        self.assertEqual(len(post_call["instances"]), 2)

        # Verify objects were actually deleted
        self.assertEqual(QuerySetTestModel.objects.count(), 0)

    def test_signal_arguments(self):
        """Test that signals receive correct arguments."""
        # Test bulk_create with all arguments
        obj = QuerySetTestModel(name="test", value=10)

        result = self.queryset.bulk_create([obj], batch_size=100, ignore_conflicts=True)

        pre_call = self.pre_create_calls[0]
        self.assertEqual(pre_call["kwargs"]["batch_size"], 100)
        self.assertEqual(pre_call["kwargs"]["ignore_conflicts"], True)

        post_call = self.post_create_calls[0]
        self.assertEqual(post_call["kwargs"]["batch_size"], 100)
        self.assertEqual(post_call["kwargs"]["ignore_conflicts"], True)

    def test_field_change_detection(self):
        """Test that field change detection works correctly."""
        # Create object in database
        obj = QuerySetTestModel.objects.create(name="test", value=10)

        # Modify object
        obj.value = 20
        obj.name = "modified"

        # Clear calls
        self.pre_update_calls.clear()

        # Perform bulk_update without specifying fields
        result = self.queryset.bulk_update([obj])  # No fields specified

        # Check that changed fields were detected
        pre_call = self.pre_update_calls[0]
        detected_fields = pre_call["fields"]

        # Should detect both changed fields
        self.assertIn("value", detected_fields)
        self.assertIn("name", detected_fields)
        self.assertNotIn("id", detected_fields)  # PK should be excluded

    def test_auto_now_fields(self):
        """Test that auto_now fields are handled correctly."""
        from datetime import timedelta

        from django.utils import timezone

        # Create object
        obj = TestModelWithAutoNow.objects.create(name="test")
        original_updated_at = obj.updated_at

        # Wait a bit to ensure timestamp difference
        import time

        time.sleep(0.01)

        # Modify object
        obj.name = "modified"

        # Perform bulk_update
        result = TestModelWithAutoNow.objects.get_queryset().bulk_update([obj])

        # Check that auto_now field was updated
        obj.refresh_from_db()
        self.assertGreater(obj.updated_at, original_updated_at)

    def test_multiple_receivers(self):
        """Test that multiple receivers can be connected."""
        calls = []

        @receiver(bulk_pre_create, sender=self.model)
        def receiver1(sender, instances, **kwargs):
            calls.append("receiver1")

        @receiver(bulk_pre_create, sender=self.model)
        def receiver2(sender, instances, **kwargs):
            calls.append("receiver2")

        # Perform operation
        obj = QuerySetTestModel(name="test", value=10)
        self.queryset.bulk_create([obj])

        # Both receivers should be called
        self.assertIn("receiver1", calls)
        self.assertIn("receiver2", calls)
