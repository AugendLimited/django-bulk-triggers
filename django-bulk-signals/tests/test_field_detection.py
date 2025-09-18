"""
Tests for automatic field detection functionality.
"""

import pytest
from django.db import models
from django.test import TestCase
from django.utils import timezone
from django_bulk_signals.models import BulkSignalModel
from django_bulk_signals.queryset import BulkSignalQuerySet


class TestModel(BulkSignalModel):
    """Test model for field detection."""

    name = models.CharField(max_length=100)
    email = models.EmailField()
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "test_app"


class FieldDetectionTestCase(TestCase):
    """Test automatic field detection functionality."""

    def setUp(self):
        """Set up test data."""
        self.obj1 = TestModel.objects.create(name="Test 1", email="test1@example.com")
        self.obj2 = TestModel.objects.create(name="Test 2", email="test2@example.com")

    def test_detect_changed_fields(self):
        """Test that changed fields are detected correctly."""
        # Modify some fields
        self.obj1.name = "Updated Test 1"
        self.obj1.email = "updated1@example.com"

        queryset = BulkSignalQuerySet(TestModel)
        changed_fields = queryset._detect_changed_fields([self.obj1])

        self.assertIn("name", changed_fields)
        self.assertIn("email", changed_fields)
        self.assertNotIn("id", changed_fields)  # PK should be excluded

    def test_prepare_update_fields(self):
        """Test that auto_now fields are included in update fields."""
        queryset = BulkSignalQuerySet(TestModel)
        changed_fields = {"name", "email"}

        fields = queryset._prepare_update_fields(changed_fields)

        # Should include changed fields
        self.assertIn("name", fields)
        self.assertIn("email", fields)

        # Should include auto_now field
        self.assertIn("updated_at", fields)

        # Should not include auto_now_add field for updates
        self.assertNotIn("created_at", fields)

    def test_bulk_update_without_fields(self):
        """Test that bulk_update works without specifying fields."""
        # Modify objects
        self.obj1.name = "Updated Test 1"
        self.obj2.email = "updated2@example.com"

        # Update without specifying fields - should auto-detect
        queryset = BulkSignalQuerySet(TestModel)
        result = queryset.bulk_update([self.obj1, self.obj2])

        self.assertEqual(result, 2)

        # Verify changes were saved
        self.obj1.refresh_from_db()
        self.obj2.refresh_from_db()

        self.assertEqual(self.obj1.name, "Updated Test 1")
        self.assertEqual(self.obj2.email, "updated2@example.com")

    def test_single_object_save(self):
        """Test that single object save uses automatic field detection."""
        # Modify object
        self.obj1.name = "Single Update"

        # Save should automatically detect changed fields
        self.obj1.save()

        # Verify change was saved
        self.obj1.refresh_from_db()
        self.assertEqual(self.obj1.name, "Single Update")
