"""
BulkSignalQuerySet - QuerySet that fires signals for bulk operations.

This QuerySet extends Django's QuerySet to fire signals before and after
bulk operations, providing Salesforce-style trigger behavior.
"""

import logging
from typing import Any, Dict, List, Optional

from django.db import models, transaction
from django.db.models import QuerySet

from django_bulk_signals.services import _default_service
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

    def __init__(
        self, model=None, query=None, using=None, hints=None, trigger_service=None
    ):
        super().__init__(model, query, using, hints)
        self.trigger_service = trigger_service or _default_service

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

        # Validate objects
        for obj in objs:
            if not isinstance(obj, self.model):
                raise TypeError(
                    f"Expected {self.model.__name__} instance, got {type(obj).__name__}"
                )

        # Fire BEFORE_CREATE signal (Salesforce-style)
        self.trigger_service.execute_before_triggers(
            bulk_pre_create,
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

        # Fire AFTER_CREATE signal (Salesforce-style)
        self.trigger_service.execute_after_triggers(
            bulk_post_create,
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
        fields: List[str],
        batch_size: Optional[int] = None,
        **kwargs,
    ) -> int:
        """
        Bulk update with signal support.

        Fires bulk_pre_update before the operation and bulk_post_update after.
        Provides OLD/NEW value comparison like Salesforce triggers.
        """
        if not objs:
            return 0

        logger.debug(
            f"bulk_update: Updating {len(objs)} objects for {self.model.__name__}"
        )

        # Validate objects
        for obj in objs:
            if not isinstance(obj, self.model):
                raise TypeError(
                    f"Expected {self.model.__name__} instance, got {type(obj).__name__}"
                )

        # Get original instances for OLD/NEW comparison (Salesforce-style)
        pks = [obj.pk for obj in objs if obj.pk is not None]
        if not pks:
            raise ValueError("All objects must have primary keys for bulk_update")

        # Use _base_manager to avoid triggering signals recursively
        originals = list(self.model._base_manager.filter(pk__in=pks))
        original_map = {obj.pk: obj for obj in originals}

        # Ensure we have originals for all objects
        for obj in objs:
            if obj.pk not in original_map:
                logger.warning(f"bulk_update: No original found for object {obj.pk}")

        # Fire BEFORE_UPDATE signal (Salesforce-style)
        self.trigger_service.execute_before_triggers(
            bulk_pre_update,
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

        # Fire AFTER_UPDATE signal (Salesforce-style)
        self.trigger_service.execute_after_triggers(
            bulk_post_update,
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

        Note: bulk_delete is only available in Django 4.2+. For older versions,
        this will raise NotImplementedError.
        """
        if not objs:
            return 0

        logger.debug(
            f"bulk_delete: Deleting {len(objs)} objects for {self.model.__name__}"
        )

        # Validate objects
        for obj in objs:
            if not isinstance(obj, self.model):
                raise TypeError(
                    f"Expected {self.model.__name__} instance, got {type(obj).__name__}"
                )

        # Fire BEFORE_DELETE signal (Salesforce-style)
        self.trigger_service.execute_before_triggers(
            bulk_pre_delete,
            sender=self.model,
            instances=objs,
            **kwargs,
        )

        # Check if bulk_delete is available (Django 4.2+)
        if not hasattr(super(), "bulk_delete"):
            logger.warning(
                f"bulk_delete not available in Django {self.model._meta.apps.__class__.__module__}. "
                f"Please upgrade to Django 4.2+ or use individual deletes."
            )
            raise NotImplementedError(
                "bulk_delete is only available in Django 4.2+. "
                "Please upgrade Django or use individual model.delete() calls."
            )

        # Perform the bulk delete operation
        result = super().bulk_delete(objs, **kwargs)

        # Fire AFTER_DELETE signal (Salesforce-style)
        self.trigger_service.execute_after_triggers(
            bulk_post_delete,
            sender=self.model,
            instances=objs,
            **kwargs,
        )

        logger.debug(f"bulk_delete: Deleted {result} objects for {self.model.__name__}")
        return result
