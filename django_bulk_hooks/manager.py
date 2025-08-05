from django.db import models

from django_bulk_hooks.queryset import HookQuerySet, HookQuerySetMixin


class BulkHookManager(models.Manager):
    def get_queryset(self):
        # Use super().get_queryset() to let Django and MRO build the queryset
        # This ensures cooperation with other managers
        base_queryset = super().get_queryset()
        
        # If the base queryset already has hook functionality, return it as-is
        if isinstance(base_queryset, HookQuerySetMixin):
            return base_queryset
        
        # Otherwise, create a new HookQuerySet with the same parameters
        # This is much simpler and avoids dynamic class creation issues
        return HookQuerySet(
            model=base_queryset.model,
            query=base_queryset.query,
            using=base_queryset._db,
            hints=base_queryset._hints
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
        **kwargs,
    ):
        """
        Delegate to QuerySet's bulk_create implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().bulk_create(
            objs,
            bypass_hooks=bypass_hooks,
            bypass_validation=bypass_validation,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            **kwargs,
        )

    def bulk_update(
        self, objs, fields, bypass_hooks=False, bypass_validation=False, **kwargs
    ):
        """
        Delegate to QuerySet's bulk_update implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().bulk_update(
            objs,
            fields,
            bypass_hooks=bypass_hooks,
            bypass_validation=bypass_validation,
            **kwargs,
        )

    def bulk_delete(
        self,
        objs,
        batch_size=None,
        bypass_hooks=False,
        bypass_validation=False,
        **kwargs,
    ):
        """
        Delegate to QuerySet's bulk_delete implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().bulk_delete(
            objs,
            bypass_hooks=bypass_hooks,
            bypass_validation=bypass_validation,
            batch_size=batch_size,
            **kwargs,
        )

    def delete(self):
        """
        Delegate to QuerySet's delete implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().delete()

    def update(self, **kwargs):
        """
        Delegate to QuerySet's update implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        return self.get_queryset().update(**kwargs)

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
