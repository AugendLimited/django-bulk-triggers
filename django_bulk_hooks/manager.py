from django.db import models, transaction, connections
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

    @transaction.atomic
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
        Insert each of the instances into the database. Behaves like Django's bulk_create,
        but supports multi-table inheritance (MTI) models. All arguments are supported and
        passed through to the correct logic. For MTI, only a subset of options may be supported.
        """
        model_cls = self.model

        if batch_size is not None and batch_size <= 0:
            raise ValueError("Batch size must be a positive integer.")

        # Check that the parents share the same concrete model with our model to detect inheritance pattern
        # (Do NOT raise for MTI, just skip the exception)
        for parent in model_cls._meta.all_parents:
            if parent._meta.concrete_model is not model_cls._meta.concrete_model:
                # Do not raise, just continue
                break

        if not objs:
            return objs

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_create expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        # Set auto_now_add/auto_now fields before DB ops
        self._set_auto_now_fields(objs, model_cls)

        # Fire hooks before DB ops
        if not bypass_hooks:
            ctx = HookContext(model_cls)
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)
            engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)

        opts = model_cls._meta
        if unique_fields:
            unique_fields = [
                model_cls._meta.get_field(opts.pk.name if name == "pk" else name)
                for name in unique_fields
            ]
        if update_fields:
            update_fields = [model_cls._meta.get_field(name) for name in update_fields]
        on_conflict = self._check_bulk_create_options(
            ignore_conflicts,
            update_conflicts,
            update_fields,
            unique_fields,
        )
        self._for_write = True
        fields = [f for f in opts.concrete_fields if not f.generated]
        objs = list(objs)
        objs_with_pk, objs_without_pk = self._prepare_for_bulk_create(objs)
        with transaction.atomic(using=self.db, savepoint=False):
            self._handle_order_with_respect_to(objs)
            if objs_with_pk:
                returned_columns = self._batched_insert(
                    objs_with_pk,
                    fields,
                    batch_size,
                    on_conflict=on_conflict,
                    update_fields=update_fields,
                    unique_fields=unique_fields,
                )
                for obj_with_pk, results in zip(objs_with_pk, returned_columns):
                    for result, field in zip(results, opts.db_returning_fields):
                        if field != opts.pk:
                            setattr(obj_with_pk, field.attname, result)
                for obj_with_pk in objs_with_pk:
                    obj_with_pk._state.adding = False
                    obj_with_pk._state.db = self.db
            if objs_without_pk:
                fields_wo_pk = [f for f in fields if not isinstance(f, AutoField)]
                returned_columns = self._batched_insert(
                    objs_without_pk,
                    fields_wo_pk,
                    batch_size,
                    on_conflict=on_conflict,
                    update_fields=update_fields,
                    unique_fields=unique_fields,
                )
                connection = connections[self.db]
                if (
                    connection.features.can_return_rows_from_bulk_insert
                    and on_conflict is None
                ):
                    assert len(returned_columns) == len(objs_without_pk)
                for obj_without_pk, results in zip(objs_without_pk, returned_columns):
                    for result, field in zip(results, opts.db_returning_fields):
                        setattr(obj_without_pk, field.attname, result)
                    obj_without_pk._state.adding = False
                    obj_without_pk._state.db = self.db

        if not bypass_hooks:
            engine.run(model_cls, AFTER_CREATE, objs, ctx=ctx)

        return objs

    # --- Private helper methods (moved to bottom for clarity) ---

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
        Sets auto_now_add/auto_now fields for each model in the chain.
        """
        batch_size = kwargs.get("batch_size") or len(objs)
        created_objects = []
        with transaction.atomic(using=self.db, savepoint=False):
            for i in range(0, len(objs), batch_size):
                batch = objs[i : i + batch_size]
                # Set auto_now fields for each model in the chain
                for model in inheritance_chain:
                    self._set_auto_now_fields(batch, model)
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
        # Handle order_with_respect_to like Django's bulk_create
        self._handle_order_with_respect_to(child_objects)
        # If the child model is still MTI, call our own logic recursively
        if len([p for p in child_model._meta.parents.keys() if not p._meta.proxy]) > 0:
            # Build inheritance chain for the child model
            inheritance_chain = []
            current_model = child_model
            while current_model:
                if not current_model._meta.proxy:
                    inheritance_chain.append(current_model)
                parents = [
                    parent
                    for parent in current_model._meta.parents.keys()
                    if not parent._meta.proxy
                ]
                current_model = parents[0] if parents else None
            inheritance_chain.reverse()
            created = self._mti_bulk_create(child_objects, inheritance_chain, **kwargs)
        else:
            # Single-table, safe to use bulk_create
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

    def _set_auto_now_fields(self, objs, model):
        """
        Set auto_now_add and auto_now fields on objects before bulk_create.
        """
        from django.utils import timezone

        now = timezone.now()
        for obj in objs:
            for field in model._meta.local_fields:
                if (
                    getattr(field, "auto_now_add", False)
                    and getattr(obj, field.name, None) is None
                ):
                    setattr(obj, field.name, now)
                if getattr(field, "auto_now", False):
                    setattr(obj, field.name, now)

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

    def _handle_order_with_respect_to(self, objs):
        """
        Set _order fields for models with order_with_respect_to.
        """
        for obj in objs:
            order_with_respect_to = obj.__class__._meta.order_with_respect_to
            if order_with_respect_to:
                key = getattr(obj, order_with_respect_to.attname)
                obj._order = key
        # Group by the value of order_with_respect_to
        groups = defaultdict(list)
        for obj in objs:
            order_with_respect_to = obj.__class__._meta.order_with_respect_to
            if order_with_respect_to:
                key = getattr(obj, order_with_respect_to.attname)
                groups[key].append(obj)
        # Enumerate within each group
        for group_objs in groups.values():
            for i, obj in enumerate(group_objs):
                obj._order = i
