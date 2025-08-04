from django.db import models

from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
    VALIDATE_CREATE,
    VALIDATE_DELETE,
    VALIDATE_UPDATE,
)
from django_bulk_hooks.context import HookContext
from django_bulk_hooks.engine import run
from django_bulk_hooks.manager import BulkHookManager


class HookModelMixin(models.Model):
    objects = BulkHookManager()

    class Meta:
        abstract = True

    def clean(self, bypass_hooks=False):
        """
        Override clean() to trigger validation hooks.
        This ensures that when Django calls clean() (like in admin forms),
        it triggers the VALIDATE_* hooks for validation only.
        """
        super().clean()

        # If bypass_hooks is True, skip validation hooks
        if bypass_hooks:
            return

        # Determine if this is a create or update operation
        is_create = self.pk is None

        if is_create:
            # For create operations, run VALIDATE_CREATE hooks for validation
            ctx = HookContext(self.__class__)
            run(self.__class__, VALIDATE_CREATE, [self], ctx=ctx)
        else:
            # For update operations, run VALIDATE_UPDATE hooks for validation
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
                ctx = HookContext(self.__class__)
                run(self.__class__, VALIDATE_UPDATE, [self], [old_instance], ctx=ctx)
            except self.__class__.DoesNotExist:
                # If the old instance doesn't exist, treat as create
                ctx = HookContext(self.__class__)
                run(self.__class__, VALIDATE_CREATE, [self], ctx=ctx)

    def save(self, *args, bypass_hooks=False, **kwargs):
        # If bypass_hooks is True, use base manager to avoid triggering hooks
        if bypass_hooks:
            return self._base_manager.save(self, *args, **kwargs)
        
        is_create = self.pk is None

        if is_create:
            # For create operations, we don't have old records
            ctx = HookContext(self.__class__)
            run(self.__class__, BEFORE_CREATE, [self], ctx=ctx)

            super().save(*args, **kwargs)

            run(self.__class__, AFTER_CREATE, [self], ctx=ctx)
        else:
            # For update operations, we need to get the old record
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
                ctx = HookContext(self.__class__)
                run(self.__class__, BEFORE_UPDATE, [self], [old_instance], ctx=ctx)

                super().save(*args, **kwargs)

                run(self.__class__, AFTER_UPDATE, [self], [old_instance], ctx=ctx)
            except self.__class__.DoesNotExist:
                # If the old instance doesn't exist, treat as create
                ctx = HookContext(self.__class__)
                run(self.__class__, BEFORE_CREATE, [self], ctx=ctx)

                super().save(*args, **kwargs)

                run(self.__class__, AFTER_CREATE, [self], ctx=ctx)

        return self

    def delete(self, *args, bypass_hooks=False, **kwargs):
        # If bypass_hooks is True, use base manager to avoid triggering hooks
        if bypass_hooks:
            return self._base_manager.delete(self, *args, **kwargs)
        
        ctx = HookContext(self.__class__)

        # Run validation hooks first
        run(self.__class__, VALIDATE_DELETE, [self], ctx=ctx)

        # Then run business logic hooks
        run(self.__class__, BEFORE_DELETE, [self], ctx=ctx)

        result = super().delete(*args, **kwargs)

        run(self.__class__, AFTER_DELETE, [self], ctx=ctx)
        return result
