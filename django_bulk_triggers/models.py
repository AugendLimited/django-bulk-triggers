import logging

from django.db import models

from django_bulk_triggers.manager import BulkTriggerManager

logger = logging.getLogger(__name__)


class TriggerModelMixin(models.Model):
    objects = BulkTriggerManager()

    class Meta:
        abstract = True

    def clean(self, bypass_triggers=False):
        """
        Override clean() to trigger validation triggers.
        This ensures that when Django calls clean() (like in admin forms),
        it triggers the VALIDATE_* triggers for validation only.
        """
        super().clean()

        # If bypass_triggers is True, skip validation triggers
        if bypass_triggers:
            return

        # Delegate to coordinator (consistent with save/delete)
        is_create = self.pk is None
        self.__class__.objects.get_queryset().coordinator.clean(
            [self], is_create=is_create
        )

    def save(self, *args, bypass_triggers=False, **kwargs):
        """
        Save the model instance.

        Delegates to bulk_create/bulk_update which handle all trigger logic
        including MTI parent triggers.
        """
        if bypass_triggers:
            # Use super().save() to call Django's default save without our trigger logic
            return super().save(*args, **kwargs)

        is_create = self.pk is None

        if is_create:
            # Delegate to bulk_create which handles all trigger logic
            result = self.__class__.objects.bulk_create([self])
            return result[0] if result else self
        else:
            # Delegate to bulk_update which handles all trigger logic
            update_fields = kwargs.get("update_fields")
            if update_fields is None:
                # Update all non-auto fields
                update_fields = [
                    f.name
                    for f in self.__class__._meta.fields
                    if not f.auto_created and f.name != "id"
                ]
            self.__class__.objects.bulk_update([self], update_fields)
            return self

    def delete(self, *args, bypass_triggers=False, **kwargs):
        """
        Delete the model instance.

        Delegates to bulk_delete which handles all trigger logic
        including MTI parent triggers.
        """
        if bypass_triggers:
            # Use super().delete() to call Django's default delete without our trigger logic
            return super().delete(*args, **kwargs)

        # Delegate to bulk_delete (handles both MTI and non-MTI)
        return self.__class__.objects.filter(pk=self.pk).delete()
