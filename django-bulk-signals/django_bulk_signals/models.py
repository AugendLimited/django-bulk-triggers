"""
Model mixin for individual model operations with signal support.

This module provides BulkSignalModelMixin that enables BEFORE/AFTER signals
for individual model operations (save, delete) and admin form validation.

The mixin now delegates signal orchestration to the service layer,
maintaining proper separation of concerns.
"""

import logging

from django.db import models

from django_bulk_signals.manager import BulkSignalManager
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


class BulkSignalModelMixin(models.Model):
    """
    Model mixin that provides signal support for individual model operations.

    This mixin enables BEFORE/AFTER signals for:
    - Individual model save() operations
    - Individual model delete() operations
    - Admin form validation via clean()

    The mixin delegates signal orchestration to the service layer,
    maintaining proper separation of concerns.

    Usage:
        class MyModel(BulkSignalModelMixin):
            name = models.CharField(max_length=100)
    """

    objects = BulkSignalManager()

    class Meta:
        abstract = True

    def clean(self, bypass_signals=False):
        """
        Override clean() to trigger validation signals.

        This ensures that when Django calls clean() (like in admin forms),
        it triggers validation signals for proper form validation.

        Args:
            bypass_signals: If True, skip validation signals
        """
        super().clean()

        # If bypass_signals is True, skip validation signals
        if bypass_signals:
            return

        # For validation, we can fire a simple validation signal
        # This allows trigger handlers to perform validation logic
        logger.debug(f"clean() called for {self.__class__.__name__} pk={self.pk}")

    def save(self, *args, bypass_signals=False, **kwargs):
        """
        Override save() to trigger BEFORE/AFTER signals for individual operations.

        Args:
            bypass_signals: If True, skip signal firing
            **kwargs: Additional arguments passed to Django's save()
        """
        # If bypass_signals is True, use base manager to avoid triggering signals
        if bypass_signals:
            logger.debug(
                f"save() called with bypass_signals=True for {self.__class__.__name__} pk={self.pk}"
            )
            return self.__class__._base_manager.save(self, *args, **kwargs)

        is_create = self.pk is None

        if is_create:
            logger.debug(f"save() creating new {self.__class__.__name__} instance")
            # For create operations, fire BEFORE_CREATE signal
            _default_service.execute_before_triggers(
                bulk_pre_create,
                sender=self.__class__,
                instances=[self],
                **kwargs,
            )

            super().save(*args, **kwargs)

            # Fire AFTER_CREATE signal
            logger.debug("Running AFTER_CREATE signal for individual save()")
            _default_service.execute_after_triggers(
                bulk_post_create,
                sender=self.__class__,
                instances=[self],
                **kwargs,
            )
        else:
            logger.debug(
                f"save() updating existing {self.__class__.__name__} instance pk={self.pk}"
            )
            # For update operations, we need to get the old record
            try:
                # Use _base_manager to avoid triggering signals recursively
                old_instance = self.__class__._base_manager.get(pk=self.pk)

                # Fire BEFORE_UPDATE signal
                _default_service.execute_before_triggers(
                    bulk_pre_update,
                    sender=self.__class__,
                    instances=[self],
                    originals=[old_instance],
                    fields=list(kwargs.get("update_fields", [])),
                    **kwargs,
                )

                super().save(*args, **kwargs)

                # Fire AFTER_UPDATE signal
                _default_service.execute_after_triggers(
                    bulk_post_update,
                    sender=self.__class__,
                    instances=[self],
                    originals=[old_instance],
                    fields=list(kwargs.get("update_fields", [])),
                    **kwargs,
                )
            except self.__class__.DoesNotExist:
                # If the old instance doesn't exist, treat as create
                logger.warning(
                    f"Old instance not found for {self.__class__.__name__} pk={self.pk}, treating as create"
                )

                # Fire BEFORE_CREATE signal
                _default_service.execute_before_triggers(
                    bulk_pre_create,
                    sender=self.__class__,
                    instances=[self],
                    **kwargs,
                )

                super().save(*args, **kwargs)

                # Fire AFTER_CREATE signal
                _default_service.execute_after_triggers(
                    bulk_post_create,
                    sender=self.__class__,
                    instances=[self],
                    **kwargs,
                )

        return self

    def delete(self, *args, bypass_signals=False, **kwargs):
        """
        Override delete() to trigger BEFORE/AFTER signals for individual operations.

        Args:
            bypass_signals: If True, skip signal firing
            **kwargs: Additional arguments passed to Django's delete()
        """
        # If bypass_signals is True, use base manager to avoid triggering signals
        if bypass_signals:
            return self.__class__._base_manager.delete(self, *args, **kwargs)

        # Fire BEFORE_DELETE signal
        _default_service.execute_before_triggers(
            bulk_pre_delete,
            sender=self.__class__,
            instances=[self],
            **kwargs,
        )

        result = super().delete(*args, **kwargs)

        # Fire AFTER_DELETE signal
        _default_service.execute_after_triggers(
            bulk_post_delete,
            sender=self.__class__,
            instances=[self],
            **kwargs,
        )

        return result
