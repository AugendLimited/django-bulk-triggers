"""
BulkSignalQuerySet - QuerySet that fires signals for bulk operations.

This QuerySet extends Django's QuerySet to fire signals before and after
bulk operations, providing Salesforce-style trigger behavior.
"""

import logging
from typing import List, Optional

from django.db import models, transaction
from django.db.models import QuerySet

from django_bulk_signals.signals import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)

logger = logging.getLogger(__name__)


class BulkSignalQuerySet(QuerySet):
    """
    QuerySet that fires signals for bulk operations.

    This provides Salesforce-style trigger behavior using Django's signal framework.
    All bulk operations (bulk_create, bulk_update, bulk_delete) fire appropriate
    signals before and after the database operation.
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
        """
        Bulk create with signal support.

        Fires bulk_pre_create before the operation and bulk_post_create after.
        All arguments are passed through to Django's bulk_create.
        """
        if not objs:
            return objs

        logger.debug(
            f"bulk_create: Creating {len(objs)} objects for {self.model.__name__}"
        )

        # Fire BEFORE_CREATE signal
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

        # Perform the bulk create operation
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

        # Fire AFTER_CREATE signal
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

        logger.debug(
            f"bulk_create: Created {len(result)} objects for {self.model.__name__}"
        )
        return result

    @transaction.atomic
    def bulk_update(
        self,
        objs: List[models.Model],
        fields: Optional[List[str]] = None,
        batch_size: Optional[int] = None,
        **kwargs,
    ) -> int:
        """
        Bulk update with signal support.

        Fires bulk_pre_update before the operation and bulk_post_update after.
        Provides OLD/NEW value comparison like Salesforce triggers.

        If fields is None, automatically detects changed fields by comparing
        objects with their current database values.
        """
        if not objs:
            return 0

        logger.debug(
            f"bulk_update: Updating {len(objs)} objects for {self.model.__name__}"
        )

        # Get original instances for OLD/NEW comparison
        pks = [obj.pk for obj in objs if obj.pk is not None]
        if not pks:
            raise ValueError("All objects must have primary keys for bulk_update")

        originals = list(self.model.objects.filter(pk__in=pks))
        original_map = {obj.pk: obj for obj in originals}

        # Ensure we have originals for all objects
        for obj in objs:
            if obj.pk not in original_map:
                logger.warning(f"bulk_update: No original found for object {obj.pk}")

        # Auto-detect fields if not provided
        if fields is None:
            # Apply auto_now timestamps first so they get detected as changed
            self._apply_auto_now_fields(objs)

            changed_fields = self._detect_changed_fields(objs, original_map)
            fields = list(changed_fields)

            logger.debug(f"bulk_update: Auto-detected fields: {fields}")

        # Fire BEFORE_UPDATE signal
        bulk_pre_update.send(
            sender=self.model,
            instances=objs,
            originals=originals,
            fields=fields,
            batch_size=batch_size,
            **kwargs,
        )

        # Perform the bulk update operation
        django_kwargs = {
            k: v
            for k, v in {
                "batch_size": batch_size,
            }.items()
            if v is not None
        }

        result = super().bulk_update(objs, fields, **django_kwargs)

        # Fire AFTER_UPDATE signal
        bulk_post_update.send(
            sender=self.model,
            instances=objs,
            originals=originals,
            fields=fields,
            batch_size=batch_size,
            **kwargs,
        )

        logger.debug(f"bulk_update: Updated {result} objects for {self.model.__name__}")
        return result

    @transaction.atomic
    def bulk_delete(self, objs: List[models.Model], **kwargs) -> int:
        """
        Bulk delete with signal support.

        Fires bulk_pre_delete before the operation and bulk_post_delete after.
        """
        if not objs:
            return 0

        logger.debug(
            f"bulk_delete: Deleting {len(objs)} objects for {self.model.__name__}"
        )

        # Fire BEFORE_DELETE signal
        bulk_pre_delete.send(sender=self.model, instances=objs, **kwargs)

        # Perform the bulk delete operation using Django's delete() method
        pks = [obj.pk for obj in objs if obj.pk is not None]
        if not pks:
            logger.warning("bulk_delete: No objects with primary keys to delete")
            return 0

        # Use the queryset's delete method to delete objects by PK
        queryset = self.model.objects.filter(pk__in=pks)
        result = queryset.delete()[0]  # delete() returns (count, {model: count})

        # Fire AFTER_DELETE signal
        bulk_post_delete.send(sender=self.model, instances=objs, **kwargs)

        logger.debug(f"bulk_delete: Deleted {result} objects for {self.model.__name__}")
        return result

    def _detect_changed_fields(self, objs, original_map=None):
        """
        Auto-detect which fields have changed by comparing objects with original values.
        Returns a set of field names that have changed across all objects.

        Args:
            objs: List of objects to check for changes
            original_map: Optional dict mapping pk to original objects (if already fetched)
        """
        if not objs:
            return set()

        changed_fields = set()

        # Use provided original_map or fetch from database
        if original_map is None:
            obj_pks = [obj.pk for obj in objs if obj.pk is not None]
            if not obj_pks:
                return set()
            original_map = {
                obj.pk: obj for obj in self.model.objects.filter(pk__in=obj_pks)
            }

        for obj in objs:
            if obj.pk is None:
                continue

            old_obj = original_map.get(obj.pk)
            if old_obj is None:
                continue  # Object not found in database

            for field in obj._meta.concrete_fields:
                if field.primary_key:
                    continue

                if getattr(obj, field.name) != getattr(old_obj, field.name):
                    changed_fields.add(field.name)

        return changed_fields

    def _apply_auto_now_fields(self, objs):
        """Apply current timestamp to auto_now fields."""
        from django.utils import timezone

        current_time = timezone.now()

        for obj in objs:
            for field in obj._meta.local_concrete_fields:
                if getattr(field, "auto_now", False):
                    setattr(obj, field.name, current_time)
