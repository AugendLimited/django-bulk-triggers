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
                obj.pk: obj
                for obj in model_cls.objects.filter(pk__in=[obj.pk for obj in objs])
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
    def mti_bulk_create(
        self, objs, bypass_hooks=False, bypass_validation=False, **kwargs
    ):
        """
        Bulk create for Multi-Table Inheritance scenarios.

        This implements the hybrid approach:
        1. Insert parent tables individually to get primary keys back
        2. Bulk insert into the childmost table

        This works around Django's limitation where bulk_create doesn't return
        primary keys for auto-increment fields, which prevents inserting into
        child tables that reference the parent.
        """
        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"mti_bulk_create expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        # Check if this is actually an MTI scenario
        if not self._is_mti_scenario(model_cls):
            # Fall back to regular bulk_create for non-MTI models
            return self.bulk_create(objs, bypass_hooks, bypass_validation, **kwargs)

        result = []

        if not bypass_hooks:
            ctx = HookContext(model_cls)

            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)

            # Then run business logic hooks
            engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)

        # Group objects by their concrete model to handle each inheritance level
        concrete_models = self._get_concrete_models(model_cls)

        # Process each inheritance level from parent to child
        for concrete_model in concrete_models:
            model_objs = [obj for obj in objs if isinstance(obj, concrete_model)]

            if not model_objs:
                continue

            if concrete_model == model_cls:
                # This is the childmost model - use bulk insert
                for i in range(0, len(model_objs), self.CHUNK_SIZE):
                    chunk = model_objs[i : i + self.CHUNK_SIZE]
                    result.extend(
                        super(models.Manager, self).bulk_create(chunk, **kwargs)
                    )
            else:
                # This is a parent model - insert individually to get PKs back
                for obj in model_objs:
                    # Use the base manager to avoid hook recursion
                    obj.save(using=self._db)
                    result.append(obj)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_CREATE, result, ctx=ctx)

        return result

    def _is_mti_scenario(self, model_cls):
        """
        Check if this model is part of a Multi-Table Inheritance scenario.
        """
        # Check if the model has a parent that's not abstract
        if model_cls._meta.parents:
            for parent_model in model_cls._meta.parents.values():
                if not parent_model._meta.abstract:
                    return True

        # Check if this model is a parent of non-abstract models
        for related_model in model_cls._meta.get_fields():
            if hasattr(related_model, "related_model") and related_model.related_model:
                if (
                    related_model.related_model._meta.parents
                    and model_cls in related_model.related_model._meta.parents.values()
                ):
                    return True

        return False

    def _get_concrete_models(self, model_cls):
        """
        Get all concrete models in the inheritance hierarchy, ordered from parent to child.
        """
        models = []

        # Get all parent models (non-abstract)
        current_model = model_cls
        while current_model._meta.parents:
            for parent_model in current_model._meta.parents.values():
                if not parent_model._meta.abstract:
                    if parent_model not in models:
                        models.insert(0, parent_model)
            current_model = list(current_model._meta.parents.values())[0]

        # Add the current model
        if model_cls not in models:
            models.append(model_cls)

        return models

    @transaction.atomic
    def mti_bulk_create_with_uuid(
        self, objs, bypass_hooks=False, bypass_validation=False, **kwargs
    ):
        """
        Bulk create for Multi-Table Inheritance scenarios using UUID primary keys.

        This implements approach #1 from Django's comments:
        - Use non-autoincrement primary keys (UUIDs)
        - This allows bulk_create to return primary keys
        - Works with all inheritance levels simultaneously

        Requirements:
        - Model must use UUIDField as primary key
        - UUIDs must be pre-assigned before calling this method
        """
        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"mti_bulk_create_with_uuid expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        # Check if this is actually an MTI scenario
        if not self._is_mti_scenario(model_cls):
            # Fall back to regular bulk_create for non-MTI models
            return self.bulk_create(objs, bypass_hooks, bypass_validation, **kwargs)

        # Verify all objects have UUID primary keys assigned
        for obj in objs:
            if obj.pk is None:
                raise ValueError(
                    f"Object {obj} must have a UUID primary key assigned before calling mti_bulk_create_with_uuid"
                )
            if not self._is_uuid_field(obj._meta.pk):
                raise ValueError(
                    f"Model {model_cls.__name__} must use UUIDField as primary key for mti_bulk_create_with_uuid"
                )

        result = []

        if not bypass_hooks:
            ctx = HookContext(model_cls)

            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)

            # Then run business logic hooks
            engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)

        # Group objects by their concrete model to handle each inheritance level
        concrete_models = self._get_concrete_models(model_cls)

        # Process each inheritance level from parent to child
        for concrete_model in concrete_models:
            model_objs = [obj for obj in objs if isinstance(obj, concrete_model)]

            if not model_objs:
                continue

            # Use bulk create for all levels since we have UUIDs
            for i in range(0, len(model_objs), self.CHUNK_SIZE):
                chunk = model_objs[i : i + self.CHUNK_SIZE]
                # Use the base manager to avoid hook recursion
                created = concrete_model._base_manager.bulk_create(chunk, **kwargs)
                result.extend(created)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_CREATE, result, ctx=ctx)

        return result

    def _is_uuid_field(self, field):
        """
        Check if a field is a UUID field.
        """
        from django.db import models

        return isinstance(field, models.UUIDField)

    def mti_bulk_create_auto_uuid(
        self, objs, bypass_hooks=False, bypass_validation=False, **kwargs
    ):
        """
        Bulk create for Multi-Table Inheritance scenarios with automatic UUID generation.

        This is a convenience method that automatically assigns UUIDs to objects
        before calling mti_bulk_create_with_uuid.
        """
        import uuid

        if not objs:
            return []

        model_cls = self.model

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"mti_bulk_create_auto_uuid expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        # Check if this is actually an MTI scenario
        if not self._is_mti_scenario(model_cls):
            # Fall back to regular bulk_create for non-MTI models
            return self.bulk_create(objs, bypass_hooks, bypass_validation, **kwargs)

        # Verify the model uses UUID primary key
        if not self._is_uuid_field(model_cls._meta.pk):
            raise ValueError(
                f"Model {model_cls.__name__} must use UUIDField as primary key for mti_bulk_create_auto_uuid"
            )

        # Assign UUIDs to objects that don't have them
        for obj in objs:
            if obj.pk is None:
                obj.pk = uuid.uuid4()

        # Now call the UUID-based bulk create
        return self.mti_bulk_create_with_uuid(
            objs, bypass_hooks, bypass_validation, **kwargs
        )

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
