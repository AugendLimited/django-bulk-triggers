from django.db import models, transaction

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
from django.db.models.fields.related_descriptors import ForwardManyToOneDescriptor
from functools import wraps
import contextlib


@contextlib.contextmanager
def patch_foreign_key_behavior():
    """
    Temporarily patches Django's foreign key descriptor to return None instead of raising
    RelatedObjectDoesNotExist when accessing an unset foreign key field.
    """
    original_get = ForwardManyToOneDescriptor.__get__
    
    @wraps(original_get)
    def safe_get(self, instance, cls=None):
        if instance is None:
            return self
        try:
            return original_get(self, instance, cls)
        except self.RelatedObjectDoesNotExist:
            return None
    
    # Patch the descriptor
    ForwardManyToOneDescriptor.__get__ = safe_get
    try:
        yield
    finally:
        # Restore original behavior
        ForwardManyToOneDescriptor.__get__ = original_get


class HookModelMixin(models.Model):
    objects = BulkHookManager()

    class Meta:
        abstract = True

    def clean(self):
        """
        Override clean() to trigger validation hooks.
        This ensures that when Django calls clean() (like in admin forms),
        it triggers the VALIDATE_* hooks for validation only.
        """
        # Call Django's clean first
        super().clean()

        # Skip hook validation during admin form validation
        # This prevents RelatedObjectDoesNotExist errors when Django hasn't
        # fully set up the object's relationships yet
        if hasattr(self, '_state') and getattr(self._state, 'validating', False):
            return

        # Determine if this is a create or update operation
        is_create = self.pk is None

        if is_create:
            # For create operations, run VALIDATE_CREATE hooks for validation
            ctx = HookContext(self.__class__)
            with patch_foreign_key_behavior():
                run(self.__class__, VALIDATE_CREATE, [self], ctx=ctx)
        else:
            # For update operations, run VALIDATE_UPDATE hooks for validation
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
                ctx = HookContext(self.__class__)
                with patch_foreign_key_behavior():
                    run(self.__class__, VALIDATE_UPDATE, [self], [old_instance], ctx=ctx)
            except self.__class__.DoesNotExist:
                # If the old instance doesn't exist, treat as create
                ctx = HookContext(self.__class__)
                with patch_foreign_key_behavior():
                    run(self.__class__, VALIDATE_CREATE, [self], ctx=ctx)

    def save(self, *args, **kwargs):
        is_create = self.pk is None
        ctx = HookContext(self.__class__)

        # Use a single context manager for all hooks
        with patch_foreign_key_behavior():
            if is_create:
                # For create operations, run validation hooks first
                run(self.__class__, VALIDATE_CREATE, [self], ctx=ctx)
                # Then run BEFORE hooks
                run(self.__class__, BEFORE_CREATE, [self], ctx=ctx)
                # Now save
                super().save(*args, **kwargs)
                # Finally run AFTER hooks
                run(self.__class__, AFTER_CREATE, [self], ctx=ctx)
            else:
                # For update operations
                try:
                    old_instance = self.__class__.objects.get(pk=self.pk)
                    # Run validation hooks first
                    run(self.__class__, VALIDATE_UPDATE, [self], [old_instance], ctx=ctx)
                    # Then run BEFORE hooks
                    run(self.__class__, BEFORE_UPDATE, [self], [old_instance], ctx=ctx)
                    # Now save
                    super().save(*args, **kwargs)
                    # Finally run AFTER hooks
                    run(self.__class__, AFTER_UPDATE, [self], [old_instance], ctx=ctx)
                except self.__class__.DoesNotExist:
                    # If the old instance doesn't exist, treat as create
                    run(self.__class__, VALIDATE_CREATE, [self], ctx=ctx)
                    run(self.__class__, BEFORE_CREATE, [self], ctx=ctx)
                    super().save(*args, **kwargs)
                    run(self.__class__, AFTER_CREATE, [self], ctx=ctx)

        return self

    def delete(self, *args, **kwargs):
        ctx = HookContext(self.__class__)

        # Use a single context manager for all hooks
        with patch_foreign_key_behavior():
            run(self.__class__, VALIDATE_DELETE, [self], ctx=ctx)
            run(self.__class__, BEFORE_DELETE, [self], ctx=ctx)
            result = super().delete(*args, **kwargs)
            run(self.__class__, AFTER_DELETE, [self], ctx=ctx)
            
        return result
