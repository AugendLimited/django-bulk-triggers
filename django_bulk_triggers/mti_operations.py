"""
Multi-table inheritance (MTI) operations for TriggerQuerySetMixin.

This module contains MTI-specific methods that were extracted from queryset.py
for better maintainability and testing.
"""

import logging

from django.db import transaction
from django.db.models import AutoField, Case, Value, When

from django_bulk_triggers import engine
from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_UPDATE,
    VALIDATE_CREATE,
    VALIDATE_UPDATE,
)
from django_bulk_triggers.context import TriggerContext

logger = logging.getLogger(__name__)


class MTIOperationsMixin:
    """
    Mixin containing multi-table inheritance (MTI) specific methods.

    This mixin provides functionality for handling Django models that use
    multi-table inheritance patterns.
    """

    def _is_multi_table_inheritance(self) -> bool:
        """
        Determine whether this model uses multi-table inheritance (MTI).
        Returns True if the model has any concrete parent models other than itself.
        """
        model_cls = self.model
        for parent in model_cls._meta.all_parents:
            if parent._meta.concrete_model is not model_cls._meta.concrete_model:
                logger.debug(
                    "%s detected as MTI model (parent: %s)",
                    model_cls.__name__,
                    getattr(parent, "__name__", str(parent)),
                )
                return True

        logger.debug("%s is not an MTI model", model_cls.__name__)
        return False

    def _detect_modified_fields(self, new_instances, original_instances):
        """
        Detect fields that were modified during BEFORE_UPDATE triggers by comparing
        new instances with their original values.

        IMPORTANT: Skip fields that contain Django expression objects (Subquery, Case, etc.)
        as these should not be treated as in-memory modifications.
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

                # Get the new value to check if it's an expression object
                # For foreign key fields, use attname to avoid N+1 queries
                if field.is_relation and not field.many_to_many:
                    new_value = getattr(new_instance, field.attname, None)
                else:
                    new_value = getattr(new_instance, field.name)

                # Skip fields that contain expression objects - these are not in-memory modifications
                # but rather database-level expressions that should not be applied to instances
                from django.db.models import Subquery

                if isinstance(new_value, Subquery) or hasattr(
                    new_value, "resolve_expression"
                ):
                    logger.debug(
                        f"Skipping field {field.name} with expression value: {type(new_value).__name__}"
                    )
                    continue

                # Handle different field types appropriately
                if field.is_relation:
                    # Compare by raw id values to catch cases where only <fk>_id was set
                    original_pk = getattr(original, field.attname, None)
                    if new_value != original_pk:
                        modified_fields.add(field.name)
                else:
                    original_value = getattr(original, field.name)
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

    def _create_parent_instance(self, source_obj, parent_model, current_parent):
        parent_obj = parent_model()
        for field in parent_model._meta.local_fields:
            # Only copy if the field exists on the source and is not None
            if hasattr(source_obj, field.name):
                value = getattr(source_obj, field.name, None)
                if value is not None:
                    # Handle foreign key fields properly
                    if (
                        field.is_relation
                        and not field.many_to_many
                        and not field.one_to_many
                    ):
                        # For foreign key fields, extract the ID if we have a model instance
                        if hasattr(value, "pk") and value.pk is not None:
                            # Set the foreign key ID field (e.g., loan_account_id)
                            setattr(parent_obj, field.attname, value.pk)
                        else:
                            # If it's already an ID or None, use it as-is
                            setattr(parent_obj, field.attname, value)
                    else:
                        # For non-relation fields, copy the value directly
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

        # CRITICAL: Copy object state from source to determine if this is an update or insert
        # If source_obj has _state.adding = False (existing record in upsert), parent must too
        if hasattr(source_obj, '_state') and hasattr(parent_obj, '_state'):
            parent_obj._state.adding = source_obj._state.adding
            if hasattr(source_obj._state, 'db'):
                parent_obj._state.db = source_obj._state.db

        # Handle auto_now_add and auto_now fields like Django does
        for field in parent_model._meta.local_fields:
            if hasattr(field, "auto_now_add") and field.auto_now_add:
                # Ensure auto_now_add fields are properly set
                if getattr(parent_obj, field.name) is None:
                    field.pre_save(parent_obj, add=True)
                    # Explicitly set the value to ensure it's not None
                    setattr(
                        parent_obj, field.attname, field.value_from_object(parent_obj)
                    )
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
                    # Handle foreign key fields properly
                    if (
                        field.is_relation
                        and not field.many_to_many
                        and not field.one_to_many
                    ):
                        # For foreign key fields, extract the ID if we have a model instance
                        if hasattr(value, "pk") and value.pk is not None:
                            # Set the foreign key ID field (e.g., loan_account_id)
                            setattr(child_obj, field.attname, value.pk)
                        else:
                            # If it's already an ID or None, use it as-is
                            setattr(child_obj, field.attname, value)
                    else:
                        # For non-relation fields, copy the value directly
                        setattr(child_obj, field.name, value)

        # Set parent links for MTI
        for parent_model, parent_instance in parent_instances.items():
            parent_link = child_model._meta.get_ancestor_link(parent_model)
            if parent_link:
                # Set both the foreign key value (the ID) and the object reference
                # This follows Django's pattern in _set_pk_val
                setattr(
                    child_obj, parent_link.attname, parent_instance.pk
                )  # Set the foreign key value
                setattr(
                    child_obj, parent_link.name, parent_instance
                )  # Set the object reference

        # CRITICAL: Copy object state from source to determine if this is an update or insert
        # If source_obj has _state.adding = False (existing record in upsert), child must too
        if hasattr(source_obj, '_state') and hasattr(child_obj, '_state'):
            child_obj._state.adding = source_obj._state.adding
            if hasattr(source_obj._state, 'db'):
                child_obj._state.db = source_obj._state.db

        # Handle auto_now_add and auto_now fields like Django does
        for field in child_model._meta.local_fields:
            if hasattr(field, "auto_now_add") and field.auto_now_add:
                # Ensure auto_now_add fields are properly set
                if getattr(child_obj, field.name) is None:
                    field.pre_save(child_obj, add=True)
                    # Explicitly set the value to ensure it's not None
                    setattr(
                        child_obj, field.attname, field.value_from_object(child_obj)
                    )
            elif hasattr(field, "auto_now") and field.auto_now:
                field.pre_save(child_obj, add=True)

        return child_obj

    def _mti_bulk_create(self, objs, inheritance_chain=None, **kwargs):
        """
        Implements Django's suggested workaround #2 for MTI bulk_create:
        O(n) normal inserts into parent tables to get primary keys back,
        then single bulk insert into childmost table.
        Sets auto_now_add/auto_now fields for each model in the chain.
        """
        # Extract classified records if available (for upsert operations)
        existing_records = kwargs.pop("existing_records", [])
        new_records = kwargs.pop("new_records", [])

        # Remove custom trigger kwargs before passing to Django internals
        django_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ["bypass_triggers", "bypass_validation"]
        }
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
                batch_result = self._process_mti_bulk_create_batch(
                    batch,
                    inheritance_chain,
                    existing_records,
                    new_records,
                    **django_kwargs,
                )
                created_objects.extend(batch_result)
        return created_objects

    def _execute_bulk_insert(
        self, queryset, objects_with_pk, objects_without_pk, fields, opts
    ):
        """
        Execute bulk insert operations for child objects.
        Extracted for easier testing and mocking.
        """
        with transaction.atomic(using=self.db, savepoint=False):
            if objects_with_pk:
                returned_columns = queryset._batched_insert(
                    objects_with_pk,
                    fields,
                    batch_size=len(objects_with_pk),
                )
                # Handle both real Django objects and Mock objects for testing
                if returned_columns:
                    for obj_with_pk, results in zip(objects_with_pk, returned_columns):
                        # For Mock objects in tests, results might be a simple tuple
                        if hasattr(opts, "db_returning_fields") and hasattr(opts, "pk"):
                            for result, field in zip(results, opts.db_returning_fields):
                                if field != opts.pk:
                                    setattr(obj_with_pk, field.attname, result)
                        # For Mock objects, just set the state
                        obj_with_pk._state.adding = False
                        obj_with_pk._state.db = self.db
                else:
                    for obj_with_pk in objects_with_pk:
                        obj_with_pk._state.adding = False
                        obj_with_pk._state.db = self.db

            if objects_without_pk:
                # For objects without PK, we still need to exclude primary key fields
                filtered_fields = [
                    f
                    for f in fields
                    if not isinstance(f, AutoField) and not f.primary_key
                ]
                returned_columns = queryset._batched_insert(
                    objects_without_pk,
                    filtered_fields,
                    batch_size=len(objects_without_pk),
                )
                # Handle both real Django objects and Mock objects for testing
                if returned_columns:
                    for obj_without_pk, results in zip(
                        objects_without_pk, returned_columns
                    ):
                        # For Mock objects in tests, results might be a simple tuple
                        if hasattr(opts, "db_returning_fields"):
                            for result, field in zip(results, opts.db_returning_fields):
                                setattr(obj_without_pk, field.attname, result)
                        # For Mock objects, just set the state
                        obj_without_pk._state.adding = False
                        obj_without_pk._state.db = self.db
                else:
                    for obj_without_pk in objects_without_pk:
                        obj_without_pk._state.adding = False
                        obj_without_pk._state.db = self.db

    def _can_use_bulk_parent_insert(self):
        """
        Check if the database supports bulk insert with RETURNING (getting PKs back).
        This is available on PostgreSQL, Oracle 12+, SQLite 3.35+, and recent MySQL/MariaDB.
        """
        from django.db import connection
        
        # Use Django's feature detection
        features = connection.features
        return getattr(features, 'can_return_rows_from_bulk_insert', False)
    
    def _bulk_create_parents(
        self,
        new_objects,
        inheritance_chain,
        bypass_triggers=False,
        bypass_validation=False,
        update_conflicts=False,
        unique_fields=None,
        update_fields=None,
    ):
        """
        OPTIMIZED: Bulk insert parent objects using Django's bulk_create with RETURNING.
        This reduces N inserts to 1 bulk insert per parent level.
        
        Returns: parent_objects_map dict mapping object id() to parent instances
        """
        parent_objects_map = {}
        
        # Process each level of the inheritance chain (excluding child)
        for level_idx, model_class in enumerate(inheritance_chain[:-1]):
            # Step 1: Create parent instances for all objects at this level
            parent_objs_for_level = []
            obj_to_parent_map = {}  # Map original obj to its parent instance
            
            for obj in new_objects:
                # Get the current parent for this object (from previous level)
                current_parent = None
                if level_idx > 0:
                    prev_parents = parent_objects_map.get(id(obj), {})
                    current_parent = prev_parents.get(inheritance_chain[level_idx - 1])
                
                parent_obj = self._create_parent_instance(obj, model_class, current_parent)
                parent_objs_for_level.append(parent_obj)
                obj_to_parent_map[id(parent_obj)] = obj
            
            # Step 2: Fire BEFORE triggers in bulk
            if not bypass_triggers:
                ctx = TriggerContext(model_class)
                if not bypass_validation:
                    engine.run(model_class, VALIDATE_CREATE, parent_objs_for_level, ctx=ctx)
                engine.run(model_class, BEFORE_CREATE, parent_objs_for_level, ctx=ctx)
            
            # Step 3: BULK INSERT/UPSERT with RETURNING - this is the key optimization!
            # Build kwargs for bulk_create, optionally enabling upsert when the conflict
            # target matches a unique constraint on the current parent model.
            bulk_kwargs = {
                "batch_size": len(parent_objs_for_level),
            }

            if update_conflicts and unique_fields:
                # Normalize unique_fields to this model's field names (map *_id -> field name)
                model_fields_by_name = {f.name: f for f in model_class._meta.local_fields}
                normalized_unique = []
                for uf in unique_fields or []:
                    if uf in model_fields_by_name:
                        normalized_unique.append(uf)
                    elif uf.endswith("_id") and uf[:-3] in model_fields_by_name:
                        # Only map when the base field exists on this model
                        normalized_unique.append(uf[:-3])
                # Ensure uniqueness fields are unique and ordered deterministically
                normalized_unique = list(dict.fromkeys(normalized_unique))

                # Validate that normalized_unique exactly matches a unique constraint on this model
                has_matching_constraint = False
                if normalized_unique:
                    # Check UniqueConstraint entries
                    try:
                        from django.db.models import UniqueConstraint
                        constraint_field_sets = [
                            tuple(c.fields) for c in model_class._meta.constraints if isinstance(c, UniqueConstraint)
                        ]
                    except Exception:
                        constraint_field_sets = []

                    # Also consider unique_together if defined
                    ut = getattr(model_class._meta, "unique_together", ()) or ()
                    # Normalize unique_together into list of tuples
                    if isinstance(ut, tuple) and ut and not isinstance(ut[0], (list, tuple)):
                        ut = (ut,)  # single grouping
                    ut_field_sets = [tuple(group) for group in ut]

                    # Compare as sets (order-insensitive) but require exact field set match
                    provided_set = set(normalized_unique)
                    for group in constraint_field_sets + ut_field_sets:
                        if provided_set == set(group):
                            has_matching_constraint = True
                            # Keep the order as declared in the constraint if possible
                            # to maximize likelihood of matching a composite index
                            normalized_unique = list(group)
                            break

                if has_matching_constraint:
                    # Filter update_fields to only those present on this parent model
                    filtered_updates = []
                    if update_fields:
                        filtered_updates = [
                            uf for uf in update_fields if uf in model_fields_by_name
                        ]
                    
                    # CRITICAL: Only enable update_conflicts if we have fields to update
                    # Django requires update_fields to be non-empty when update_conflicts=True
                    if filtered_updates:
                        bulk_kwargs["update_conflicts"] = True
                        bulk_kwargs["unique_fields"] = normalized_unique
                        bulk_kwargs["update_fields"] = filtered_updates
                    else:
                        # No fields to update on this parent level - skip upsert
                        # This happens when all update_fields belong to child models only
                        logger.debug(
                            f"Skipping upsert for {model_class.__name__} - "
                            f"no update_fields present on this parent model"
                        )

            created_parents = model_class._base_manager.using(self.db).bulk_create(
                parent_objs_for_level,
                **bulk_kwargs,
            )
            
            # Step 4: Copy all fields back from created objects (Django sets PKs automatically)
            for created_parent, parent_obj in zip(created_parents, parent_objs_for_level):
                # Copy all fields including auto-generated ones
                for field in model_class._meta.local_fields:
                    created_value = getattr(created_parent, field.name, None)
                    if created_value is not None:
                        setattr(parent_obj, field.name, created_value)
                
                parent_obj._state.adding = False
                parent_obj._state.db = self.db
            
            # Step 5: Fire AFTER triggers in bulk
            if not bypass_triggers:
                engine.run(model_class, AFTER_CREATE, parent_objs_for_level, ctx=ctx)
            
            # Step 6: Store parent instances in the map
            for parent_obj in parent_objs_for_level:
                original_obj = obj_to_parent_map[id(parent_obj)]
                if id(original_obj) not in parent_objects_map:
                    parent_objects_map[id(original_obj)] = {}
                parent_objects_map[id(original_obj)][model_class] = parent_obj
        
        logger.debug(f"Bulk created parents for {len(new_objects)} objects across {len(inheritance_chain) - 1} levels")
        return parent_objects_map
    
    def _loop_create_parents(
        self,
        new_objects,
        inheritance_chain,
        bypass_triggers=False,
        bypass_validation=False
    ):
        """
        FALLBACK: Create parent objects one-by-one in a loop.
        Used when database doesn't support RETURNING or bulk insert fails.
        
        Returns: parent_objects_map dict mapping object id() to parent instances
        """
        parent_objects_map = {}
        
        for obj in new_objects:
            parent_instances = {}
            current_parent = None
            
            for model_class in inheritance_chain[:-1]:
                parent_obj = self._create_parent_instance(obj, model_class, current_parent)
                
                # Fire parent triggers if not bypassed
                if not bypass_triggers:
                    ctx = TriggerContext(model_class)
                    if not bypass_validation:
                        engine.run(model_class, VALIDATE_CREATE, [parent_obj], ctx=ctx)
                    engine.run(model_class, BEFORE_CREATE, [parent_obj], ctx=ctx)
                
                # Use Django's base manager to create the object and get PKs back
                field_values = {
                    field.name: getattr(parent_obj, field.name)
                    for field in model_class._meta.local_fields
                    if hasattr(parent_obj, field.name)
                    and getattr(parent_obj, field.name) is not None
                }
                created_obj = model_class._base_manager.using(self.db).create(**field_values)
                
                # Copy ALL fields back from created_obj to parent_obj
                for field in model_class._meta.local_fields:
                    created_value = getattr(created_obj, field.name, None)
                    if created_value is not None:
                        setattr(parent_obj, field.name, created_value)
                
                parent_obj._state.adding = False
                parent_obj._state.db = self.db
                
                # Fire AFTER_CREATE triggers for parent
                if not bypass_triggers:
                    engine.run(model_class, AFTER_CREATE, [parent_obj], ctx=ctx)
                
                parent_instances[model_class] = parent_obj
                current_parent = parent_obj
            
            parent_objects_map[id(obj)] = parent_instances
        
        logger.debug(f"Loop created parents for {len(new_objects)} objects")
        return parent_objects_map
    
    def _process_mti_bulk_create_batch(
        self,
        batch,
        inheritance_chain,
        existing_records=None,
        new_records=None,
        **kwargs,
    ):
        """
        Process a single batch of objects through the inheritance chain.
        
        OPTIMIZED APPROACH (bulk-first with fallback):
        1. Try BULK INSERT for parent tables (works on PostgreSQL, Oracle, newer DBs)
        2. If successful, all parents inserted in O(k) queries where k = inheritance depth
        3. Fall back to O(n) individual inserts only if bulk fails or unsupported
        
        This gives us MASSIVE performance gains on modern databases while maintaining compatibility.
        """
        bypass_triggers = kwargs.get("bypass_triggers", False)
        bypass_validation = kwargs.get("bypass_validation", False)
        existing_records_list = existing_records if existing_records else []
        
        # Separate new and existing objects
        new_objects_in_batch = [obj for obj in batch if obj not in existing_records_list]
        existing_objects_in_batch = [obj for obj in batch if obj in existing_records_list]
        
        # Step 1: Create parent objects - TRY BULK FIRST, then fallback to loop
        if new_objects_in_batch and self._can_use_bulk_parent_insert():
            try:
                parent_objects_map = self._bulk_create_parents(
                    new_objects_in_batch,
                    inheritance_chain,
                    bypass_triggers,
                    bypass_validation,
                    update_conflicts=kwargs.get("update_conflicts", False),
                    unique_fields=kwargs.get("unique_fields"),
                    update_fields=kwargs.get("update_fields"),
                )
                logger.info(
                    f"✓ BULK optimization: Inserted {len(new_objects_in_batch)} parent objects "
                    f"in {len(inheritance_chain) - 1} queries (vs {len(new_objects_in_batch) * (len(inheritance_chain) - 1)} in loop)"
                )
            except Exception as e:
                # Fall back to loop if bulk fails
                logger.warning(f"Bulk parent insert failed, falling back to loop: {e}")
                parent_objects_map = self._loop_create_parents(
                    new_objects_in_batch,
                    inheritance_chain,
                    bypass_triggers,
                    bypass_validation
                )
        elif new_objects_in_batch:
            # Database doesn't support RETURNING, use loop approach
            logger.debug("Using loop approach for parent inserts (DB doesn't support RETURNING)")
            parent_objects_map = self._loop_create_parents(
                new_objects_in_batch,
                inheritance_chain,
                bypass_triggers,
                bypass_validation
            )
        else:
            parent_objects_map = {}
        
        # Step 2: Handle existing objects separately (they always need individual saves)
        for obj in existing_objects_in_batch:
            parent_instances = {}
            current_parent = None

            for model_class in inheritance_chain[:-1]:
                parent_obj = self._create_parent_instance(obj, model_class, current_parent)

                # For existing records, update the parent object
                if not bypass_triggers:
                    ctx = TriggerContext(model_class)
                    if not bypass_validation:
                        engine.run(model_class, VALIDATE_UPDATE, [parent_obj], ctx=ctx)
                    engine.run(model_class, BEFORE_UPDATE, [parent_obj], ctx=ctx)

                # Update the existing parent object
                parent_update_fields = kwargs.get("update_fields")
                if parent_update_fields:
                    # Only include fields that exist in the parent model
                    parent_model_fields = {
                        field.name for field in model_class._meta.local_fields
                    }
                    filtered_update_fields = [
                        field
                        for field in parent_update_fields
                        if field in parent_model_fields
                    ]
                    parent_obj.save(update_fields=filtered_update_fields)
                else:
                    parent_obj.save()

                # Fire AFTER_UPDATE triggers for parent
                if not bypass_triggers:
                    engine.run(model_class, AFTER_UPDATE, [parent_obj], ctx=ctx)

                parent_instances[model_class] = parent_obj
                current_parent = parent_obj
            parent_objects_map[id(obj)] = parent_instances

        # Step 2: Handle child objects - create new ones and update existing ones
        child_model = inheritance_chain[-1]
        all_child_objects = []
        existing_child_objects = []

        for obj in batch:
            is_existing_record = obj in existing_records_list

            if is_existing_record:
                # For existing records, update the child object
                child_obj = self._create_child_instance(
                    obj, child_model, parent_objects_map.get(id(obj), {})
                )
                existing_child_objects.append(child_obj)
            else:
                # For new records, create the child object
                child_obj = self._create_child_instance(
                    obj, child_model, parent_objects_map.get(id(obj), {})
                )
                all_child_objects.append(child_obj)

        # Step 2.5: Update existing child objects
        if existing_child_objects:
            for child_obj in existing_child_objects:
                # Filter update_fields to only include fields that exist in the child model
                child_update_fields = kwargs.get("update_fields")
                if child_update_fields:
                    # Only include fields that exist in the child model
                    child_model_fields = {
                        field.name for field in child_model._meta.local_fields
                    }
                    filtered_child_update_fields = [
                        field
                        for field in child_update_fields
                        if field in child_model_fields
                    ]
                    child_obj.save(update_fields=filtered_child_update_fields)
                else:
                    child_obj.save()

        # Step 2.6: Use Django's internal bulk_create infrastructure for new child objects
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

            # Extracted method for easier testing
            self._execute_bulk_insert(
                base_qs, objs_with_pk, objs_without_pk, fields, opts
            )

        # Step 3: Update original objects with generated PKs and state
        pk_field_name = child_model._meta.pk.name

        # CRITICAL: We need to map new objects to their child objects correctly
        # all_child_objects only contains NEW objects, not existing ones
        # So we must iterate through batch and only update new objects with their corresponding child object
        new_obj_index = 0
        for orig_obj in batch:
            is_existing_record = orig_obj in existing_records_list
            
            if is_existing_record:
                # Existing objects already have their PKs, just update state
                orig_obj._state.adding = False
                orig_obj._state.db = self.db
            else:
                # New objects need to get their PKs and auto-generated field values 
                # from the corresponding child object AND parent objects
                if new_obj_index < len(all_child_objects):
                    child_obj = all_child_objects[new_obj_index]
                    
                    # Copy PK back to original object
                    child_pk = getattr(child_obj, pk_field_name)
                    setattr(orig_obj, pk_field_name, child_pk)
                    
                    # Get the parent instances for this object
                    parent_instances = parent_objects_map.get(id(orig_obj), {})
                    
                    # Copy auto-generated field values from ALL models in the inheritance chain
                    # (parent models AND child model) back to the original object
                    for model_class in inheritance_chain:
                        # For parent models, get values from parent_instances
                        if model_class in parent_instances:
                            source_obj = parent_instances[model_class]
                        # For child model, get values from child_obj
                        elif model_class == child_model:
                            source_obj = child_obj
                        else:
                            continue
                        
                        # Copy auto-generated fields from this level of the hierarchy
                        for field in model_class._meta.local_fields:
                            # Skip the PK field as we already set it
                            if field.name == pk_field_name:
                                continue
                            
                            # Skip parent link fields (they're internal to Django's MTI)
                            if hasattr(field, 'remote_field') and field.remote_field:
                                parent_link = child_model._meta.get_ancestor_link(model_class)
                                if parent_link and field.name == parent_link.name:
                                    continue
                            
                            # Copy auto-generated field values back
                            if hasattr(field, 'auto_now_add') and field.auto_now_add:
                                setattr(orig_obj, field.name, getattr(source_obj, field.name))
                            elif hasattr(field, 'auto_now') and field.auto_now:
                                setattr(orig_obj, field.name, getattr(source_obj, field.name))
                            # Also copy any database-generated values (like db_returning_fields)
                            elif hasattr(field, 'db_returning') and field.db_returning:
                                source_value = getattr(source_obj, field.name, None)
                                if source_value is not None:
                                    setattr(orig_obj, field.name, source_value)
                    
                    orig_obj._state.adding = False
                    orig_obj._state.db = self.db
                    new_obj_index += 1
                else:
                    # This should never happen, but log if it does
                    logger.error(
                        f"Mismatch between new objects in batch and all_child_objects: "
                        f"new_obj_index={new_obj_index}, len(all_child_objects)={len(all_child_objects)}"
                    )

        return batch

    def _mti_bulk_update(
        self, objs, fields, field_groups=None, inheritance_chain=None, originals=None, trigger_context=None, **kwargs
    ):
        """
        Custom bulk update implementation for MTI models.
        Updates each table in the inheritance chain efficiently using Django's batch_size.
        """
        model_cls = self.model
        if inheritance_chain is None:
            inheritance_chain = self._get_inheritance_chain()

        # Remove custom trigger kwargs and unsupported parameters before passing to Django internals
        unsupported_params = [
            "unique_fields",
            "update_conflicts",
            "update_fields",
            "ignore_conflicts",
        ]
        django_kwargs = {}
        for k, v in kwargs.items():
            if k in unsupported_params:
                logger.warning(
                    f"Parameter '{k}' is not supported by bulk_update. "
                    f"This parameter is only available in bulk_create for UPSERT operations."
                )
            elif k not in ["bypass_triggers", "bypass_validation"]:
                django_kwargs[k] = v

        # Safety check to prevent infinite recursion
        if len(inheritance_chain) > 10:  # Arbitrary limit to prevent infinite loops
            raise ValueError(
                "Inheritance chain too deep - possible infinite recursion detected"
            )

        # Handle auto_now fields and custom fields by calling pre_save on objects
        # Check all models in the inheritance chain for auto_now and custom fields
        custom_update_fields = []
        for obj in objs:
            for model in inheritance_chain:
                for field in model._meta.local_fields:
                    if hasattr(field, "auto_now") and field.auto_now:
                        field.pre_save(obj, add=False)
                    # CRITICAL FIX: Only call pre_save() for fields that are explicitly being updated
                    # Don't call pre_save() on fields not in the update set (prevents UNIQUE constraint violations in upsert)
                    elif hasattr(field, "pre_save") and field.name in fields:
                        try:
                            new_value = field.pre_save(obj, add=False)
                            if new_value is not None:
                                # Handle ForeignKey fields properly
                                if getattr(field, "is_relation", False) and not getattr(
                                    field, "many_to_many", False
                                ):
                                    # For ForeignKey fields, check if we need to assign to the _id field
                                    if (
                                        hasattr(field, "attname")
                                        and field.attname != field.name
                                    ):
                                        # This is a ForeignKey field, assign to the _id field
                                        setattr(obj, field.attname, new_value)
                                        custom_update_fields.append(field.attname)
                                    else:
                                        # Direct assignment for non-ForeignKey relation fields
                                        setattr(obj, field.name, new_value)
                                        custom_update_fields.append(field.name)
                                else:
                                    # Non-relation field, assign directly
                                    setattr(obj, field.name, new_value)
                                    custom_update_fields.append(field.name)
                                logger.debug(
                                    f"Custom field {field.name} updated via pre_save() for MTI object {obj.pk}"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to call pre_save() on custom field {field.name} in MTI: {e}"
                            )

        # Add auto_now fields to the fields list so they get updated in the database
        auto_now_fields = set()
        for model in inheritance_chain:
            for field in model._meta.local_fields:
                if hasattr(field, "auto_now") and field.auto_now:
                    auto_now_fields.add(field.name)

        # Add custom fields that were updated to the fields list
        all_fields = list(fields) + list(auto_now_fields) + custom_update_fields

        # Group fields by model in the inheritance chain (if not provided)
        if field_groups is None:
            field_groups = {}
            for field_name in all_fields:
                field = model_cls._meta.get_field(field_name)
                # Find which model in the inheritance chain this field belongs to
                for model in inheritance_chain:
                    if field in model._meta.local_fields:
                        if model not in field_groups:
                            field_groups[model] = []
                        field_groups[model].append(field_name)
                        break

        # Process in batches
        batch_size = django_kwargs.get("batch_size") or len(objs)
        total_updated = 0

        with transaction.atomic(using=self.db, savepoint=False):
            for i in range(0, len(objs), batch_size):
                batch = objs[i : i + batch_size]
                batch_result = self._process_mti_bulk_update_batch(
                    batch, field_groups, inheritance_chain, **django_kwargs
                )
                total_updated += batch_result

        return total_updated

    def _process_mti_bulk_update_batch(
        self, batch, field_groups, inheritance_chain, **kwargs
    ):
        """
        Process a single batch of objects for MTI bulk update.
        Updates each table in the inheritance chain for the batch.
        """
        total_updated = 0

        # For MTI, we need to handle parent links correctly
        # The root model (first in chain) has its own PK
        # Child models use the parent link to reference the root PK
        root_model = inheritance_chain[0]

        # Get the primary keys from the objects
        # If objects have pk set but are not loaded from DB, use those PKs
        root_pks = []
        for obj in batch:
            # Check both pk and id attributes
            pk_value = getattr(obj, "pk", None)
            if pk_value is None:
                pk_value = getattr(obj, "id", None)

            if pk_value is not None:
                root_pks.append(pk_value)
            else:
                continue

        if not root_pks:
            return 0

        # Update each table in the inheritance chain
        for model, model_fields in field_groups.items():
            if not model_fields:
                continue

            if model == inheritance_chain[0]:
                # Root model - use primary keys directly
                pks = root_pks
                filter_field = "pk"
            else:
                # Child model - use parent link field
                parent_link = None
                for parent_model in inheritance_chain:
                    if parent_model in model._meta.parents:
                        parent_link = model._meta.parents[parent_model]
                        break

                if parent_link is None:
                    continue

                # For child models, the parent link values should be the same as root PKs
                pks = root_pks
                filter_field = parent_link.attname

            if pks:
                base_qs = model._base_manager.using(self.db)

                # Check if records exist
                existing_count = base_qs.filter(**{f"{filter_field}__in": pks}).count()

                if existing_count == 0:
                    continue

                # Build CASE statements for each field to perform a single bulk update
                case_statements = {}
                for field_name in model_fields:
                    field = model._meta.get_field(field_name)
                    
                    # Skip auto_now_add fields - they should only be set on creation, not update
                    if getattr(field, 'auto_now_add', False):
                        continue
                    
                    # Skip primary key fields
                    if field.primary_key:
                        continue
                    
                    # For ForeignKey fields, use the column name (_id) instead of the field name
                    # This ensures we store the ID value, not the object
                    if getattr(field, 'is_relation', False) and hasattr(field, 'attname'):
                        # Use the database column name (e.g., 'category_id' instead of 'category')
                        db_field_name = field.attname
                        target_field = field.target_field
                    else:
                        db_field_name = field_name
                        target_field = field
                    
                    when_statements = []

                    for pk, obj in zip(pks, batch):
                        # Check both pk and id attributes for the object
                        obj_pk = getattr(obj, "pk", None)
                        if obj_pk is None:
                            obj_pk = getattr(obj, "id", None)

                        if obj_pk is None:
                            continue
                        # Get the value using the db_field_name (for FK, this gets the ID)
                        value = getattr(obj, db_field_name)
                        when_statements.append(
                            When(
                                **{filter_field: pk},
                                then=Value(value, output_field=target_field),
                            )
                        )

                    if when_statements:  # Only add CASE statement if we have conditions
                        case_statements[db_field_name] = Case(
                            *when_statements, output_field=target_field
                        )

                # Execute a single bulk update for all objects in this model
                try:
                    updated_count = base_qs.filter(
                        **{f"{filter_field}__in": pks}
                    ).update(**case_statements)
                    total_updated += updated_count
                except Exception as e:
                    import traceback

                    traceback.print_exc()

        return total_updated
