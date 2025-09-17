"""
BulkSignalManager - Manager that provides bulk operation signals.

This manager extends Django's Manager to provide QuerySets that fire signals
for bulk operations, providing Salesforce-style trigger behavior.
"""

from django.db import models

from django_bulk_signals.core import BulkSignalQuerySet


class BulkSignalManager(models.Manager):
    """
    Manager that provides bulk operation signals.

    This manager returns BulkSignalQuerySet instances that fire signals
    for bulk operations, providing Salesforce-style trigger behavior.

    The manager follows Django's pattern of delegating to QuerySet methods
    rather than duplicating the interface.
    """

    def get_queryset(self):
        """
        Return a BulkSignalQuerySet instead of a regular QuerySet.

        This ensures that all bulk operations (bulk_create, bulk_update, bulk_delete)
        fire appropriate signals.
        """
        return BulkSignalQuerySet(self.model, using=self._db, hints=self._hints)
