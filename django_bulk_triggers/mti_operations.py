"""
Multi-table inheritance (MTI) operations for TriggerQuerySetMixin.

This module contains MTI-specific methods that were extracted from queryset.py
for better maintainability and testing.
"""

import logging
from typing import List, Dict, Any, Optional

from django.db import models, transaction
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

        # Handle auto_now_add and auto_now fields like Django does
        for field in parent_model._meta.local_fields:
            if hasattr(field, "auto_now_add") and field.auto_now_add:
                # Ensure auto_now_add fields are properly set
                if getattr(parent_obj, field.name) is None:
                    field.pre_save(parent_obj, add=True)
                    # Explicitly set the value to ensure it's not None
                    setattr(parent_obj, field.attname, field.value_from_object(parent_obj))
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

        # Handle auto_now_add and auto_now fields like Django does
        for field in child_model._meta.local_fields:
            if hasattr(field, "auto_now_add") and field.auto_now_add:
                # Ensure auto_now_add fields are properly set
                if getattr(child_obj, field.name) is None:
                    field.pre_save(child_obj, add=True)
                    # Explicitly set the value to ensure it's not None
                    setattr(child_obj, field.attname, field.value_from_object(child_obj))
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
        Implements Django's suggested workaround #2: O(n) normal inserts into parent
        tables to get primary keys back, then single bulk insert into childmost table.
        """
        # For MTI, we need to save parent objects first to get PKs
        # Then we can use Django's bulk_create for the child objects
        parent_objects_map = {}

        # Step 1: Do O(n) normal inserts into parent tables to get primary keys back
        # Get bypass_triggers from kwargs
        bypass_triggers = kwargs.get("bypass_triggers", False)
        bypass_validation = kwargs.get("bypass_validation", False)

        # Create a list for lookup (since model instances without PKs are not hashable)
        existing_records_list = existing_records if existing_records else []

        for obj in batch:
            parent_instances = {}
            current_parent = None
            is_existing_record = obj in existing_records_list

            for model_class in inheritance_chain[:-1]:
                parent_obj = self._create_parent_instance(
                    obj, model_class, current_parent
                )

                if is_existing_record:
                    # For existing records, we need to update the parent object instead of creating
                    # The parent_obj should already have the correct PK from the database lookup
                    # Fire parent triggers for updates
                    if not bypass_triggers:
                        ctx = TriggerContext(model_class)
                        if not bypass_validation:
                            engine.run(
                                model_class, VALIDATE_UPDATE, [parent_obj], ctx=ctx
                            )
                        engine.run(model_class, BEFORE_UPDATE, [parent_obj], ctx=ctx)

                    # Update the existing parent object
                    # Filter update_fields to only include fields that exist in the parent model
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
                else:
                    # For new records, create the parent object as before
                    # Fire parent triggers if not bypassed
                    if not bypass_triggers:
                        ctx = TriggerContext(model_class)
                        if not bypass_validation:
                            engine.run(
                                model_class, VALIDATE_CREATE, [parent_obj], ctx=ctx
                            )
                        engine.run(model_class, BEFORE_CREATE, [parent_obj], ctx=ctx)

                    # Use Django's base manager to create the object and get PKs back
                    # This bypasses triggers and the MTI exception
                    field_values = {
                        field.name: getattr(parent_obj, field.name)
                        for field in model_class._meta.local_fields
                        if hasattr(parent_obj, field.name)
                        and getattr(parent_obj, field.name) is not None
                    }
                    created_obj = model_class._base_manager.using(self.db).create(
                        **field_values
                    )

                    # Update the parent_obj with the created object's PK
                    parent_obj.pk = created_obj.pk
                    parent_obj._state.adding = False
                    parent_obj._state.db = self.db

                    # Fire AFTER_CREATE triggers for parent
                    if not bypass_triggers:
                        engine.run(model_class, AFTER_CREATE, [parent_obj], ctx=ctx)

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
                    fields = [
                        f
                        for f in fields
                        if not isinstance(f, AutoField) and not f.primary_key
                    ]
                    returned_columns = base_qs._batched_insert(
                        objs_without_pk,
                        fields,
                        batch_size=len(objs_without_pk),  # Use actual batch size
                    )
                    for obj_without_pk, results in zip(
                        objs_without_pk, returned_columns
                    ):
                        for result, field in zip(results, opts.db_returning_fields):
                            setattr(obj_without_pk, field.attname, result)
                        obj_without_pk._state.adding = False
                        obj_without_pk._state.db = self.db

        # Step 3: Update original objects with generated PKs and state
        pk_field_name = child_model._meta.pk.name

        # Handle new objects
        for orig_obj, child_obj in zip(batch, all_child_objects):
            child_pk = getattr(child_obj, pk_field_name)
            setattr(orig_obj, pk_field_name, child_pk)
            orig_obj._state.adding = False
            orig_obj._state.db = self.db

        # Handle existing objects (they already have PKs, just update state)
        for orig_obj in batch:
            is_existing_record = orig_obj in existing_records_list
            if is_existing_record:
                orig_obj._state.adding = False
                orig_obj._state.db = self.db

        return batch

    def _mti_bulk_update(
        self, objs, fields, field_groups=None, inheritance_chain=None, **kwargs
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
                print(f"WARNING: Parameter '{k}' is not supported by bulk_update")
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
                    # Check for custom fields that might need pre_save() on update (like CurrentUserField)
                    elif hasattr(field, "pre_save") and field.name not in fields:
                        try:
                            new_value = field.pre_save(obj, add=False)
                            if new_value is not None:
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
                    when_statements = []

                    for pk, obj in zip(pks, batch):
                        # Check both pk and id attributes for the object
                        obj_pk = getattr(obj, "pk", None)
                        if obj_pk is None:
                            obj_pk = getattr(obj, "id", None)

                        if obj_pk is None:
                            continue
                        value = getattr(obj, field_name)
                        when_statements.append(
                            When(
                                **{filter_field: pk},
                                then=Value(value, output_field=field),
                            )
                        )

                    case_statements[field_name] = Case(
                        *when_statements, output_field=field
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
