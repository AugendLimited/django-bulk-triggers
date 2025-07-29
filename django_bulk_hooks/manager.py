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
    CHUNK_SIZE = 200

    def get_queryset(self):
        return HookQuerySet(self.model, using=self._db)

    def _has_multi_table_inheritance(self, model_cls):
        """
        Check if this model uses multi-table inheritance.
        """
        return (
            model_cls._meta.parents and 
            not all(parent._meta.abstract for parent in model_cls._meta.parents.values())
        )
    
    def _get_base_model(self, model_cls):
        """
        Get the base model (first non-abstract parent or self).
        """
        base_model = model_cls
        while base_model._meta.parents:
            parent = next(iter(base_model._meta.parents.values()))
            if not parent._meta.abstract:
                base_model = parent
            else:
                break
        return base_model
    
    def _extract_base_objects(self, objs, model_cls):
        """
        Extract base model objects from inherited objects.
        """
        base_model = self._get_base_model(model_cls)
        base_objects = []
        
        for obj in objs:
            base_obj = base_model()
            for field in base_model._meta.fields:
                if field.name != 'id' and hasattr(obj, field.name):
                    setattr(base_obj, field.name, getattr(obj, field.name))
            base_objects.append(base_obj)
        
        return base_objects
    
    def _extract_child_objects(self, objs, model_cls):
        """
        Extract child model objects from inherited objects.
        """
        child_objects = []
        
        for obj in objs:
            child_obj = model_cls()
            child_obj.pk = obj.pk  # Set the same PK as base
            
            # Copy only fields specific to this model
            for field in model_cls._meta.fields:
                if (field.name != 'id' and 
                    field.model == model_cls and 
                    hasattr(obj, field.name)):
                    setattr(child_obj, field.name, getattr(obj, field.name))
            
            child_objects.append(child_obj)
        
        return child_objects
    
    def _bulk_create_inherited(self, objs, **kwargs):
        """
        Handle bulk create for inherited models by handling each table separately.
        """
        if not objs:
            return []
        
        model_cls = self.model
        result = []
        
        # Group objects by their actual class
        objects_by_class = {}
        for obj in objs:
            obj_class = obj.__class__
            if obj_class not in objects_by_class:
                objects_by_class[obj_class] = []
            objects_by_class[obj_class].append(obj)
        
        for obj_class, class_objects in objects_by_class.items():
            # Check if this class has multi-table inheritance
            parent_models = [p for p in obj_class._meta.get_parent_list() 
                           if not p._meta.abstract]
            
            if not parent_models:
                # No inheritance, use standard bulk_create
                chunk_result = super(models.Manager, self).bulk_create(class_objects, **kwargs)
                result.extend(chunk_result)
                continue
            
            # Handle multi-table inheritance
            # Step 1: Bulk create base objects without hooks
            base_objects = self._extract_base_objects(class_objects, obj_class)
            created_base = super(models.Manager, self).bulk_create(base_objects, **kwargs)
            
            # Step 2: Update original objects with base IDs
            for obj, base_obj in zip(class_objects, created_base):
                obj.pk = base_obj.pk
                obj._state.adding = False
            
            # Step 3: Bulk create child objects without hooks
            child_objects = self._extract_child_objects(class_objects, obj_class)
            if child_objects:
                # Use _base_manager to avoid recursion
                obj_class._base_manager.bulk_create(child_objects, **kwargs)
            
            result.extend(class_objects)
        
        return result

    @transaction.atomic
    def bulk_update(
        self, objs, fields, bypass_hooks=False, bypass_validation=False, **kwargs
    ):
        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_update expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        if not bypass_hooks:
            # Load originals for hook comparison and ensure they match the order of new instances
            original_map = {
                obj.pk: obj for obj in model_cls.objects.filter(pk__in=[obj.pk for obj in objs])
            }
            originals = [original_map.get(obj.pk) for obj in objs]

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

        modified_fields = set()

        # Since original_instances is now ordered to match new_instances, we can zip them directly
        for new_instance, original in zip(new_instances, original_instances):
            if new_instance.pk is None or original is None:
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

        # Check if this model uses multi-table inheritance
        has_multi_table_inheritance = self._has_multi_table_inheritance(model_cls)

        result = []

        if not bypass_hooks:
            ctx = HookContext(model_cls)

            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)

            # Then run business logic hooks
            engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)

        # Perform bulk create in chunks
        for i in range(0, len(objs), self.CHUNK_SIZE):
            chunk = objs[i : i + self.CHUNK_SIZE]
            
            if has_multi_table_inheritance:
                # Use our multi-table bulk create
                created_chunk = self._bulk_create_inherited(chunk, **kwargs)
            else:
                # Use Django's standard bulk create
                created_chunk = super(models.Manager, self).bulk_create(chunk, **kwargs)
            
            result.extend(created_chunk)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_CREATE, result, ctx=ctx)

        return result

    @transaction.atomic
    def bulk_delete(
        self, objs, batch_size=None, bypass_hooks=False, bypass_validation=False
    ):
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
        
        # Use base manager for the actual deletion to prevent recursion
        # The hooks have already been fired above, so we don't need them again
        model_cls._base_manager.filter(pk__in=pks).delete()

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
