from django.db import models

from django_bulk_hooks.queryset import HookQuerySet, HookQuerySetMixin


def inject_bulk_hook_behavior(queryset):
    """
    Dynamically inject bulk hook behavior into any queryset.
    This follows the industry-standard pattern for cooperative queryset extensions.
    
    Args:
        queryset: Any Django QuerySet instance
        
    Returns:
        A new queryset instance with bulk hook functionality added
    """
    if isinstance(queryset, HookQuerySetMixin):
        # Already has hook functionality, return as-is
        return queryset
    
    # Create a new class that inherits from both HookQuerySetMixin and the queryset's class
    HookedQuerySetClass = type(
        "HookedQuerySet",
        (HookQuerySetMixin, queryset.__class__),
        {
            '__module__': 'django_bulk_hooks.queryset',
            '__doc__': f'Dynamically created queryset with bulk hook functionality for {queryset.__class__.__name__}'
        }
    )
    
    # Create a new instance with the same parameters
    new_queryset = HookedQuerySetClass(
        model=queryset.model,
        query=queryset.query,
        using=queryset._db,
        hints=queryset._hints
    )
    
    # Copy any additional attributes that might be important
    for attr, value in queryset.__dict__.items():
        if not hasattr(new_queryset, attr):
            setattr(new_queryset, attr, value)
    
    return new_queryset


class BulkHookManager(models.Manager):
    def get_queryset(self):
        # Use super().get_queryset() to let Django and MRO build the queryset
        # This ensures cooperation with other managers
        base_queryset = super().get_queryset()
        
        # Inject our bulk hook behavior into the queryset
        return inject_bulk_hook_behavior(base_queryset)

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
