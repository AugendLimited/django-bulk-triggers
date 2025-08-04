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


class HookQuerySet(models.QuerySet):
    CHUNK_SIZE = 200

    @transaction.atomic
    def delete(self):
        objs = list(self)
        if not objs:
            return 0
        # Call the base QuerySet implementation to avoid recursion
        return super().bulk_delete(objs)

    @transaction.atomic
    def update(self, **kwargs):
        instances = list(self)
        if not instances:
            return 0

        model_cls = self.model
        pks = [obj.pk for obj in instances]

        # Load originals for hook comparison and ensure they match the order of instances
        # Use the base manager to avoid recursion
        original_map = {obj.pk: obj for obj in model_cls._base_manager.filter(pk__in=pks)}
        originals = [original_map.get(obj.pk) for obj in instances]

        # Apply field updates to instances
        for obj in instances:
            for field, value in kwargs.items():
                setattr(obj, field, value)

        # Run BEFORE_UPDATE hooks
        ctx = HookContext(model_cls)
        engine.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

        # Use Django's built-in update logic directly
        # Call the base QuerySet implementation to avoid recursion
        update_count = super().update(**kwargs)

        # Run AFTER_UPDATE hooks
        engine.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)

        return update_count

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
        but supports multi-table inheritance (MTI) models and hooks. All arguments are supported and
        passed through to the correct logic. For MTI, only a subset of options may be supported.
        """
        model_cls = self.model

        # When you bulk insert you don't get the primary keys back (if it's an
        # autoincrement, except if can_return_rows_from_bulk_insert=True), so
        # you can't insert into the child tables which references this. There
        # are two workarounds:
        # 1) This could be implemented if you didn't have an autoincrement pk
        # 2) You could do it by doing O(n) normal inserts into the parent
        #    tables to get the primary keys back and then doing a single bulk
        #    insert into the childmost table.
        # We currently set the primary keys on the objects when using
        # PostgreSQL via the RETURNING ID clause. It should be possible for
        # Oracle as well, but the semantics for extracting the primary keys is
        # trickier so it's not done yet.
        if batch_size is not None and batch_size <= 0:
            raise ValueError("Batch size must be a positive integer.")

        # Check for MTI - if we detect multi-table inheritance, we need special handling
        # This follows Django's approach: check that the parents share the same concrete model
        # with our model to detect the inheritance pattern ConcreteGrandParent ->
        # MultiTableParent -> ProxyChild. Simply checking self.model._meta.proxy would not
        # identify that case as involving multiple tables.
        is_mti = False
        for parent in model_cls._meta.all_parents:
            if parent._meta.concrete_model is not model_cls._meta.concrete_model:
                is_mti = True
                break

        if not objs:
            return objs

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_create expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        # Fire hooks before DB ops
        if not bypass_hooks:
            print(f"DEBUG: Firing BEFORE_CREATE hooks for {model_cls}")
            print(f"DEBUG: Number of objects: {len(objs)}")
            print(f"DEBUG: Object types: {[type(obj) for obj in objs]}")
            print(f"DEBUG: QuerySet type: {type(self)}")
            print(f"DEBUG: Is this HookQuerySet? {isinstance(self, HookQuerySet)}")
            ctx = HookContext(model_cls)
            if not bypass_validation:
                print(f"DEBUG: Running VALIDATE_CREATE hooks")
                engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)
            print(f"DEBUG: Running BEFORE_CREATE hooks")
            engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)
        else:
            print(f"DEBUG: Skipping hooks due to bypass_hooks=True for {model_cls}")

        # For MTI models, we need to handle them specially
        if is_mti:
            # Use our MTI-specific logic
            # Filter out custom parameters that Django's bulk_create doesn't accept
            mti_kwargs = {
                'batch_size': batch_size,
                'ignore_conflicts': ignore_conflicts,
                'update_conflicts': update_conflicts,
                'update_fields': update_fields,
                'unique_fields': unique_fields,
            }
            # Remove custom hook kwargs if present in self.bulk_create signature
            result = self._mti_bulk_create(
                objs,
                **{k: v for k, v in mti_kwargs.items() if k not in ['bypass_hooks', 'bypass_validation']}
            )
        else:
            # For single-table models, use Django's built-in bulk_create
            # but we need to call it on the base manager to avoid recursion
            # Filter out custom parameters that Django's bulk_create doesn't accept

            # Use Django's original QuerySet to avoid recursive calls
            from django.db.models import QuerySet
            original_qs = QuerySet(model_cls, using=self.db)
            result = original_qs.bulk_create(
                objs,
                batch_size=batch_size,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

        # Fire AFTER_CREATE hooks
        if not bypass_hooks:
            print(f"DEBUG: Firing AFTER_CREATE hooks for {model_cls}")
            print(f"DEBUG: Number of objects: {len(objs)}")
            print(f"DEBUG: QuerySet type: {type(self)}")
            print(f"DEBUG: Is this HookQuerySet? {isinstance(self, HookQuerySet)}")
            engine.run(model_cls, AFTER_CREATE, objs, ctx=ctx)
        else:
            print(f"DEBUG: Skipping AFTER_CREATE hooks due to bypass_hooks=True for {model_cls}")

        return result

    @transaction.atomic
    def bulk_update(self, objs, fields, bypass_hooks=False, bypass_validation=False, **kwargs):
        """
        Bulk update objects in the database.
        """
        import inspect
        print(f"DEBUG: QuerySet.bulk_update called with:")
        print(f"  - self: {type(self)}")
        print(f"  - objs: {type(objs)}")
        print(f"  - fields: {fields}")
        print(f"  - bypass_hooks: {bypass_hooks}")
        print(f"  - bypass_validation: {bypass_validation}")
        print(f"  - kwargs: {kwargs}")
        print(f"DEBUG: Method signature: {inspect.signature(self.bulk_update)}")
        
        model_cls = self.model
        print(f"DEBUG: Model class: {model_cls}")
        print(f"DEBUG: bypass_hooks value: {bypass_hooks}")
        print(f"DEBUG: QuerySet type: {type(self)}")
        print(f"DEBUG: Is this HookQuerySet? {isinstance(self, HookQuerySet)}")
        
        if not objs:
            return []

        if any(not isinstance(obj, model_cls) for obj in objs):
            raise TypeError(
                f"bulk_update expected instances of {model_cls.__name__}, but got {set(type(obj).__name__ for obj in objs)}"
            )

        if not bypass_hooks:
            # Load originals for hook comparison and ensure they match the order of new instances
            # Use the base manager to avoid recursion
            original_map = {
                obj.pk: obj
                for obj in model_cls._base_manager.filter(pk__in=[obj.pk for obj in objs])
            }
            originals = [original_map.get(obj.pk) for obj in objs]

            ctx = HookContext(model_cls)

            # Run validation hooks first
            if not bypass_validation:
                engine.run(model_cls, VALIDATE_UPDATE, objs, originals, ctx=ctx)

            # Then run business logic hooks
            if not bypass_hooks:
                print(f"DEBUG: Firing BEFORE_UPDATE hooks for {model_cls}")
                print(f"DEBUG: Number of objects: {len(objs)}")
                print(f"DEBUG: Object types: {[type(obj) for obj in objs]}")
                engine.run(model_cls, BEFORE_UPDATE, objs, originals, ctx=ctx)
            else:
                print(f"DEBUG: Skipping hooks due to bypass_hooks=True for {model_cls}")

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
            # Filter out custom parameters that Django's bulk_update doesn't accept
            django_kwargs = {k: v for k, v in kwargs.items() if k not in ['bypass_hooks', 'bypass_validation']}
            super().bulk_update(chunk, fields, **django_kwargs)

        if not bypass_hooks:
            print(f"DEBUG: Firing AFTER_UPDATE hooks for {model_cls}")
            print(f"DEBUG: Number of objects: {len(objs)}")
            engine.run(model_cls, AFTER_UPDATE, objs, originals, ctx=ctx)
        else:
            print(f"DEBUG: Skipping AFTER_UPDATE hooks due to bypass_hooks=True for {model_cls}")

        return objs

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

        # Call the base QuerySet implementation to avoid recursion
        # The hooks have already been fired above, so we don't need them again
        super().bulk_delete(objs, batch_size=batch_size)

        if not bypass_hooks:
            engine.run(model_cls, AFTER_DELETE, objs, ctx=ctx)

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

    def _mti_bulk_create(self, objs, inheritance_chain=None, **kwargs):
        """
        Implements Django's suggested workaround #2 for MTI bulk_create:
        O(n) normal inserts into parent tables to get primary keys back,
        then single bulk insert into childmost table.
        Sets auto_now_add/auto_now fields for each model in the chain.
        """
        # Remove custom hook kwargs before passing to Django internals
        django_kwargs = {k: v for k, v in kwargs.items() if k not in ['bypass_hooks', 'bypass_validation']}
        if inheritance_chain is None:
            inheritance_chain = self._get_inheritance_chain()

        # Safety check to prevent infinite recursion
        if len(inheritance_chain) > 10:  # Arbitrary limit to prevent infinite loops
            raise ValueError(
                "Inheritance chain too deep - possible infinite recursion detected"
            )

        batch_size = django_kwargs.get("batch_size") or len(objs)
        created_objects = []
        with transaction.atomic(using=self.db, savepoint=False):
            for i in range(0, len(objs), batch_size):
                batch = objs[i : i + batch_size]
                batch_result = self._process_mti_batch(
                    batch, inheritance_chain, **django_kwargs
                )
                created_objects.extend(batch_result)
        return created_objects

    def _process_mti_batch(self, batch, inheritance_chain, **kwargs):
        """
        Process a single batch of objects through the inheritance chain.
        Implements Django's suggested workaround #2: O(n) normal inserts into parent
        tables to get primary keys back, then single bulk insert into childmost table.
        """
        # For MTI, we need to save parent objects first to get PKs
        # Then we can use Django's bulk_create for the child objects
        parent_objects_map = {}

        # Step 1: Do O(n) normal inserts into parent tables to get primary keys back
        # Get bypass_hooks from kwargs
        bypass_hooks = kwargs.get('bypass_hooks', False)
        bypass_validation = kwargs.get('bypass_validation', False)
        
        for obj in batch:
            parent_instances = {}
            current_parent = None
            for model_class in inheritance_chain[:-1]:
                parent_obj = self._create_parent_instance(
                    obj, model_class, current_parent
                )
                
                # Fire parent hooks if not bypassed
                if not bypass_hooks:
                    ctx = HookContext(model_class)
                    if not bypass_validation:
                        engine.run(model_class, VALIDATE_CREATE, [parent_obj], ctx=ctx)
                    engine.run(model_class, BEFORE_CREATE, [parent_obj], ctx=ctx)
                
                # Use Django's base manager to create the object and get PKs back
                # This bypasses hooks and the MTI exception
                field_values = {
                    field.name: getattr(parent_obj, field.name)
                    for field in model_class._meta.local_fields
                    if hasattr(parent_obj, field.name) and getattr(parent_obj, field.name) is not None
                }
                created_obj = model_class._base_manager.using(self.db).create(**field_values)
                
                # Update the parent_obj with the created object's PK
                parent_obj.pk = created_obj.pk
                parent_obj._state.adding = False
                parent_obj._state.db = self.db
                
                # Fire AFTER_CREATE hooks for parent
                if not bypass_hooks:
                    engine.run(model_class, AFTER_CREATE, [parent_obj], ctx=ctx)
                
                parent_instances[model_class] = parent_obj
                current_parent = parent_obj
            parent_objects_map[id(obj)] = parent_instances

        # Step 2: Create all child objects and do single bulk insert into childmost table
        child_model = inheritance_chain[-1]
        all_child_objects = []
        for obj in batch:
            child_obj = self._create_child_instance(
                obj, child_model, parent_objects_map.get(id(obj), {})
            )
            all_child_objects.append(child_obj)

        # Step 2.5: Use Django's internal bulk_create infrastructure
        if all_child_objects:
            # Get the base manager's queryset
            base_qs = child_model._base_manager.using(self.db)
            
            # Use Django's exact approach: call _prepare_for_bulk_create then partition
            base_qs._prepare_for_bulk_create(all_child_objects)
            
            # Implement our own partition since itertools.partition might not be available
            objs_without_pk, objs_with_pk = [], []
            for obj in all_child_objects:
                if obj._is_pk_set():
                    objs_with_pk.append(obj)
                else:
                    objs_without_pk.append(obj)
            
            # Use Django's internal _batched_insert method
            opts = child_model._meta
            # For child models in MTI, we need to include the foreign key to the parent
            # but exclude the primary key since it's inherited
            
            # Include all local fields except generated ones
            # We need to include the foreign key to the parent (business_ptr)
            fields = [f for f in opts.local_fields if not f.generated]
            
            with transaction.atomic(using=self.db, savepoint=False):
                 if objs_with_pk:
                     returned_columns = base_qs._batched_insert(
                         objs_with_pk,
                         fields,
                         batch_size=len(objs_with_pk),  # Use actual batch size
                     )
                     for obj_with_pk, results in zip(objs_with_pk, returned_columns):
                         for result, field in zip(results, opts.db_returning_fields):
                             if field != opts.pk:
                                 setattr(obj_with_pk, field.attname, result)
                     for obj_with_pk in objs_with_pk:
                         obj_with_pk._state.adding = False
                         obj_with_pk._state.db = self.db
                 
                 if objs_without_pk:
                     # For objects without PK, we still need to exclude primary key fields
                     fields = [f for f in fields if not isinstance(f, AutoField) and not f.primary_key]
                     returned_columns = base_qs._batched_insert(
                         objs_without_pk,
                         fields,
                         batch_size=len(objs_without_pk),  # Use actual batch size
                     )
                     for obj_without_pk, results in zip(objs_without_pk, returned_columns):
                         for result, field in zip(results, opts.db_returning_fields):
                             setattr(obj_without_pk, field.attname, result)
                         obj_without_pk._state.adding = False
                         obj_without_pk._state.db = self.db

        # Step 3: Update original objects with generated PKs and state
        pk_field_name = child_model._meta.pk.name
        for orig_obj, child_obj in zip(batch, all_child_objects):
            child_pk = getattr(child_obj, pk_field_name)
            setattr(orig_obj, pk_field_name, child_pk)
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

        # Handle auto_now_add and auto_now fields like Django does
        for field in parent_model._meta.local_fields:
            if hasattr(field, "auto_now_add") and field.auto_now_add:
                # Ensure auto_now_add fields are properly set
                if getattr(parent_obj, field.name) is None:
                    field.pre_save(parent_obj, add=True)
                    # Explicitly set the value to ensure it's not None
                    setattr(parent_obj, field.name, field.value_from_object(parent_obj))
            elif hasattr(field, "auto_now") and field.auto_now:
                field.pre_save(parent_obj, add=True)

        return parent_obj

    def _create_child_instance(self, source_obj, child_model, parent_instances):
        child_obj = child_model()
        # Only copy fields that exist in the child model's local fields
        for field in child_model._meta.local_fields:
            if isinstance(field, AutoField):
                continue
            if hasattr(source_obj, field.name):
                value = getattr(source_obj, field.name, None)
                if value is not None:
                    setattr(child_obj, field.name, value)
        
        # Set parent links for MTI
        for parent_model, parent_instance in parent_instances.items():
            parent_link = child_model._meta.get_ancestor_link(parent_model)
            if parent_link:
                # Set both the foreign key value (the ID) and the object reference
                # This follows Django's pattern in _set_pk_val
                setattr(child_obj, parent_link.attname, parent_instance.pk)  # Set the foreign key value
                setattr(child_obj, parent_link.name, parent_instance)        # Set the object reference

        # Handle auto_now_add and auto_now fields like Django does
        for field in child_model._meta.local_fields:
            if hasattr(field, "auto_now_add") and field.auto_now_add:
                # Ensure auto_now_add fields are properly set
                if getattr(child_obj, field.name) is None:
                    field.pre_save(child_obj, add=True)
                    # Explicitly set the value to ensure it's not None
                    setattr(child_obj, field.name, field.value_from_object(child_obj))
            elif hasattr(field, "auto_now") and field.auto_now:
                field.pre_save(child_obj, add=True)

        return child_obj
