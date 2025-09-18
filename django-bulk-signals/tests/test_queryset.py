"""
Tests for django_bulk_signals.queryset module.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django.db import models
from django_bulk_signals.models import BulkSignalModel
from django_bulk_signals.queryset import BulkSignalQuerySet
from django_bulk_signals.signals import (
    bulk_pre_create,
    bulk_post_create,
    bulk_pre_update,
    bulk_post_update,
    bulk_pre_delete,
    bulk_post_delete,
)


class QuerySetTestModel(BulkSignalModel):
    """Test model for queryset tests."""

    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)

    class Meta:
        app_label = "tests"


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
        from unittest.mock import patch, MagicMock

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
