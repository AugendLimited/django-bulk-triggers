"""
BulkSignalManager - Manager that provides bulk operation signals.

This manager extends Django's Manager to provide QuerySets that fire signals
for bulk operations, providing Salesforce-style trigger behavior.
"""

from django.db import models

from django_bulk_signals.queryset import BulkSignalQuerySet


class BulkSignalManager(models.Manager):
    """
    Manager that provides bulk operation signals.

    This manager returns BulkSignalQuerySet instances that fire signals
    for bulk operations, providing Salesforce-style trigger behavior.
    """

    def get_queryset(self):
        """
        Return a BulkSignalQuerySet instead of a regular QuerySet.

        This ensures that all bulk operations (bulk_create, bulk_update, bulk_delete)
        fire appropriate signals.
        """
        return BulkSignalQuerySet(self.model, using=self._db, hints=self._hints)

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
        **kwargs,
    ):
        """
        Delegate to QuerySet's bulk_create implementation.

        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            **kwargs,
        )

    def bulk_update(self, objs, fields=None, batch_size=None, **kwargs):
        """
        Delegate to QuerySet's bulk_update implementation.

        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        if fields is not None:
            kwargs["fields"] = fields
        return self.get_queryset().bulk_update(
            objs, fields=fields, batch_size=batch_size, **kwargs
        )

    def bulk_delete(self, objs, **kwargs):
        """
        Delegate to QuerySet's bulk_delete implementation.

        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().bulk_delete(objs, **kwargs)
