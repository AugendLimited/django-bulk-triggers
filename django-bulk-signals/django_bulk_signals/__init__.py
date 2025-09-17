"""
Django Bulk Signals - Salesforce-style triggers for Django bulk operations.

This package provides Django signals for bulk operations (bulk_create, bulk_update, bulk_delete)
that work just like Salesforce triggers but follow Django's signal patterns.
"""

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

__all__ = [
    "bulk_pre_create",
    "bulk_post_create",
    "bulk_pre_update",
    "bulk_post_update",
    "bulk_pre_delete",
    "bulk_post_delete",
    "BulkSignalQuerySet",
    "BulkSignalManager",
]

__version__ = "1.0.0"
