"""
Tests for bulk operation signals.
"""

from unittest.mock import Mock, call, patch

import pytest
from django.db import models
from django.test import TestCase
from django_bulk_signals.manager import BulkSignalManager
from django_bulk_signals.queryset import BulkSignalQuerySet
from django_bulk_signals.signals import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)


class SignalTestModel(models.Model):
    """Test model for signal testing."""

    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)

    objects = BulkSignalManager()

    class Meta:
        app_label = "tests"


class TestBulkSignals(TestCase):
    """Test bulk operation signals."""

    def setUp(self):
        """Set up test data."""
        self.objs = [
            SignalTestModel(name="obj1", value=1),
            SignalTestModel(name="obj2", value=2),
            SignalTestModel(name="obj3", value=3),
        ]

    def test_bulk_create_signals(self):
        """Test that bulk_create fires appropriate signals."""
        with (
            patch("django_bulk_signals.signals.bulk_pre_create.send") as mock_pre,
            patch("django_bulk_signals.signals.bulk_post_create.send") as mock_post,
            patch("django.db.models.QuerySet.bulk_create") as mock_bulk_create,
        ):
            mock_bulk_create.return_value = self.objs

            queryset = BulkSignalQuerySet(SignalTestModel)
            result = queryset.bulk_create(self.objs)

            # Check that signals were fired
            mock_pre.assert_called_once()
            mock_post.assert_called_once()

            # Check signal arguments
            pre_call = mock_pre.call_args
            self.assertEqual(pre_call[1]["sender"], SignalTestModel)
            self.assertEqual(pre_call[1]["instances"], self.objs)

            post_call = mock_post.call_args
            self.assertEqual(post_call[1]["sender"], SignalTestModel)
            self.assertEqual(post_call[1]["instances"], self.objs)

    def test_bulk_update_signals(self):
        """Test that bulk_update fires appropriate signals."""
        # Create objects with PKs
        for i, obj in enumerate(self.objs):
            obj.pk = i + 1

        with (
            patch("django_bulk_signals.signals.bulk_pre_update.send") as mock_pre,
            patch("django_bulk_signals.signals.bulk_post_update.send") as mock_post,
            patch("django.db.models.QuerySet.bulk_update") as mock_bulk_update,
            patch("django.db.models.QuerySet.filter") as mock_filter,
        ):
            mock_bulk_update.return_value = len(self.objs)
            mock_filter.return_value = self.objs  # Mock originals

            queryset = BulkSignalQuerySet(SignalTestModel)
            result = queryset.bulk_update(self.objs, ["name"])

            # Check that signals were fired
            mock_pre.assert_called_once()
            mock_post.assert_called_once()

            # Check signal arguments
            pre_call = mock_pre.call_args
            self.assertEqual(pre_call[1]["sender"], SignalTestModel)
            self.assertEqual(pre_call[1]["instances"], self.objs)
            self.assertEqual(pre_call[1]["fields"], ["name"])

            post_call = mock_post.call_args
            self.assertEqual(post_call[1]["sender"], SignalTestModel)
            self.assertEqual(post_call[1]["instances"], self.objs)
            self.assertEqual(post_call[1]["fields"], ["name"])

    def test_bulk_delete_signals(self):
        """Test that bulk_delete fires appropriate signals."""
        with (
            patch("django_bulk_signals.signals.bulk_pre_delete.send") as mock_pre,
            patch("django_bulk_signals.signals.bulk_post_delete.send") as mock_post,
            patch("django.db.models.query.QuerySet.delete") as mock_delete,
        ):
            mock_delete.return_value = (len(self.objs), {})

            queryset = BulkSignalQuerySet(SignalTestModel)
            result = queryset.bulk_delete(self.objs)

            # Check that signals were fired
            mock_pre.assert_called_once()
            mock_post.assert_called_once()

            # Check signal arguments
            pre_call = mock_pre.call_args
            self.assertEqual(pre_call[1]["sender"], SignalTestModel)
            self.assertEqual(pre_call[1]["instances"], self.objs)

            post_call = mock_post.call_args
            self.assertEqual(post_call[1]["sender"], SignalTestModel)
            self.assertEqual(post_call[1]["instances"], self.objs)

    def test_empty_bulk_operations(self):
        """Test that empty bulk operations don't fire signals."""
        with (
            patch("django_bulk_signals.signals.bulk_pre_create.send") as mock_pre,
            patch("django_bulk_signals.signals.bulk_post_create.send") as mock_post,
        ):
            queryset = BulkSignalQuerySet(SignalTestModel)
            result = queryset.bulk_create([])

            # Signals should not be fired for empty operations
            mock_pre.assert_not_called()
            mock_post.assert_not_called()

    def test_manager_delegation(self):
        """Test that manager methods delegate to QuerySet."""
        with patch(
            "django_bulk_signals.queryset.BulkSignalQuerySet.bulk_create"
        ) as mock_bulk_create:
            mock_bulk_create.return_value = self.objs

            manager = BulkSignalManager()
            manager.model = SignalTestModel

            result = manager.bulk_create(self.objs)

            mock_bulk_create.assert_called_once_with(self.objs)

    def test_transaction_atomic(self):
        """Test that bulk operations are wrapped in transactions."""
        with patch("django.db.transaction.atomic") as mock_atomic:
            mock_atomic.return_value.__enter__ = Mock()
            mock_atomic.return_value.__exit__ = Mock(return_value=None)

            queryset = BulkSignalQuerySet(SignalTestModel)
            queryset.bulk_create(self.objs)

            # Should be called for transaction.atomic decorator
            mock_atomic.assert_called()

    def test_bulk_update_without_pks(self):
        """Test that bulk_update raises error for objects without PKs."""
        queryset = BulkSignalQuerySet(SignalTestModel)

        with self.assertRaises(ValueError):
            queryset.bulk_update(self.objs, ["name"])
