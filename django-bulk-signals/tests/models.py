"""
Test models for django-bulk-signals tests.
"""

from django.db import models
from django_bulk_signals.models import BulkSignalModel


class QuerySetTestModel(BulkSignalModel):
    """Test model for queryset tests."""

    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)

    class Meta:
        app_label = "tests"


class TestModelWithAutoNow(BulkSignalModel):
    """Test model with auto_now field."""

    name = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "tests"
