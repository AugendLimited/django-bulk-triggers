"""
Core bulk signals implementation - Zero coupling design.

This module provides the core functionality for bulk signals with minimal coupling.
Each component has a single responsibility and no dependencies on other components.
"""

import logging
from typing import Any, List, Optional

from django.db import models, transaction
from django.db.models import QuerySet
from django.dispatch import Signal

logger = logging.getLogger(__name__)


# Core signals - These never change
bulk_pre_create = Signal()
bulk_post_create = Signal()
bulk_pre_update = Signal()
bulk_post_update = Signal()
bulk_pre_delete = Signal()
bulk_post_delete = Signal()


class BulkSignalQuerySet(QuerySet):
    """
    QuerySet that fires signals for bulk operations.

    This is the ONLY component that knows about signals.
    It has ZERO dependencies on services, executors, or configuration.
    """

    @transaction.atomic
    def bulk_create(
        self,
        objs: List[models.Model],
        batch_size: Optional[int] = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Optional[List[str]] = None,
        unique_fields: Optional[List[str]] = None,
        **kwargs,
    ) -> List[models.Model]:
        """Bulk create with signal support."""
        if not objs:
            return objs

        # Fire BEFORE signal
        bulk_pre_create.send(
            sender=self.model,
            instances=objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            **kwargs,
        )

        # Perform operation
        django_kwargs = {
            k: v
            for k, v in {
                "batch_size": batch_size,
                "ignore_conflicts": ignore_conflicts,
                "update_conflicts": update_conflicts,
                "update_fields": update_fields,
                "unique_fields": unique_fields,
            }.items()
            if v is not None
        }

        result = super().bulk_create(objs, **django_kwargs)

        # Fire AFTER signal
        bulk_post_create.send(
            sender=self.model,
            instances=result,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            **kwargs,
        )

        return result

    @transaction.atomic
    def bulk_update(
        self,
        objs: List[models.Model],
        fields: List[str],
        batch_size: Optional[int] = None,
        **kwargs,
    ) -> int:
        """Bulk update with signal support."""
        if not objs:
            return 0

        # Get originals for OLD/NEW comparison
        pks = [obj.pk for obj in objs if obj.pk is not None]
        if not pks:
            raise ValueError("All objects must have primary keys for bulk_update")

        originals = list(self.model._base_manager.filter(pk__in=pks))

        # Fire BEFORE signal
        bulk_pre_update.send(
            sender=self.model,
            instances=objs,
            originals=originals,
            fields=fields,
            batch_size=batch_size,
            **kwargs,
        )

        # Perform operation
        django_kwargs = {
            k: v for k, v in {"batch_size": batch_size}.items() if v is not None
        }

        result = super().bulk_update(objs, fields, **django_kwargs)

        # Fire AFTER signal
        bulk_post_update.send(
            sender=self.model,
            instances=objs,
            originals=originals,
            fields=fields,
            batch_size=batch_size,
            **kwargs,
        )

        return result

    @transaction.atomic
    def bulk_delete(self, objs: List[models.Model], **kwargs) -> int:
        """Bulk delete with signal support."""
        if not objs:
            return 0

        # Fire BEFORE signal
        bulk_pre_delete.send(
            sender=self.model,
            instances=objs,
            **kwargs,
        )

        # Check Django version
        if not hasattr(super(), "bulk_delete"):
            raise NotImplementedError(
                "bulk_delete is only available in Django 4.2+. "
                "Please upgrade Django or use individual model.delete() calls."
            )

        # Perform operation
        result = super().bulk_delete(objs, **kwargs)

        # Fire AFTER signal
        bulk_post_delete.send(
            sender=self.model,
            instances=objs,
            **kwargs,
        )

        return result


class BulkSignalManager(models.Manager):
    """
    Manager that provides bulk operation signals.

    This has ZERO dependencies on services or configuration.
    It only delegates to QuerySet.
    """

    def get_queryset(self):
        """Return BulkSignalQuerySet instead of regular QuerySet."""
        return BulkSignalQuerySet(self.model, using=self._db, hints=self._hints)
