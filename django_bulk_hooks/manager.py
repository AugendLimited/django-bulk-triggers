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
    VALIDATE_DELETE,
    VALIDATE_UPDATE,
)
from django_bulk_hooks.context import HookContext
from django_bulk_hooks.queryset import HookQuerySet


class BulkHookManager(models.Manager):
    # Default chunk sizes - can be overridden per model
    DEFAULT_CHUNK_SIZE = 200
    DEFAULT_RELATED_CHUNK_SIZE = 500  # Higher for related object fetching
    
    def __init__(self):
        super().__init__()
        self._chunk_size = self.DEFAULT_CHUNK_SIZE
        self._related_chunk_size = self.DEFAULT_RELATED_CHUNK_SIZE
        self._prefetch_related_fields = set()
        self._select_related_fields = set()

    def configure(self, chunk_size=None, related_chunk_size=None, 
                 select_related=None, prefetch_related=None):
        """
        Configure bulk operation parameters for this manager.
        
        Args:
            chunk_size: Number of objects to process in each bulk operation chunk
            related_chunk_size: Number of objects to fetch in each related object query
            select_related: List of fields to always select_related in bulk operations
            prefetch_related: List of fields to always prefetch_related in bulk operations
        """
        if chunk_size is not None:
            self._chunk_size = chunk_size
        if related_chunk_size is not None:
            self._related_chunk_size = related_chunk_size
        if select_related:
            self._select_related_fields.update(select_related)
        if prefetch_related:
            self._prefetch_related_fields.update(prefetch_related)

    def _load_originals_optimized(self, pks, fields_to_fetch=None):
        """
        Optimized loading of original instances with smart batching and field selection.
        """
        queryset = self.model.objects.filter(pk__in=pks)
        
        # Only select specific fields if provided
        if fields_to_fetch:
            queryset = queryset.only('pk', *fields_to_fetch)
            
        # Apply configured related field optimizations
        if self._select_related_fields:
            queryset = queryset.select_related(*self._select_related_fields)
        if self._prefetch_related_fields:
            queryset = queryset.prefetch_related(*self._prefetch_related_fields)
            
        # Batch load in chunks to avoid memory issues
        all_originals = []
        for i in range(0, len(pks), self._related_chunk_size):
            chunk_pks = pks[i:i + self._related_chunk_size]
            chunk_originals = list(queryset.filter(pk__in=chunk_pks))
            all_originals.extend(chunk_originals)
            
        return all_originals

    def _get_fields_to_fetch(self, objs, fields):
        """
        Determine which fields need to be fetched based on what's being updated
        and what's needed for hooks.
        """
        fields_to_fetch = set(fields)
        
        # Add fields needed by registered hooks
        from django_bulk_hooks.registry import get_hooks
        hooks = get_hooks(self.model, "before_update") + get_hooks(self.model, "after_update")
        
        for handler_cls, method_name, condition, _ in hooks:
            if condition:
                # If there's a condition, we need all fields it might access
                fields_to_fetch.update(condition.get_required_fields())
                
        return fields_to_fetch

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
            # Determine which fields we need to fetch
            fields_to_fetch = self._get_fields_to_fetch(objs, fields)
            
            # Load originals efficiently
            pks = [obj.pk for obj in objs if obj.pk is not None]
            originals = self._load_originals_optimized(pks, fields_to_fetch)
            
            # Create a mapping for quick lookup
            original_map = {obj.pk: obj for obj in originals}
            
            # Align originals with new instances
            aligned_originals = [original_map.get(obj.pk) for obj in objs]

            ctx = HookContext(model_cls)

            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_UPDATE, objs, aligned_originals, ctx=ctx)

            # Then run business logic hooks
            engine.run(model_cls, BEFORE_UPDATE, objs, aligned_originals, ctx=ctx)

            # Automatically detect fields that were modified during BEFORE_UPDATE hooks
            modified_fields = self._detect_modified_fields(objs, aligned_originals)
            if modified_fields:
                fields_set = set(fields)
                fields_set.update(modified_fields)
                fields = list(fields_set)

        # Process in chunks
        for i in range(0, len(objs), self._chunk_size):
            chunk = objs[i:i + self._chunk_size]
            super(models.Manager, self).bulk_update(chunk, fields, **kwargs)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_UPDATE, objs, aligned_originals, ctx=ctx)

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
        if not objs:
            return []

        model_cls = self.model
        result = []

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_create expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        if not bypass_hooks:
            ctx = HookContext(model_cls)

            # Process validation in chunks to avoid memory issues
            if not bypass_validation:
                for i in range(0, len(objs), self._chunk_size):
                    chunk = objs[i:i + self._chunk_size]
                    engine.run(model_cls, VALIDATE_CREATE, chunk, ctx=ctx)

            # Process before_create hooks in chunks
            for i in range(0, len(objs), self._chunk_size):
                chunk = objs[i:i + self._chunk_size]
                engine.run(model_cls, BEFORE_CREATE, chunk, ctx=ctx)

        # Perform bulk create in chunks
        for i in range(0, len(objs), self._chunk_size):
            chunk = objs[i:i + self._chunk_size]
            created_chunk = super(models.Manager, self).bulk_create(chunk, **kwargs)
            result.extend(created_chunk)

        if not bypass_hooks:
            # Process after_create hooks in chunks
            for i in range(0, len(result), self._chunk_size):
                chunk = result[i:i + self._chunk_size]
                engine.run(model_cls, AFTER_CREATE, chunk, ctx=ctx)

        return result

    @transaction.atomic
    def bulk_delete(self, objs, batch_size=None, bypass_hooks=False, bypass_validation=False):
        if not objs:
            return []

        model_cls = self.model
        chunk_size = batch_size or self._chunk_size

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_delete expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        ctx = HookContext(model_cls)

        if not bypass_hooks:
            # Process hooks in chunks
            for i in range(0, len(objs), chunk_size):
                chunk = objs[i:i + chunk_size]
                
                if not bypass_validation:
                    engine.run(model_cls, VALIDATE_DELETE, chunk, ctx=ctx)
                engine.run(model_cls, BEFORE_DELETE, chunk, ctx=ctx)

        # Collect PKs and delete in chunks
        pks = [obj.pk for obj in objs if obj.pk is not None]
        for i in range(0, len(pks), chunk_size):
            chunk_pks = pks[i:i + chunk_size]
            model_cls._base_manager.filter(pk__in=chunk_pks).delete()

        if not bypass_hooks:
            # Process after_delete hooks in chunks
            for i in range(0, len(objs), chunk_size):
                chunk = objs[i:i + chunk_size]
                engine.run(model_cls, AFTER_DELETE, chunk, ctx=ctx)

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
