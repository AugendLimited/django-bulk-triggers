from django.db import models

from django_bulk_hooks.queryset import HookQuerySet


class BulkHookManager(models.Manager):
    def get_queryset(self):
        return HookQuerySet(self.model, using=self._db)

    def bulk_update(
        self, objs, fields, bypass_hooks=False, bypass_validation=False, **kwargs
    ):
        """
        Delegate to QuerySet's bulk_update implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().bulk_update(
            objs, fields, bypass_hooks=bypass_hooks, bypass_validation=bypass_validation, **kwargs
        )

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
        bypass_hooks=False,
        bypass_validation=False,
    ):
        """
        Delegate to QuerySet's bulk_create implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        kwargs = {
            'batch_size': batch_size,
            'ignore_conflicts': ignore_conflicts,
            'update_conflicts': update_conflicts,
            'update_fields': update_fields,
            'unique_fields': unique_fields,
        }
        # Only include custom args if explicitly set to True
        if bypass_hooks:
            kwargs['bypass_hooks'] = bypass_hooks
        if bypass_validation:
            kwargs['bypass_validation'] = bypass_validation
        return self.get_queryset().bulk_create(
            objs,
            **kwargs
        )

    def bulk_delete(
        self, objs, batch_size=None, bypass_hooks=False, bypass_validation=False
    ):
        """
        Delegate to QuerySet's bulk_delete implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().bulk_delete(
            objs, batch_size=batch_size, bypass_hooks=bypass_hooks, bypass_validation=bypass_validation
        )

    def update(self, **kwargs):
        """
        Delegate to QuerySet's update implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().update(**kwargs)

    def delete(self):
        """
        Delegate to QuerySet's delete implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().delete()

    def save(self, obj):
        """
        Save a single object using the appropriate bulk operation.
        """
        if obj.pk:
            self.bulk_update(
                [obj],
                fields=[field.name for field in obj._meta.fields if field.name != "id"],
            )
        else:
            self.bulk_create([obj])
        return obj
