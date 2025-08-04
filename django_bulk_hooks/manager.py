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
        import inspect
        qs = self.get_queryset()
        method = qs.bulk_update
        print(f"DEBUG: bulk_update method signature: {inspect.signature(method)}")
        print(f"DEBUG: Calling with args: objs={type(objs)}, fields={fields}, bypass_hooks={bypass_hooks}, bypass_validation={bypass_validation}, kwargs={kwargs}")
        print(f"DEBUG: QuerySet class: {type(qs)}")
        
        # Check if this is our HookQuerySet or a different QuerySet
        if hasattr(qs, 'bulk_update') and 'bypass_hooks' in inspect.signature(qs.bulk_update).parameters:
            # Our HookQuerySet - pass all parameters
            print(f"DEBUG: Using our HookQuerySet for {self.model}")
            return qs.bulk_update(objs, fields, bypass_hooks=bypass_hooks, bypass_validation=bypass_validation, **kwargs)
        else:
            # Different QuerySet (like queryable_properties) - only pass standard parameters
            print(f"DEBUG: Using different QuerySet ({type(qs)}) for {self.model}, bypassing hooks")
            django_kwargs = {k: v for k, v in kwargs.items() if k not in ['bypass_hooks', 'bypass_validation']}
            return qs.bulk_update(objs, fields, **django_kwargs)

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
        import inspect
        qs = self.get_queryset()
        method = qs.bulk_create
        
        # Check if this is our HookQuerySet or a different QuerySet
        if hasattr(qs, 'bulk_create') and 'bypass_hooks' in inspect.signature(qs.bulk_create).parameters:
            # Our HookQuerySet - pass all parameters
            print(f"DEBUG: Using our HookQuerySet for {self.model}")
            kwargs = {
                'batch_size': batch_size,
                'ignore_conflicts': ignore_conflicts,
                'update_conflicts': update_conflicts,
                'update_fields': update_fields,
                'unique_fields': unique_fields,
            }
            return qs.bulk_create(objs, bypass_hooks=bypass_hooks, bypass_validation=bypass_validation, **kwargs)
        else:
            # Different QuerySet - only pass standard parameters
            print(f"DEBUG: Using different QuerySet ({type(qs)}) for {self.model}, bypassing hooks")
            kwargs = {
                'batch_size': batch_size,
                'ignore_conflicts': ignore_conflicts,
                'update_conflicts': update_conflicts,
                'update_fields': update_fields,
                'unique_fields': unique_fields,
            }
            return qs.bulk_create(objs, **kwargs)

    def bulk_delete(
        self, objs, batch_size=None, bypass_hooks=False, bypass_validation=False
    ):
        """
        Delegate to QuerySet's bulk_delete implementation.
        This follows Django's pattern where Manager methods call QuerySet methods.
        """
        import inspect
        qs = self.get_queryset()
        method = qs.bulk_delete
        
        # Check if this is our HookQuerySet or a different QuerySet
        if hasattr(qs, 'bulk_delete') and 'bypass_hooks' in inspect.signature(qs.bulk_delete).parameters:
            # Our HookQuerySet - pass all parameters
            print(f"DEBUG: Using our HookQuerySet for {self.model}")
            kwargs = {
                'batch_size': batch_size,
            }
            return qs.bulk_delete(objs, bypass_hooks=bypass_hooks, bypass_validation=bypass_validation, **kwargs)
        else:
            # Different QuerySet - only pass standard parameters
            print(f"DEBUG: Using different QuerySet ({type(qs)}) for {self.model}, bypassing hooks")
            kwargs = {
                'batch_size': batch_size,
            }
            return qs.bulk_delete(objs, **kwargs)

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
