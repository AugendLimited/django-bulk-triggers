"""
Bulk operations for TriggerQuerySetMixin.

This module contains bulk operation methods that were extracted from queryset.py
for better maintainability and testing.
"""

import logging

from django.db import transaction

from django_bulk_triggers import engine
from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_UPDATE,
    VALIDATE_CREATE,
    VALIDATE_UPDATE,
)

logger = logging.getLogger(__name__)


class BulkOperationsMixin:
    """
    Mixin containing bulk operation methods for TriggerQuerySetMixin.

    This mixin provides the core bulk operation functionality:
    - bulk_create
    - bulk_update
    - bulk_delete
    """

    @transaction.atomic
    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
        bypass_triggers=False,
        bypass_validation=False,
    ):
        """
        Insert each of the instances into the database. Behaves like Django's bulk_create,
        but supports multi-table inheritance (MTI) models and triggers. All arguments are supported and
        passed through to the correct logic. For MTI, only a subset of options may be supported.
        """
        model_cls, ctx, originals = self._setup_bulk_operation(
            objs,
            "bulk_create",
            require_pks=False,
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
            update_conflicts=update_conflicts,
            unique_fields=unique_fields,
            update_fields=update_fields,
        )

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

        if not objs:
            return objs

        self._validate_objects(objs, require_pks=False, operation_name="bulk_create")

        # Check for MTI - if we detect multi-table inheritance, we need special handling
        is_mti = self._is_multi_table_inheritance()

        # Fire triggers before DB ops
        if not bypass_triggers:
            if update_conflicts and unique_fields:
                # For upsert operations, we need to determine which records will be created vs updated
                # Check which records already exist in the database based on unique fields
                existing_records = []
                new_records = []

                # We'll store the records for AFTER triggers after classification is complete

                # Build a filter to check which records already exist
                unique_values = []
                for obj in objs:
                    unique_value = {}
                    query_fields = {}  # Track which database field to use for each unique field
                    for field_name in unique_fields:
                        # First check for _id field (more reliable for ForeignKeys)
                        if hasattr(obj, field_name + "_id"):
                            # Handle ForeignKey fields where _id suffix is used
                            unique_value[field_name] = getattr(obj, field_name + "_id")
                            query_fields[field_name] = (
                                field_name + "_id"
                            )  # Use _id field for query
                        elif hasattr(obj, field_name):
                            unique_value[field_name] = getattr(obj, field_name)
                            query_fields[field_name] = field_name
                    if unique_value:
                        unique_values.append((unique_value, query_fields))

                # Query the database to find existing records
                if unique_values:
                    # Build Q objects for the query
                    from django.db.models import Q

                    query = Q()
                    for unique_value, query_fields in unique_values:
                        subquery = Q()
                        for field_name, db_field in query_fields.items():
                            subquery &= Q(**{db_field: unique_value[field_name]})
                        query |= subquery

                    # Find existing records
                    existing_objs = list(model_cls.objects.filter(query))

                    # Classify objects as existing or new based on unique fields
                    for obj in objs:
                        is_existing = False
                        for existing_obj in existing_objs:
                            match = True
                            for field_name in unique_fields:
                                # Check both the field name and _id variant
                                obj_value = None
                                existing_value = None

                                # Try to get the value from the object
                                if hasattr(obj, field_name + "_id"):
                                    obj_value = getattr(obj, field_name + "_id")
                                elif hasattr(obj, field_name):
                                    obj_value = getattr(obj, field_name)

                                # Try to get the value from existing object
                                if hasattr(existing_obj, field_name + "_id"):
                                    existing_value = getattr(
                                        existing_obj, field_name + "_id"
                                    )
                                elif hasattr(existing_obj, field_name):
                                    existing_value = getattr(existing_obj, field_name)

                                if obj_value != existing_value:
                                    match = False
                                    break

                            if match:
                                # Copy field values from the existing object, BUT SKIP fields that are being updated
                                # This preserves the user's updates while populating other fields from the database
                                update_fields_set = set(update_fields) if update_fields else set()
                                
                                for field in model_cls._meta.fields:
                                    if not hasattr(existing_obj, field.name):
                                        continue
                                    
                                    # Skip fields that the user wants to update - keep user's values
                                    if field.name in update_fields_set:
                                        continue
                                    
                                    # Also skip the attname (e.g., created_by_id) for FK fields being updated
                                    if field.is_relation and not field.many_to_many:
                                        if field.name in update_fields_set or field.attname in update_fields_set:
                                            continue

                                    if field.is_relation and not field.many_to_many:
                                        # For foreign key fields, copy the ID to avoid stale object references
                                        setattr(
                                            obj,
                                            field.attname,
                                            getattr(existing_obj, field.attname),
                                        )
                                    else:
                                        # For non-relation fields, copy the value directly
                                        setattr(
                                            obj,
                                            field.name,
                                            getattr(existing_obj, field.name),
                                        )

                                # Copy the object state
                                obj._state.adding = False
                                obj._state.db = existing_obj._state.db

                                existing_records.append(obj)
                                is_existing = True
                                break

                        if not is_existing:
                            new_records.append(obj)
                else:
                    # If no unique fields specified, all records are new
                    new_records = objs

                # Fire BEFORE and VALIDATE triggers for existing records (treated as updates)
                if existing_records:
                    if not bypass_validation:
                        engine.run(
                            model_cls, VALIDATE_UPDATE, existing_records, ctx=ctx
                        )
                    engine.run(model_cls, BEFORE_UPDATE, existing_records, ctx=ctx)

                # Fire BEFORE and VALIDATE triggers for new records
                if new_records:
                    if not bypass_validation:
                        engine.run(model_cls, VALIDATE_CREATE, new_records, ctx=ctx)
                    engine.run(model_cls, BEFORE_CREATE, new_records, ctx=ctx)
            else:
                # Regular bulk create without upsert logic
                if not bypass_validation:
                    engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)
                engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)

        # Do the database operations
        if is_mti:
            # Multi-table inheritance requires special handling
            if update_conflicts and unique_fields:
                result = self._mti_bulk_create(
                    objs,
                    existing_records=existing_records,
                    new_records=new_records,
                    batch_size=batch_size,
                    ignore_conflicts=ignore_conflicts,
                    update_conflicts=update_conflicts,
                    update_fields=update_fields,
                    unique_fields=unique_fields,
                    bypass_triggers=bypass_triggers,
                    bypass_validation=bypass_validation,
                )
            else:
                result = self._mti_bulk_create(
                    objs,
                    batch_size=batch_size,
                    ignore_conflicts=ignore_conflicts,
                    update_conflicts=update_conflicts,
                    update_fields=update_fields,
                    unique_fields=unique_fields,
                    bypass_triggers=bypass_triggers,
                    bypass_validation=bypass_validation,
                )
        else:
            # Single table inheritance - use Django's bulk_create
            django_kwargs = {
                k: v
                for k, v in {
                    "batch_size": batch_size,
                    "ignore_conflicts": ignore_conflicts,
                    "update_conflicts": update_conflicts,
                    "update_fields": update_fields,
                    "unique_fields": unique_fields,
                }.items()
                if v is not None
            }

            logger.debug(
                "Calling Django bulk_create for %d objects with kwargs: %s",
                len(objs),
                django_kwargs,
            )
            result = super().bulk_create(objs, **django_kwargs)

        # Fire AFTER triggers
        if not bypass_triggers:
            if update_conflicts and unique_fields and existing_records and new_records:
                # For upsert operations, fire AFTER triggers for both created and updated records
                engine.run(model_cls, AFTER_UPDATE, existing_records, ctx=ctx)
                engine.run(model_cls, AFTER_CREATE, new_records, ctx=ctx)
            else:
                # Regular bulk create AFTER triggers
                engine.run(model_cls, AFTER_CREATE, result, ctx=ctx)

        return result

    @transaction.atomic
    def bulk_update(
        self, objs, bypass_triggers=False, bypass_validation=False, **kwargs
    ):
        if not objs:
            return []

        self._validate_objects(objs, require_pks=True, operation_name="bulk_update")

        # Set a context variable to indicate we're in bulk_update
        from django_bulk_triggers.context import set_bulk_update_active

        set_bulk_update_active(True)

        # Check global bypass triggers context (like QuerySet.update() does)
        from django_bulk_triggers.context import get_bypass_triggers

        current_bypass_triggers = get_bypass_triggers()

        # If global bypass is set or explicitly requested, bypass triggers
        if current_bypass_triggers or bypass_triggers:
            bypass_triggers = True

        # Fetch original instances for trigger comparison (like QuerySet.update() does)
        # This is needed for HasChanged conditions to work properly
        model_cls = self.model
        pks = [obj.pk for obj in objs if obj.pk is not None]
        original_map = {
            obj.pk: obj for obj in model_cls._base_manager.filter(pk__in=pks)
        }
        originals = [original_map.get(obj.pk) for obj in objs]

        changed_fields = self._detect_changed_fields(objs)
        is_mti = self._is_multi_table_inheritance()
        trigger_context, _ = self._init_trigger_context(
            bypass_triggers, objs, "bulk_update"
        )
        # Note: _init_trigger_context returns dummy originals, we use our fetched ones

        fields_set, auto_now_fields, custom_update_fields = self._prepare_update_fields(
            changed_fields
        )

        self._apply_auto_now_fields(objs, auto_now_fields)
        self._apply_custom_update_fields(objs, custom_update_fields, fields_set)

        # Execute BEFORE_UPDATE triggers if not bypassed
        if not bypass_triggers:
            from django_bulk_triggers import engine
            from django_bulk_triggers.constants import BEFORE_UPDATE, VALIDATE_UPDATE

            logger.debug(
                f"bulk_update: executing VALIDATE_UPDATE triggers for {model_cls.__name__}"
            )
            engine.run(model_cls, VALIDATE_UPDATE, objs, originals, ctx=trigger_context)

            logger.debug(
                f"bulk_update: executing BEFORE_UPDATE triggers for {model_cls.__name__}"
            )
            engine.run(model_cls, BEFORE_UPDATE, objs, originals, ctx=trigger_context)
        else:
            logger.debug(
                f"bulk_update: BEFORE_UPDATE triggers bypassed for {model_cls.__name__}"
            )

        # Execute bulk update with proper trigger handling
        if is_mti:
            # Remove 'fields' from kwargs to avoid conflict with positional argument
            mti_kwargs = {k: v for k, v in kwargs.items() if k != "fields"}
            result = self._mti_bulk_update(
                objs,
                list(fields_set),
                originals=originals,
                trigger_context=trigger_context,
                **mti_kwargs,
            )
        else:
            result = self._single_table_bulk_update(
                objs,
                fields_set,
                auto_now_fields,
                originals=originals,
                trigger_context=trigger_context,
                **kwargs,
            )

        # Execute AFTER_UPDATE triggers if not bypassed
        if not bypass_triggers:
            from django_bulk_triggers import engine
            from django_bulk_triggers.constants import AFTER_UPDATE

            logger.debug(
                f"bulk_update: executing AFTER_UPDATE triggers for {model_cls.__name__}"
            )
            engine.run(model_cls, AFTER_UPDATE, objs, originals, ctx=trigger_context)
        else:
            logger.debug(
                f"bulk_update: AFTER_UPDATE triggers bypassed for {model_cls.__name__}"
            )

        # Clear the bulk_update_active flag
        from django_bulk_triggers.context import set_bulk_update_active

        set_bulk_update_active(False)

        return result

    @transaction.atomic
    def bulk_delete(
        self, objs, bypass_triggers=False, bypass_validation=False, **kwargs
    ):
        """
        Bulk delete objects in the database.
        """
        model_cls = self.model

        if not objs:
            return 0

        model_cls, ctx, _ = self._setup_bulk_operation(
            objs,
            "bulk_delete",
            require_pks=True,
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )

        # Execute the database operation with triggers
        def delete_operation():
            pks = [obj.pk for obj in objs if obj.pk is not None]
            if pks:
                # Use the base manager to avoid recursion
                return self.model._base_manager.filter(pk__in=pks).delete()[0]
            else:
                return 0

        result = self._execute_delete_triggers_with_operation(
            delete_operation,
            objs,
            ctx=ctx,
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )

        return result

    def _apply_custom_update_fields(self, objs, custom_update_fields, fields_set):
        """
        Call pre_save() for custom fields that require update handling
        (e.g., CurrentUserField) and update both the objects and the field set.

        Args:
            objs (list[Model]): The model instances being updated.
            custom_update_fields (list[Field]): Fields that define a pre_save() trigger.
            fields_set (set[str]): The overall set of fields to update, mutated in place.
        """
        if not custom_update_fields:
            return

        model_cls = self.model
        pk_field_names = [f.name for f in model_cls._meta.pk_fields]

        logger.debug(
            "Applying pre_save() on custom update fields: %s",
            [f.name for f in custom_update_fields],
        )

        for obj in objs:
            for field in custom_update_fields:
                try:
                    # Call pre_save with add=False (since this is an update)
                    new_value = field.pre_save(obj, add=False)

                    # Only assign if pre_save returned something
                    if new_value is not None:
                        logger.debug(
                            "DEBUG: pre_save() returned value %s (type: %s) for field %s on object %s",
                            new_value,
                            type(new_value).__name__,
                            field.name,
                            obj.pk,
                        )

                        # Handle ForeignKey fields properly
                        if getattr(field, "is_relation", False) and not getattr(
                            field, "many_to_many", False
                        ):
                            logger.debug(
                                "DEBUG: Field %s is a relation field (is_relation=True, many_to_many=False)",
                                field.name,
                            )
                            # For ForeignKey fields, check if we need to assign to the _id field
                            if (
                                hasattr(field, "attname")
                                and field.attname != field.name
                            ):
                                logger.debug(
                                    "DEBUG: Assigning ForeignKey value %s to _id field %s (original field: %s)",
                                    new_value,
                                    field.attname,
                                    field.name,
                                )
                                # This is a ForeignKey field, assign to the _id field
                                setattr(obj, field.attname, new_value)
                                # Also ensure the _id field is in the update set
                                if (
                                    field.attname not in fields_set
                                    and field.attname not in pk_field_names
                                ):
                                    fields_set.add(field.attname)
                                    logger.debug(
                                        "DEBUG: Added _id field %s to fields_set",
                                        field.attname,
                                    )
                            else:
                                logger.debug(
                                    "DEBUG: Direct assignment for relation field %s (attname=%s)",
                                    field.name,
                                    getattr(field, "attname", "None"),
                                )
                                # Direct assignment for non-ForeignKey relation fields
                                setattr(obj, field.name, new_value)
                        else:
                            logger.debug(
                                "DEBUG: Non-relation field %s, assigning directly",
                                field.name,
                            )
                            # Non-relation field, assign directly
                            setattr(obj, field.name, new_value)

                        # Ensure this field is included in the update set
                        if (
                            field.name not in fields_set
                            and field.name not in pk_field_names
                        ):
                            fields_set.add(field.name)
                            logger.debug(
                                "DEBUG: Added field %s to fields_set",
                                field.name,
                            )

                        logger.debug(
                            "Custom field %s updated via pre_save() for object %s",
                            field.name,
                            obj.pk,
                        )
                    else:
                        logger.debug(
                            "DEBUG: pre_save() returned None for field %s on object %s",
                            field.name,
                            obj.pk,
                        )

                except Exception as e:
                    logger.warning(
                        "Failed to call pre_save() on custom field %s for object %s: %s",
                        field.name,
                        getattr(obj, "pk", None),
                        e,
                    )

    def _single_table_bulk_update(
        self,
        objs,
        fields_set,
        auto_now_fields,
        originals=None,
        trigger_context=None,
        **kwargs,
    ):
        """
        Perform bulk_update for single-table models, handling Django semantics
        for kwargs and setting a value map for trigger execution.

        Args:
            objs (list[Model]): The model instances being updated.
            fields_set (set[str]): The names of fields to update.
            auto_now_fields (list[str]): Names of auto_now fields included in update.
            originals (list[Model], optional): Original instances for trigger comparison.
            **kwargs: Extra arguments (only Django-supported ones are passed through).

        Returns:
            list[Model]: The updated model instances.
        """
        # Strip out unsupported bulk_update kwargs, excluding fields since we handle it separately
        django_kwargs = self._filter_django_kwargs(kwargs)
        # Remove 'fields' from django_kwargs since we pass it as a positional argument
        django_kwargs.pop("fields", None)

        # Build a value map: {pk -> {field: raw_value}} for later trigger use
        value_map = self._build_value_map(objs, fields_set, auto_now_fields)

        if value_map:
            # Import here to avoid circular imports
            from django_bulk_triggers.context import set_bulk_update_value_map

            set_bulk_update_value_map(value_map)

        try:
            logger.debug(
                "Calling Django bulk_update for %d objects on fields %s",
                len(objs),
                list(fields_set),
            )

            # Import the trigger engine and constants
            from django_bulk_triggers import engine
            from django_bulk_triggers.constants import AFTER_UPDATE, BEFORE_UPDATE
            from django_bulk_triggers.context import TriggerContext

            # Use provided trigger context or determine bypass state
            model_cls = self.model
            ctx = trigger_context
            if ctx is None:
                ctx = TriggerContext(model_cls, bypass_triggers=False)

            # NOTE: bulk_update does NOT run triggers directly - it relies on being called
            # from QuerySet.update() or other trigger-aware contexts that handle triggers
            result = super().bulk_update(objs, list(fields_set), **django_kwargs)

            return result
        finally:
            # Always clear thread-local state
            from django_bulk_triggers.context import set_bulk_update_value_map

            set_bulk_update_value_map(None)
