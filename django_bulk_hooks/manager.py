from django.db import models, transaction
from django_bulk_hooks import engine
from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
    VALIDATE_CREATE,
    VALIDATE_UPDATE,
    VALIDATE_DELETE,
)
from django_bulk_hooks.context import HookContext
from django_bulk_hooks.queryset import HookQuerySet


class BulkHookManager(models.Manager):
    CHUNK_SIZE = 200

    def get_queryset(self):
        return HookQuerySet(self.model, using=self._db)

    @transaction.atomic
    def bulk_update(self, objs, fields, bypass_hooks=False, bypass_validation=False, **kwargs):
        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_update expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        if not bypass_hooks:
            originals = list(model_cls.objects.filter(pk__in=[obj.pk for obj in objs]))
            ctx = HookContext(model_cls)
            
            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_UPDATE, objs, originals, ctx=ctx)
            
            # Then run business logic hooks
            engine.run(model_cls, BEFORE_UPDATE, objs, originals, ctx=ctx)

            # Automatically detect fields that were modified during BEFORE_UPDATE hooks
            modified_fields = self._detect_modified_fields(objs, originals)
            if modified_fields:
                # Convert to set for efficient union operation
                fields_set = set(fields)
                fields_set.update(modified_fields)
                fields = list(fields_set)

        for i in range(0, len(objs), self.CHUNK_SIZE):
            chunk = objs[i : i + self.CHUNK_SIZE]
            # Call the base implementation to avoid re-triggering this method
            super(models.Manager, self).bulk_update(chunk, fields, **kwargs)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_UPDATE, objs, originals, ctx=ctx)

        return objs

    def _detect_modified_fields(self, new_instances, original_instances):
        """
        Detect fields that were modified during BEFORE_UPDATE hooks by comparing
        new instances with their original values.
        """
        if not original_instances:
            return set()

        # Create a mapping of pk to original instance for efficient lookup
        original_map = {obj.pk: obj for obj in original_instances if obj.pk is not None}

        modified_fields = set()

        for new_instance in new_instances:
            if new_instance.pk is None:
                continue

            original = original_map.get(new_instance.pk)
            if not original:
                continue

            # Compare all fields to detect changes
            for field in new_instance._meta.fields:
                if field.name == "id":
                    continue

                new_value = getattr(new_instance, field.name)
                original_value = getattr(original, field.name)

                # Handle different field types appropriately
                if field.is_relation:
                    # For foreign keys, compare the pk values
                    new_pk = new_value.pk if new_value else None
                    original_pk = original_value.pk if original_value else None
                    if new_pk != original_pk:
                        modified_fields.add(field.name)
                else:
                    # For regular fields, use direct comparison
                    if new_value != original_value:
                        modified_fields.add(field.name)

        return modified_fields

    @transaction.atomic
    def bulk_create(self, objs, bypass_hooks=False, bypass_validation=False, **kwargs):
        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_create expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        result = []

        if not bypass_hooks:
            ctx = HookContext(model_cls)
            
            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)
            
            # Then run business logic hooks
            engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)

        for i in range(0, len(objs), self.CHUNK_SIZE):
            chunk = objs[i : i + self.CHUNK_SIZE]
            result.extend(super(models.Manager, self).bulk_create(chunk, **kwargs))

        if not bypass_hooks:
            engine.run(model_cls, AFTER_CREATE, result, ctx=ctx)

        return result

    @transaction.atomic
    def bulk_delete(self, objs, batch_size=None, bypass_hooks=False, bypass_validation=False):
        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_delete expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        ctx = HookContext(model_cls)

        if not bypass_hooks:
            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_DELETE, objs, ctx=ctx)
            
            # Then run business logic hooks
            engine.run(model_cls, BEFORE_DELETE, objs, ctx=ctx)

        pks = [obj.pk for obj in objs if obj.pk is not None]
        model_cls.objects.filter(pk__in=pks).delete()

        if not bypass_hooks:
            engine.run(model_cls, AFTER_DELETE, objs, ctx=ctx)

        return objs

    @transaction.atomic
    def update(self, **kwargs):
        objs = list(self.all())
        if not objs:
            return 0
        for key, value in kwargs.items():
            for obj in objs:
                setattr(obj, key, value)
        self.bulk_update(objs, fields=list(kwargs.keys()))
        return len(objs)

    @transaction.atomic
    def delete(self):
        objs = list(self.all())
        if not objs:
            return 0
        self.bulk_delete(objs)
        return len(objs)

    @transaction.atomic
    def save(self, obj):
        if obj.pk:
            self.bulk_update(
                [obj],
                fields=[field.name for field in obj._meta.fields if field.name != "id"],
            )
        else:
            self.bulk_create([obj])
        return obj
