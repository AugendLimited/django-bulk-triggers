from django.db import models, transaction
from django.db.models import AutoField

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
        """
        Enhanced bulk_create that handles multi-table inheritance (MTI) and single-table models.
        Falls back to Django's standard bulk_create for single-table models.
        Fires hooks as usual.
        """
        model_cls = self.model

        if not objs:
            return []

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_create expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        # Fire hooks before DB ops
        if not bypass_hooks:
            ctx = HookContext(model_cls)
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)
            engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)

        # MTI detection: if inheritance chain > 1, use MTI logic
        inheritance_chain = self._get_inheritance_chain()
        if len(inheritance_chain) <= 1:
            # Single-table: use Django's standard bulk_create
            result = []
            for i in range(0, len(objs), self.CHUNK_SIZE):
                chunk = objs[i : i + self.CHUNK_SIZE]
                result.extend(super(models.Manager, self).bulk_create(chunk, **kwargs))
        else:
            # Multi-table: use workaround (parent saves, child bulk)
            result = self._mti_bulk_create(objs, inheritance_chain, **kwargs)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_CREATE, result, ctx=ctx)

        return result

    def _get_inheritance_chain(self):
        """
        Get the complete inheritance chain from root parent to current model.
        Returns list of model classes in order: [RootParent, Parent, Child]
        """
        chain = []
        current_model = self.model
        while current_model:
            if not current_model._meta.proxy:
                chain.append(current_model)
            parents = [
                parent
                for parent in current_model._meta.parents.keys()
                if not parent._meta.proxy
            ]
            current_model = parents[0] if parents else None
        chain.reverse()
        return chain

    def _mti_bulk_create(self, objs, inheritance_chain, **kwargs):
        """
        Implements workaround: individual saves for parents, bulk create for child.
        """
        batch_size = kwargs.get("batch_size") or len(objs)
        created_objects = []
        with transaction.atomic(using=self.db, savepoint=False):
            for i in range(0, len(objs), batch_size):
                batch = objs[i : i + batch_size]
                batch_result = self._process_mti_batch(
                    batch, inheritance_chain, **kwargs
                )
                created_objects.extend(batch_result)
        return created_objects

    def _process_mti_batch(self, batch, inheritance_chain, **kwargs):
        """
        Process a single batch of objects through the inheritance chain.
        """
        # Step 1: Handle parent tables with individual saves (needed for PKs)
        parent_objects_map = {}
        for obj in batch:
            parent_instances = {}
            current_parent = None
            for model_class in inheritance_chain[:-1]:
                parent_obj = self._create_parent_instance(
                    obj, model_class, current_parent
                )
                parent_obj.save()
                parent_instances[model_class] = parent_obj
                current_parent = parent_obj
            parent_objects_map[id(obj)] = parent_instances
        # Step 2: Bulk insert for child objects
        child_model = inheritance_chain[-1]
        child_objects = []
        for obj in batch:
            child_obj = self._create_child_instance(
                obj, child_model, parent_objects_map.get(id(obj), {})
            )
            child_objects.append(child_obj)
        # Use Django's _base_manager for child table to avoid recursion
        child_manager = child_model._base_manager
        child_manager._for_write = True
        created = child_manager.bulk_create(child_objects, **kwargs)
        # Step 3: Update original objects with generated PKs and state
        pk_field_name = child_model._meta.pk.name
        for orig_obj, child_obj in zip(batch, created):
            setattr(orig_obj, pk_field_name, getattr(child_obj, pk_field_name))
            orig_obj._state.adding = False
            orig_obj._state.db = self.db
        return batch

    def _create_parent_instance(self, source_obj, parent_model, current_parent):
        parent_obj = parent_model()
        for field in parent_model._meta.local_fields:
            # Only copy if the field exists on the source and is not None
            if hasattr(source_obj, field.name):
                value = getattr(source_obj, field.name, None)
                if value is not None:
                    setattr(parent_obj, field.name, value)
        if current_parent is not None:
            for field in parent_model._meta.local_fields:
                if (
                    hasattr(field, "remote_field")
                    and field.remote_field
                    and field.remote_field.model == current_parent.__class__
                ):
                    setattr(parent_obj, field.name, current_parent)
                    break
        return parent_obj

    def _create_child_instance(self, source_obj, child_model, parent_instances):
        child_obj = child_model()
        for field in child_model._meta.local_fields:
            if isinstance(field, AutoField):
                continue
            if hasattr(source_obj, field.name):
                value = getattr(source_obj, field.name, None)
                if value is not None:
                    setattr(child_obj, field.name, value)
        for parent_model, parent_instance in parent_instances.items():
            parent_link = child_model._meta.get_ancestor_link(parent_model)
            if parent_link:
                setattr(child_obj, parent_link.name, parent_instance)
        return child_obj

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
