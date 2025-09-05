import logging

from django.db import models, transaction
from django.db.models import AutoField, Case, Field, Value, When

from django_bulk_hooks import engine

logger = logging.getLogger(__name__)
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
from django_bulk_hooks.context import (
    HookContext,
    get_bulk_update_value_map,
    set_bulk_update_value_map,
)


class HookQuerySetMixin:
    """
    A mixin that provides bulk hook functionality to any QuerySet.
    This can be dynamically injected into querysets from other managers.
    """

    @transaction.atomic
    def delete(self):
        objs = list(self)
        if not objs:
            return 0

        model_cls = self.model
        ctx = HookContext(model_cls)

        # Run validation hooks first
        engine.run(model_cls, VALIDATE_DELETE, objs, ctx=ctx)

        # Then run business logic hooks
        engine.run(model_cls, BEFORE_DELETE, objs, ctx=ctx)

        # Before deletion, ensure all related fields are properly cached
        # to avoid DoesNotExist errors in AFTER_DELETE hooks
        for obj in objs:
            if obj.pk is not None:
                # Cache all foreign key relationships by accessing them
                for field in model_cls._meta.fields:
                    if (
                        field.is_relation
                        and not field.many_to_many
                        and not field.one_to_many
                    ):
                        try:
                            # Access the related field to cache it before deletion
                            getattr(obj, field.name)
                        except Exception:
                            # If we can't access the field (e.g., already deleted, no permission, etc.)
                            # continue with other fields
                            pass

        # Use Django's standard delete() method
        result = super().delete()

        # Run AFTER_DELETE hooks
        engine.run(model_cls, AFTER_DELETE, objs, ctx=ctx)

        return result

    @transaction.atomic
    def update(self, **kwargs):
        logger.debug(f"Entering update method with {len(kwargs)} kwargs")
        instances = list(self)
        if not instances:
            return 0

        model_cls = self.model
        pks = [obj.pk for obj in instances]

        # Load originals for hook comparison and ensure they match the order of instances
        # Use the base manager to avoid recursion
        original_map = {
            obj.pk: obj for obj in model_cls._base_manager.filter(pk__in=pks)
        }
        originals = [original_map.get(obj.pk) for obj in instances]

        # Check if any of the update values are Subquery objects
        try:
            from django.db.models import Subquery

            logger.debug("Successfully imported Subquery from django.db.models")
        except ImportError as e:
            logger.error(f"Failed to import Subquery: {e}")
            raise

        logger.debug(f"Checking for Subquery objects in {len(kwargs)} kwargs")

        subquery_detected = []
        for key, value in kwargs.items():
            is_subquery = isinstance(value, Subquery)
            logger.debug(
                f"Key '{key}': type={type(value).__name__}, is_subquery={is_subquery}"
            )
            if is_subquery:
                subquery_detected.append(key)

        has_subquery = len(subquery_detected) > 0
        logger.debug(
            f"Subquery detection result: {has_subquery}, detected keys: {subquery_detected}"
        )

        # Debug logging for Subquery detection
        logger.debug(f"Update kwargs: {list(kwargs.keys())}")
        logger.debug(
            f"Update kwargs types: {[(k, type(v).__name__) for k, v in kwargs.items()]}"
        )

        if has_subquery:
            logger.debug(
                f"Detected Subquery in update: {[k for k, v in kwargs.items() if isinstance(v, Subquery)]}"
            )
        else:
            # Check if we missed any Subquery objects
            for k, v in kwargs.items():
                if hasattr(v, "query") and hasattr(v, "resolve_expression"):
                    logger.warning(
                        f"Potential Subquery-like object detected but not recognized: {k}={type(v).__name__}"
                    )
                    logger.warning(
                        f"Object attributes: query={hasattr(v, 'query')}, resolve_expression={hasattr(v, 'resolve_expression')}"
                    )
                    logger.warning(
                        f"Object dir: {[attr for attr in dir(v) if not attr.startswith('_')][:10]}"
                    )

        # Apply field updates to instances
        # If a per-object value map exists (from bulk_update), prefer it over kwargs
        # IMPORTANT: Do not assign Django expression objects (e.g., Subquery/Case/F)
        # to in-memory instances before running BEFORE_UPDATE hooks. Hooks must not
        # receive unresolved expression objects.
        per_object_values = get_bulk_update_value_map()

        # For Subquery updates, skip all in-memory field assignments to prevent
        # expression objects from reaching hooks
        if has_subquery:
            logger.debug(
                "Skipping in-memory field assignments due to Subquery detection"
            )
        else:
            for obj in instances:
                if per_object_values and obj.pk in per_object_values:
                    for field, value in per_object_values[obj.pk].items():
                        setattr(obj, field, value)
                else:
                    for field, value in kwargs.items():
                        # Skip assigning expression-like objects (they will be handled at DB level)
                        is_expression_like = hasattr(value, "resolve_expression")
                        if is_expression_like:
                            # Special-case Value() which can be unwrapped safely
                            if isinstance(value, Value):
                                try:
                                    setattr(obj, field, value.value)
                                except Exception:
                                    # If Value cannot be unwrapped for any reason, skip assignment
                                    continue
                            else:
                                # Do not assign unresolved expressions to in-memory objects
                                logger.debug(
                                    f"Skipping assignment of expression {type(value).__name__} to field {field}"
                                )
                                continue
                        else:
                            setattr(obj, field, value)

        # Salesforce-style trigger behavior: Always run hooks, rely on Django's stack overflow protection
        from django_bulk_hooks.context import get_bypass_hooks

        current_bypass_hooks = get_bypass_hooks()

        # Only skip hooks if explicitly bypassed (not for recursion prevention)
        if current_bypass_hooks:
            logger.debug("update: hooks explicitly bypassed")
            ctx = HookContext(model_cls, bypass_hooks=True)
        else:
            # Always run hooks - Django will handle stack overflow protection
            logger.debug("update: running hooks with Salesforce-style behavior")
            ctx = HookContext(model_cls, bypass_hooks=False)

            # Run validation hooks first
            engine.run(model_cls, VALIDATE_UPDATE, instances, originals, ctx=ctx)

            # For Subquery updates, skip BEFORE_UPDATE hooks here - they'll run after refresh
            if not has_subquery:
                # Then run BEFORE_UPDATE hooks for non-Subquery updates
                engine.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

            # Persist any additional field mutations made by BEFORE_UPDATE hooks.
            # Build CASE statements per modified field not already present in kwargs.
            # Note: For Subquery updates, this will be empty since hooks haven't run yet
            # For Subquery updates, hook modifications are handled later via bulk_update
            if not has_subquery:
                modified_fields = self._detect_modified_fields(instances, originals)
                extra_fields = [f for f in modified_fields if f not in kwargs]
            else:
                extra_fields = []  # Skip for Subquery updates

            if extra_fields:
                case_statements = {}
                for field_name in extra_fields:
                    try:
                        field_obj = model_cls._meta.get_field(field_name)
                    except Exception:
                        # Skip unknown fields
                        continue

                    when_statements = []
                    for obj in instances:
                        obj_pk = getattr(obj, "pk", None)
                        if obj_pk is None:
                            continue

                        # Determine value and output field
                        if getattr(field_obj, "is_relation", False):
                            # For FK fields, store the raw id and target field output type
                            value = getattr(obj, field_obj.attname, None)
                            output_field = field_obj.target_field
                            target_name = (
                                field_obj.attname
                            )  # use column name (e.g., fk_id)
                        else:
                            value = getattr(obj, field_name)
                            output_field = field_obj
                            target_name = field_name

                        # Special handling for Subquery and other expression values in CASE statements
                        if isinstance(value, Subquery):
                            logger.debug(
                                f"Creating When statement with Subquery for {field_name}"
                            )
                            # Ensure the Subquery has proper output_field
                            if (
                                not hasattr(value, "output_field")
                                or value.output_field is None
                            ):
                                value.output_field = output_field
                                logger.debug(
                                    f"Set output_field for Subquery in When statement to {output_field}"
                                )
                            when_statements.append(When(pk=obj_pk, then=value))
                        elif hasattr(value, "resolve_expression"):
                            # Handle other expression objects (Case, F, etc.)
                            logger.debug(
                                f"Creating When statement with expression for {field_name}: {type(value).__name__}"
                            )
                            when_statements.append(When(pk=obj_pk, then=value))
                        else:
                            when_statements.append(
                                When(
                                    pk=obj_pk,
                                    then=Value(value, output_field=output_field),
                                )
                            )

                    if when_statements:
                        case_statements[target_name] = Case(
                            *when_statements, output_field=output_field
                        )

                # Merge extra CASE updates into kwargs for DB update
                if case_statements:
                    logger.debug(
                        f"Adding case statements to kwargs: {list(case_statements.keys())}"
                    )
                    for field_name, case_stmt in case_statements.items():
                        logger.debug(
                            f"Case statement for {field_name}: {type(case_stmt).__name__}"
                        )
                        # Check if the case statement contains Subquery objects
                        if hasattr(case_stmt, "get_source_expressions"):
                            source_exprs = case_stmt.get_source_expressions()
                            for expr in source_exprs:
                                if isinstance(expr, Subquery):
                                    logger.debug(
                                        f"Case statement for {field_name} contains Subquery"
                                    )
                                elif hasattr(expr, "get_source_expressions"):
                                    # Check nested expressions (like Value objects)
                                    nested_exprs = expr.get_source_expressions()
                                    for nested_expr in nested_exprs:
                                        if isinstance(nested_expr, Subquery):
                                            logger.debug(
                                                f"Case statement for {field_name} contains nested Subquery"
                                            )

                    kwargs = {**kwargs, **case_statements}

        # Use Django's built-in update logic directly
        # Call the base QuerySet implementation to avoid recursion

        # Additional safety check: ensure Subquery objects are properly handled
        # This prevents the "cannot adapt type 'Subquery'" error
        safe_kwargs = {}
        logger.debug(f"Processing {len(kwargs)} kwargs for safety check")

        for key, value in kwargs.items():
            logger.debug(
                f"Processing key '{key}' with value type {type(value).__name__}"
            )

            if isinstance(value, Subquery):
                logger.debug(f"Found Subquery for field {key}")
                # Ensure Subquery has proper output_field
                if not hasattr(value, "output_field") or value.output_field is None:
                    logger.warning(
                        f"Subquery for field {key} missing output_field, attempting to infer"
                    )
                    # Try to infer from the model field
                    try:
                        field = model_cls._meta.get_field(key)
                        logger.debug(f"Inferred field type: {type(field).__name__}")
                        value = value.resolve_expression(None, None)
                        value.output_field = field
                        logger.debug(f"Set output_field to {field}")
                    except Exception as e:
                        logger.error(
                            f"Failed to infer output_field for Subquery on {key}: {e}"
                        )
                        raise
                else:
                    logger.debug(
                        f"Subquery for field {key} already has output_field: {value.output_field}"
                    )
                safe_kwargs[key] = value
            elif hasattr(value, "get_source_expressions") and hasattr(
                value, "resolve_expression"
            ):
                # Handle Case statements and other complex expressions
                logger.debug(
                    f"Found complex expression for field {key}: {type(value).__name__}"
                )

                # Check if this expression contains any Subquery objects
                source_expressions = value.get_source_expressions()
                has_nested_subquery = False

                for expr in source_expressions:
                    if isinstance(expr, Subquery):
                        has_nested_subquery = True
                        logger.debug(f"Found nested Subquery in {type(value).__name__}")
                        # Ensure the nested Subquery has proper output_field
                        if (
                            not hasattr(expr, "output_field")
                            or expr.output_field is None
                        ):
                            try:
                                field = model_cls._meta.get_field(key)
                                expr.output_field = field
                                logger.debug(
                                    f"Set output_field for nested Subquery to {field}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to set output_field for nested Subquery: {e}"
                                )
                                raise

                if has_nested_subquery:
                    logger.debug(
                        "Expression contains Subquery, ensuring proper output_field"
                    )
                    # Try to resolve the expression to ensure it's properly formatted
                    try:
                        resolved_value = value.resolve_expression(None, None)
                        safe_kwargs[key] = resolved_value
                        logger.debug(f"Successfully resolved expression for {key}")
                    except Exception as e:
                        logger.error(f"Failed to resolve expression for {key}: {e}")
                        raise
                else:
                    safe_kwargs[key] = value
            else:
                logger.debug(
                    f"Non-Subquery value for field {key}: {type(value).__name__}"
                )
                safe_kwargs[key] = value

        logger.debug(f"Safe kwargs keys: {list(safe_kwargs.keys())}")
        logger.debug(
            f"Safe kwargs types: {[(k, type(v).__name__) for k, v in safe_kwargs.items()]}"
        )

        logger.debug(f"Calling super().update() with {len(safe_kwargs)} kwargs")
        try:
            update_count = super().update(**safe_kwargs)
            logger.debug(f"Super update successful, count: {update_count}")
        except Exception as e:
            logger.error(f"Super update failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Safe kwargs that caused failure: {safe_kwargs}")
            raise

        # If we used Subquery objects, refresh the instances to get computed values
        # and run BEFORE_UPDATE hooks so HasChanged conditions work correctly
        if has_subquery and instances and not current_bypass_hooks:
            logger.debug(
                "Refreshing instances with Subquery computed values before running hooks"
            )
            # Simple refresh of model fields without fetching related objects
            # Subquery updates only affect the model's own fields, not relationships
            refreshed_instances = {
                obj.pk: obj for obj in model_cls._base_manager.filter(pk__in=pks)
            }

            # Bulk update all instances in memory and save pre-hook state
            pre_hook_state = {}
            for instance in instances:
                if instance.pk in refreshed_instances:
                    refreshed_instance = refreshed_instances[instance.pk]
                    # Save current state before modifying for hook comparison
                    pre_hook_values = {}
                    for field in model_cls._meta.fields:
                        if field.name != "id":
                            pre_hook_values[field.name] = getattr(
                                refreshed_instance, field.name
                            )
                            setattr(
                                instance,
                                field.name,
                                getattr(refreshed_instance, field.name),
                            )
                    pre_hook_state[instance.pk] = pre_hook_values

            # Now run BEFORE_UPDATE hooks with refreshed instances so conditions work
            logger.debug("Running BEFORE_UPDATE hooks after Subquery refresh")
            engine.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

            # Check if hooks modified any fields and persist them with bulk_update
            hook_modified_fields = set()
            for instance in instances:
                if instance.pk in pre_hook_state:
                    pre_hook_values = pre_hook_state[instance.pk]
                    for field_name, pre_hook_value in pre_hook_values.items():
                        current_value = getattr(instance, field_name)
                        if current_value != pre_hook_value:
                            hook_modified_fields.add(field_name)

            hook_modified_fields = list(hook_modified_fields)
            if hook_modified_fields:
                logger.debug(
                    f"Running bulk_update for hook-modified fields: {hook_modified_fields}"
                )
                # Use bulk_update to persist hook modifications, bypassing hooks to avoid recursion
                model_cls.objects.bulk_update(
                    instances, hook_modified_fields, bypass_hooks=True
                )

        # Salesforce-style: Always run AFTER_UPDATE hooks unless explicitly bypassed
        if not current_bypass_hooks:
            logger.debug("update: running AFTER_UPDATE")
            engine.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)
        else:
            logger.debug("update: AFTER_UPDATE explicitly bypassed")

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
        model_cls, ctx, originals = self._setup_bulk_operation(
            objs,
            "bulk_create",
            require_pks=False,
            bypass_hooks=bypass_hooks,
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

        # Fire hooks before DB ops
        if not bypass_hooks:
            if update_conflicts and unique_fields:
                # For upsert operations, we need to determine which records will be created vs updated
                # Check which records already exist in the database based on unique fields
                existing_records = []
                new_records = []

                # We'll store the records for AFTER hooks after classification is complete

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

                if unique_values:
                    # Query the database to see which records already exist - SINGLE BULK QUERY
                    from django.db.models import Q

                    existing_filters = Q()
                    for unique_value, query_fields in unique_values:
                        filter_kwargs = {}
                        for field_name, value in unique_value.items():
                            # Use the correct database field name (may include _id suffix)
                            db_field_name = query_fields[field_name]
                            filter_kwargs[db_field_name] = value
                        existing_filters |= Q(**filter_kwargs)

                    logger.debug(
                        f"DEBUG: Existence check query filters: {existing_filters}"
                    )
                    logger.debug(
                        f"DEBUG: Unique fields for values_list: {unique_fields}"
                    )

                    # Get all existing records in one query and create a lookup set
                    # We need to use the original unique_fields for values_list to maintain consistency
                    existing_records_lookup = set()
                    existing_query = model_cls.objects.filter(existing_filters)
                    logger.debug(f"DEBUG: Existence check SQL: {existing_query.query}")

                    # Also get the raw database values for debugging
                    raw_existing = list(existing_query.values_list(*unique_fields))
                    logger.debug(f"DEBUG: Raw existing records from DB: {raw_existing}")

                    # Convert database values to match object types for comparison
                    # This handles cases where object values are strings but DB values are integers
                    existing_records_lookup = set()
                    for existing_record in raw_existing:
                        # Convert each value in the tuple to match the type from object extraction
                        converted_record = []
                        for i, field_name in enumerate(unique_fields):
                            db_value = existing_record[i]
                            # Convert all values to strings for consistent comparison
                            # This ensures all database values are strings like object values
                            converted_record.append(str(db_value))
                        converted_tuple = tuple(converted_record)
                        existing_records_lookup.add(converted_tuple)

                    logger.debug(
                        f"DEBUG: Found {len(raw_existing)} existing records from DB"
                    )
                    logger.debug(
                        f"DEBUG: Existing records lookup set: {existing_records_lookup}"
                    )

                    # Separate records based on whether they already exist
                    for obj in objs:
                        obj_unique_value = {}
                        for field_name in unique_fields:
                            # First check for _id field (more reliable for ForeignKeys)
                            if hasattr(obj, field_name + "_id"):
                                # Handle ForeignKey fields where _id suffix is used
                                obj_unique_value[field_name] = getattr(
                                    obj, field_name + "_id"
                                )
                            elif hasattr(obj, field_name):
                                obj_unique_value[field_name] = getattr(obj, field_name)

                        # Check if this record already exists using our bulk lookup
                        if obj_unique_value:
                            # Convert object values to tuple for comparison with existing records
                            # Apply the same type conversion as we did for database values
                            obj_unique_tuple = []
                            for field_name in unique_fields:
                                value = obj_unique_value[field_name]
                                # Check if this field uses _id suffix in the query
                                query_field_name = query_fields[field_name]
                                if query_field_name.endswith("_id"):
                                    # Convert to string to match how we convert DB values
                                    obj_unique_tuple.append(str(value))
                                else:
                                    # For non-_id fields, also convert to string for consistency
                                    # This ensures all values are strings like in the database lookup
                                    obj_unique_tuple.append(str(value))
                            obj_unique_tuple = tuple(obj_unique_tuple)

                            logger.debug(
                                f"DEBUG: Object unique tuple: {obj_unique_tuple}"
                            )
                            logger.debug(
                                f"DEBUG: Object unique value: {obj_unique_value}"
                            )
                            if obj_unique_tuple in existing_records_lookup:
                                existing_records.append(obj)
                                logger.debug(
                                    f"DEBUG: Found existing record for tuple: {obj_unique_tuple}"
                                )
                            else:
                                new_records.append(obj)
                                logger.debug(
                                    f"DEBUG: No existing record found for tuple: {obj_unique_tuple}"
                                )
                        else:
                            # If we can't determine uniqueness, treat as new
                            new_records.append(obj)
                else:
                    # If no unique fields, treat all as new
                    new_records = objs

                # Store the classified records for AFTER hooks to avoid duplicate queries
                ctx.upsert_existing_records = existing_records
                ctx.upsert_new_records = new_records

                # Handle auto_now fields intelligently for upsert operations
                # Only set auto_now fields on records that will actually be created
                self._handle_auto_now_fields(new_records, add=True)

                # For existing records, preserve their original auto_now values
                # We'll need to fetch them from the database to preserve the timestamps
                if existing_records:
                    # Get the unique field values for existing records
                    existing_unique_values = []
                    for obj in existing_records:
                        unique_value = {}
                        for field_name in unique_fields:
                            if hasattr(obj, field_name):
                                unique_value[field_name] = getattr(obj, field_name)
                        if unique_value:
                            existing_unique_values.append(unique_value)

                    if existing_unique_values:
                        # Build filter to fetch existing records
                        existing_filters = Q()
                        for unique_value in existing_unique_values:
                            filter_kwargs = {}
                            for field_name, value in unique_value.items():
                                filter_kwargs[field_name] = value
                            existing_filters |= Q(**filter_kwargs)

                        # Fetch existing records to preserve their auto_now values
                        existing_db_records = model_cls.objects.filter(existing_filters)
                        existing_db_map = {}
                        for db_record in existing_db_records:
                            key = tuple(
                                getattr(db_record, field) for field in unique_fields
                            )
                            existing_db_map[key] = db_record

                        # For existing records, populate all fields from database and set auto_now fields
                        for obj in existing_records:
                            key = tuple(getattr(obj, field) for field in unique_fields)
                            if key in existing_db_map:
                                db_record = existing_db_map[key]
                                # Copy all fields from the database record to ensure completeness
                                # but exclude auto_now_add fields which should never be updated
                                populated_fields = []
                                for field in model_cls._meta.local_fields:
                                    if field.name != "id":  # Don't overwrite the ID
                                        # Skip auto_now_add fields for existing records
                                        if (
                                            hasattr(field, "auto_now_add")
                                            and field.auto_now_add
                                        ):
                                            continue
                                        db_value = getattr(db_record, field.name)
                                        if (
                                            db_value is not None
                                        ):  # Only set non-None values
                                            setattr(obj, field.name, db_value)
                                            populated_fields.append(field.name)
                                print(
                                    f"DEBUG: Populated {len(populated_fields)} fields for existing record: {populated_fields}"
                                )
                                logger.debug(
                                    f"Populated {len(populated_fields)} fields for existing record: {populated_fields}"
                                )

                                # Now set auto_now fields using Django's pre_save method
                                for field in model_cls._meta.local_fields:
                                    if hasattr(field, "auto_now") and field.auto_now:
                                        field.pre_save(
                                            obj, add=False
                                        )  # add=False for updates
                                        print(
                                            f"DEBUG: Set {field.name} using pre_save for existing record {obj.pk}"
                                        )
                                        logger.debug(
                                            f"Set {field.name} using pre_save for existing record {obj.pk}"
                                        )

                # Remove duplicate code since we're now handling this above

                # CRITICAL: Handle auto_now fields intelligently for existing records
                # We need to exclude them from Django's ON CONFLICT DO UPDATE clause to prevent
                # Django's default behavior, but still ensure they get updated via pre_save
                if existing_records and update_fields:
                    logger.debug(
                        f"Processing {len(existing_records)} existing records with update_fields: {update_fields}"
                    )

                    # Identify auto_now fields
                    auto_now_fields = set()
                    for field in model_cls._meta.local_fields:
                        if hasattr(field, "auto_now") and field.auto_now:
                            auto_now_fields.add(field.name)

                    logger.debug(f"Found auto_now fields: {auto_now_fields}")

                    if auto_now_fields:
                        # Store original update_fields and auto_now fields for later restoration
                        ctx.original_update_fields = update_fields
                        ctx.auto_now_fields = auto_now_fields

                        # Filter out auto_now fields from update_fields for the database operation
                        # This prevents Django from including them in ON CONFLICT DO UPDATE
                        filtered_update_fields = [
                            f for f in update_fields if f not in auto_now_fields
                        ]

                        logger.debug(
                            f"Filtered update_fields: {filtered_update_fields}"
                        )
                        logger.debug(f"Excluded auto_now fields: {auto_now_fields}")

                        # Use filtered update_fields for Django's bulk_create operation
                        update_fields = filtered_update_fields

                        logger.debug(
                            f"Final update_fields for DB operation: {update_fields}"
                        )
                    else:
                        logger.debug("No auto_now fields found to handle")
                else:
                    logger.debug(
                        f"No existing records or update_fields to process. existing_records: {len(existing_records) if existing_records else 0}, update_fields: {update_fields}"
                    )

                # Run validation hooks on all records
                if not bypass_validation:
                    engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)

                # Run appropriate BEFORE hooks based on what will happen
                if new_records:
                    engine.run(model_cls, BEFORE_CREATE, new_records, ctx=ctx)
                if existing_records:
                    engine.run(model_cls, BEFORE_UPDATE, existing_records, ctx=ctx)
            else:
                # For regular create operations, run create hooks before DB ops
                # Handle auto_now fields normally for new records
                self._handle_auto_now_fields(objs, add=True)

                if not bypass_validation:
                    engine.run(model_cls, VALIDATE_CREATE, objs, ctx=ctx)
                engine.run(model_cls, BEFORE_CREATE, objs, ctx=ctx)
        else:
            logger.debug("bulk_create bypassed hooks")

        # For MTI models, we need to handle them specially
        if is_mti:
            # Use our MTI-specific logic
            # Filter out custom parameters that Django's bulk_create doesn't accept
            mti_kwargs = {
                "batch_size": batch_size,
                "ignore_conflicts": ignore_conflicts,
                "update_conflicts": update_conflicts,
                "update_fields": update_fields,
                "unique_fields": unique_fields,
            }

            # If we have classified records from upsert logic, pass them to MTI method
            if (
                update_conflicts
                and unique_fields
                and hasattr(ctx, "upsert_existing_records")
            ):
                mti_kwargs["existing_records"] = ctx.upsert_existing_records
                mti_kwargs["new_records"] = ctx.upsert_new_records

            # Remove custom hook kwargs if present in self.bulk_create signature
            result = self._mti_bulk_create(
                objs,
                **mti_kwargs,
            )
        else:
            # For single-table models, use Django's built-in bulk_create
            # but we need to call it on the base manager to avoid recursion
            # Filter out custom parameters that Django's bulk_create doesn't accept

            logger.debug(
                f"Calling Django bulk_create with update_fields: {update_fields}"
            )
            logger.debug(
                f"Calling Django bulk_create with update_conflicts: {update_conflicts}"
            )
            logger.debug(
                f"Calling Django bulk_create with unique_fields: {unique_fields}"
            )

            result = super().bulk_create(
                objs,
                batch_size=batch_size,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )

            logger.debug(f"Django bulk_create completed with result: {result}")

        # Fire AFTER hooks
        if not bypass_hooks:
            if update_conflicts and unique_fields:
                # Handle auto_now fields that were excluded from the main update
                if hasattr(ctx, "auto_now_fields") and existing_records:
                    logger.debug(
                        f"Performing separate update for auto_now fields: {ctx.auto_now_fields}"
                    )

                    # Perform a separate bulk_update for the auto_now fields that were set via pre_save
                    # This ensures they get saved to the database even though they were excluded from the main upsert
                    try:
                        # Use Django's base manager to bypass hooks and ensure the update happens
                        base_manager = model_cls._base_manager
                        auto_now_update_result = base_manager.bulk_update(
                            existing_records, list(ctx.auto_now_fields)
                        )
                        logger.debug(
                            f"Auto_now fields update completed with result: {auto_now_update_result}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to update auto_now fields: {e}")
                        # Don't raise the exception - the main operation succeeded

                # Restore original update_fields if we modified them
                if hasattr(ctx, "original_update_fields"):
                    logger.debug(
                        f"Restoring original update_fields: {ctx.original_update_fields}"
                    )
                    update_fields = ctx.original_update_fields
                    delattr(ctx, "original_update_fields")
                    if hasattr(ctx, "auto_now_fields"):
                        delattr(ctx, "auto_now_fields")
                    logger.debug(f"Restored update_fields: {update_fields}")

                # For upsert operations, reuse the existing/new records determination from BEFORE hooks
                # This avoids duplicate queries and improves performance
                if hasattr(ctx, "upsert_existing_records") and hasattr(
                    ctx, "upsert_new_records"
                ):
                    existing_records = ctx.upsert_existing_records
                    new_records = ctx.upsert_new_records
                    logger.debug(
                        f"Reusing upsert record classification from BEFORE hooks: {len(existing_records)} existing, {len(new_records)} new"
                    )
                else:
                    # Fallback: determine records that actually exist after bulk operation
                    logger.warning(
                        "Upsert record classification not found in context, performing fallback query"
                    )
                    existing_records = []
                    new_records = []

                    # Build a filter to check which records now exist
                    unique_values = []
                    for obj in objs:
                        unique_value = {}
                        for field_name in unique_fields:
                            if hasattr(obj, field_name):
                                unique_value[field_name] = getattr(obj, field_name)
                        if unique_value:
                            unique_values.append(unique_value)

                    if unique_values:
                        # Query the database to see which records exist after bulk operation
                        from django.db.models import Q

                        existing_filters = Q()
                        for unique_value in unique_values:
                            filter_kwargs = {}
                            for field_name, value in unique_value.items():
                                filter_kwargs[field_name] = value
                            existing_filters |= Q(**filter_kwargs)

                        # Get all existing records in one query and create a lookup set
                        existing_records_lookup = set()
                        for existing_record in model_cls.objects.filter(
                            existing_filters
                        ).values_list(*unique_fields):
                            # Convert tuple to a hashable key for lookup
                            existing_records_lookup.add(existing_record)

                        # Separate records based on whether they now exist
                        for obj in objs:
                            obj_unique_value = {}
                            for field_name in unique_fields:
                                if hasattr(obj, field_name):
                                    obj_unique_value[field_name] = getattr(
                                        obj, field_name
                                    )

                            # Check if this record exists using our bulk lookup
                            if obj_unique_value:
                                # Convert object values to tuple for comparison with existing records
                                obj_unique_tuple = tuple(
                                    obj_unique_value[field_name]
                                    for field_name in unique_fields
                                )
                                if obj_unique_tuple in existing_records_lookup:
                                    existing_records.append(obj)
                                else:
                                    new_records.append(obj)
                            else:
                                # If we can't determine uniqueness, treat as new
                                new_records.append(obj)
                    else:
                        # If no unique fields, treat all as new
                        new_records = objs

                # Run appropriate AFTER hooks based on what actually happened
                if new_records:
                    engine.run(model_cls, AFTER_CREATE, new_records, ctx=ctx)
                if existing_records:
                    engine.run(model_cls, AFTER_UPDATE, existing_records, ctx=ctx)
            else:
                # For regular create operations, run create hooks after DB ops
                engine.run(model_cls, AFTER_CREATE, objs, ctx=ctx)

        return result

    def _detect_changed_fields(self, objs):
        """
        Auto-detect which fields have changed by comparing objects with database values.
        Returns a set of field names that have changed across all objects.
        """
        if not objs:
            return set()

        model_cls = self.model
        changed_fields = set()

        # Get primary key field names
        pk_fields = [f.name for f in model_cls._meta.pk_fields]
        if not pk_fields:
            pk_fields = ["pk"]

        # Get all object PKs
        obj_pks = []
        for obj in objs:
            if hasattr(obj, "pk") and obj.pk is not None:
                obj_pks.append(obj.pk)
            else:
                # Skip objects without PKs
                continue

        if not obj_pks:
            return set()

        # Fetch current database values for all objects
        existing_objs = {
            obj.pk: obj for obj in model_cls.objects.filter(pk__in=obj_pks)
        }

        # Compare each object's current values with database values
        for obj in objs:
            if obj.pk not in existing_objs:
                continue

            db_obj = existing_objs[obj.pk]

            # Check all concrete fields for changes
            for field in model_cls._meta.concrete_fields:
                field_name = field.name

                # Skip primary key fields
                if field_name in pk_fields:
                    continue

                # Get current value from object
                current_value = getattr(obj, field_name, None)
                # Get database value
                db_value = getattr(db_obj, field_name, None)

                # Compare values (handle None cases)
                if current_value != db_value:
                    changed_fields.add(field_name)

        return changed_fields

    @transaction.atomic
    def bulk_update(self, objs, bypass_hooks=False, bypass_validation=False, **kwargs):
        if not objs:
            return []

        self._validate_objects(objs, require_pks=True, operation_name="bulk_update")

        changed_fields = self._detect_changed_fields(objs)
        is_mti = self._is_multi_table_inheritance()
        hook_context, originals = self._init_hook_context(
            bypass_hooks, objs, "bulk_update"
        )

        fields_set, auto_now_fields, custom_update_fields = self._prepare_update_fields(
            changed_fields
        )

        self._apply_auto_now_fields(objs, auto_now_fields)
        self._apply_custom_update_fields(objs, custom_update_fields, fields_set)

        if is_mti:
            return self._mti_bulk_update(objs, list(fields_set), **kwargs)
        else:
            return self._single_table_bulk_update(
                objs, fields_set, auto_now_fields, **kwargs
            )

    def _apply_custom_update_fields(self, objs, custom_update_fields, fields_set):
        """
        Call pre_save() for custom fields that require update handling
        (e.g., CurrentUserField) and update both the objects and the field set.

        Args:
            objs (list[Model]): The model instances being updated.
            custom_update_fields (list[Field]): Fields that define a pre_save() hook.
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
                        setattr(obj, field.name, new_value)

                        # Ensure this field is included in the update set
                        if (
                            field.name not in fields_set
                            and field.name not in pk_field_names
                        ):
                            fields_set.add(field.name)

                        logger.debug(
                            "Custom field %s updated via pre_save() for object %s",
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

    def _single_table_bulk_update(self, objs, fields_set, auto_now_fields, **kwargs):
        """
        Perform bulk_update for single-table models, handling Django semantics
        for kwargs and setting a value map for hook execution.

        Args:
            objs (list[Model]): The model instances being updated.
            fields_set (set[str]): The names of fields to update.
            auto_now_fields (list[str]): Names of auto_now fields included in update.
            **kwargs: Extra arguments (only Django-supported ones are passed through).

        Returns:
            list[Model]: The updated model instances.
        """
        # Strip out unsupported bulk_update kwargs
        django_kwargs = self._filter_django_kwargs(kwargs)

        # Build a value map: {pk -> {field: raw_value}} for later hook use
        value_map = self._build_value_map(objs, fields_set, auto_now_fields)

        if value_map:
            set_bulk_update_value_map(value_map)

        try:
            logger.debug(
                "Calling Django bulk_update for %d objects on fields %s",
                len(objs),
                list(fields_set),
            )
            return super().bulk_update(objs, list(fields_set), **django_kwargs)
        finally:
            # Always clear thread-local state
            set_bulk_update_value_map(None)

    def _filter_django_kwargs(self, kwargs):
        """
        Remove unsupported arguments before passing to Django's bulk_update.
        """
        unsupported = {
            "unique_fields",
            "update_conflicts",
            "update_fields",
            "ignore_conflicts",
        }
        passthrough = {}
        for k, v in kwargs.items():
            if k in unsupported:
                logger.warning(
                    "Parameter '%s' is not supported by bulk_update. "
                    "It is only available for bulk_create UPSERT operations.",
                    k,
                )
            elif k not in {"bypass_hooks", "bypass_validation"}:
                passthrough[k] = v
        return passthrough

    def _build_value_map(self, objs, fields_set, auto_now_fields):
        """
        Build a mapping of {pk -> {field_name: raw_value}} for hook processing.

        Expressions are not included; only concrete values assigned on the object.
        """
        value_map = {}
        for obj in objs:
            if obj.pk is None:
                continue  # skip unsaved objects
            field_values = {}
            for field_name in fields_set:
                value = getattr(obj, field_name)
                field_values[field_name] = value
                if field_name in auto_now_fields:
                    logger.debug("Object %s %s=%s", obj.pk, field_name, value)
            if field_values:
                value_map[obj.pk] = field_values

        logger.debug("Built value_map for %d objects", len(value_map))
        return value_map

    def _validate_objects(self, objs, require_pks=False, operation_name="bulk_update"):
        """
        Validate that all objects are instances of this queryset's model.

        Args:
            objs (list): Objects to validate
            require_pks (bool): Whether to validate that objects have primary keys
            operation_name (str): Name of the operation for error messages
        """
        model_cls = self.model

        # Type check
        invalid_types = {
            type(obj).__name__ for obj in objs if not isinstance(obj, model_cls)
        }
        if invalid_types:
            raise TypeError(
                f"{operation_name} expected instances of {model_cls.__name__}, "
                f"but got {invalid_types}"
            )

        # Primary key check (optional, for operations that require saved objects)
        if require_pks:
            missing_pks = [obj for obj in objs if obj.pk is None]
            if missing_pks:
                raise ValueError(
                    f"{operation_name} cannot operate on unsaved {model_cls.__name__} instances. "
                    f"{len(missing_pks)} object(s) have no primary key."
                )

        logger.debug(
            "Validated %d %s objects for %s",
            len(objs),
            model_cls.__name__,
            operation_name,
        )

    def _init_hook_context(
        self, bypass_hooks: bool, objs, operation_name="bulk_update"
    ):
        """
        Initialize the hook context for bulk operations.

        Args:
            bypass_hooks (bool): Whether to bypass hooks
            objs (list): List of objects being operated on
            operation_name (str): Name of the operation for logging

        Returns:
            (HookContext, list): The hook context and a placeholder list
            for 'originals', which can be populated later if needed for
            after_update hooks.
        """
        model_cls = self.model

        if bypass_hooks:
            logger.debug(
                "%s: hooks bypassed for %s", operation_name, model_cls.__name__
            )
            ctx = HookContext(model_cls, bypass_hooks=True)
        else:
            logger.debug("%s: hooks enabled for %s", operation_name, model_cls.__name__)
            ctx = HookContext(model_cls, bypass_hooks=False)

        # Keep `originals` aligned with objs to support later hook execution.
        originals = [None] * len(objs)

        return ctx, originals

    def _prepare_update_fields(self, changed_fields):
        """
        Determine the final set of fields to update, including auto_now
        fields and custom fields that require pre_save() on updates.

        Args:
            changed_fields (Iterable[str]): Fields detected as changed.

        Returns:
            tuple:
                fields_set (set): All fields that should be updated.
                auto_now_fields (list[str]): Fields that require auto_now behavior.
                custom_update_fields (list[Field]): Fields with pre_save hooks to call.
        """
        model_cls = self.model
        fields_set = set(changed_fields)
        pk_field_names = [f.name for f in model_cls._meta.pk_fields]

        auto_now_fields = []
        custom_update_fields = []

        for field in model_cls._meta.local_concrete_fields:
            # Handle auto_now fields
            if getattr(field, "auto_now", False):
                if field.name not in fields_set and field.name not in pk_field_names:
                    fields_set.add(field.name)
                    if field.name != field.attname:  # handle attname vs name
                        fields_set.add(field.attname)
                    auto_now_fields.append(field.name)
                    logger.debug("Added auto_now field %s to update set", field.name)

            # Skip auto_now_add (only applies at creation time)
            elif getattr(field, "auto_now_add", False):
                continue

            # Handle custom pre_save fields
            elif hasattr(field, "pre_save"):
                if field.name not in fields_set and field.name not in pk_field_names:
                    custom_update_fields.append(field)
                    logger.debug(
                        "Marked custom field %s for pre_save update", field.name
                    )

        logger.debug(
            "Prepared update fields: fields_set=%s, auto_now_fields=%s, custom_update_fields=%s",
            fields_set,
            auto_now_fields,
            [f.name for f in custom_update_fields],
        )

        return fields_set, auto_now_fields, custom_update_fields

    def _apply_auto_now_fields(self, objs, auto_now_fields, add=False):
        """
        Apply the current timestamp to all auto_now fields on each object.

        Args:
            objs (list[Model]): The model instances being processed.
            auto_now_fields (list[str]): Field names that require auto_now behavior.
            add (bool): Whether this is for creation (add=True) or update (add=False).
        """
        if not auto_now_fields:
            return

        from django.utils import timezone

        current_time = timezone.now()

        logger.debug(
            "Setting auto_now fields %s to %s for %d objects (add=%s)",
            auto_now_fields,
            current_time,
            len(objs),
            add,
        )

        for obj in objs:
            for field_name in auto_now_fields:
                setattr(obj, field_name, current_time)

    def _handle_auto_now_fields(self, objs, add=False):
        """
        Handle auto_now and auto_now_add fields for objects.

        Args:
            objs (list[Model]): The model instances being processed.
            add (bool): Whether this is for creation (add=True) or update (add=False).

        Returns:
            list[str]: Names of auto_now fields that were handled.
        """
        model_cls = self.model
        handled_fields = []

        for obj in objs:
            for field in model_cls._meta.local_fields:
                # Handle auto_now_add only during creation
                if add and hasattr(field, "auto_now_add") and field.auto_now_add:
                    if getattr(obj, field.name) is None:
                        field.pre_save(obj, add=True)
                    handled_fields.append(field.name)
                # Handle auto_now during creation or update
                elif hasattr(field, "auto_now") and field.auto_now:
                    field.pre_save(obj, add=add)
                    handled_fields.append(field.name)

        return list(set(handled_fields))  # Remove duplicates

    def _execute_hooks_with_operation(
        self,
        operation_func,
        validate_hook,
        before_hook,
        after_hook,
        objs,
        originals=None,
        ctx=None,
        bypass_hooks=False,
        bypass_validation=False,
    ):
        """
        Execute the complete hook lifecycle around a database operation.

        Args:
            operation_func (callable): The database operation to execute
            validate_hook: Hook constant for validation
            before_hook: Hook constant for before operation
            after_hook: Hook constant for after operation
            objs (list): Objects being operated on
            originals (list, optional): Original objects for comparison hooks
            ctx: Hook context
            bypass_hooks (bool): Whether to skip hooks
            bypass_validation (bool): Whether to skip validation hooks

        Returns:
            The result of the database operation
        """
        model_cls = self.model

        # Run validation hooks first (if not bypassed)
        if not bypass_validation and validate_hook:
            engine.run(model_cls, validate_hook, objs, ctx=ctx)

        # Run before hooks (if not bypassed)
        if not bypass_hooks and before_hook:
            engine.run(model_cls, before_hook, objs, originals, ctx=ctx)

        # Execute the database operation
        result = operation_func()

        # Run after hooks (if not bypassed)
        if not bypass_hooks and after_hook:
            engine.run(model_cls, after_hook, objs, originals, ctx=ctx)

        return result

    def _log_bulk_operation_start(self, operation_name, objs, **kwargs):
        """
        Log the start of a bulk operation with consistent formatting.

        Args:
            operation_name (str): Name of the operation (e.g., "bulk_create")
            objs (list): Objects being operated on
            **kwargs: Additional parameters to log
        """
        model_cls = self.model

        # Build parameter string for additional kwargs
        param_str = ""
        if kwargs:
            param_parts = []
            for key, value in kwargs.items():
                if isinstance(value, (list, tuple)):
                    param_parts.append(f"{key}={value}")
                else:
                    param_parts.append(f"{key}={value}")
            param_str = f", {', '.join(param_parts)}"

        # Use both print and logger for consistency with existing patterns
        print(
            f"DEBUG: {operation_name} called for {model_cls.__name__} with {len(objs)} objects{param_str}"
        )
        logger.debug(
            f"{operation_name} called for {model_cls.__name__} with {len(objs)} objects{param_str}"
        )

    def _execute_delete_hooks_with_operation(
        self,
        operation_func,
        objs,
        ctx=None,
        bypass_hooks=False,
        bypass_validation=False,
    ):
        """
        Execute hooks for delete operations with special field caching logic.

        Args:
            operation_func (callable): The delete operation to execute
            objs (list): Objects being deleted
            ctx: Hook context
            bypass_hooks (bool): Whether to skip hooks
            bypass_validation (bool): Whether to skip validation hooks

        Returns:
            The result of the delete operation
        """
        model_cls = self.model

        # Run validation hooks first (if not bypassed)
        if not bypass_validation:
            engine.run(model_cls, VALIDATE_DELETE, objs, ctx=ctx)

        # Run before hooks (if not bypassed)
        if not bypass_hooks:
            engine.run(model_cls, BEFORE_DELETE, objs, ctx=ctx)

            # Before deletion, ensure all related fields are properly cached
            # to avoid DoesNotExist errors in AFTER_DELETE hooks
            for obj in objs:
                if obj.pk is not None:
                    # Cache all foreign key relationships by accessing them
                    for field in model_cls._meta.fields:
                        if (
                            field.is_relation
                            and not field.many_to_many
                            and not field.one_to_many
                        ):
                            try:
                                # Access the related field to cache it before deletion
                                getattr(obj, field.name)
                            except Exception:
                                # If we can't access the field (e.g., already deleted, no permission, etc.)
                                # continue with other fields
                                pass

        # Execute the database operation
        result = operation_func()

        # Run after hooks (if not bypassed)
        if not bypass_hooks:
            engine.run(model_cls, AFTER_DELETE, objs, ctx=ctx)

        return result

    def _setup_bulk_operation(
        self,
        objs,
        operation_name,
        require_pks=False,
        bypass_hooks=False,
        bypass_validation=False,
        **log_kwargs,
    ):
        """
        Common setup logic for bulk operations.

        Args:
            objs (list): Objects to operate on
            operation_name (str): Name of the operation for logging and validation
            require_pks (bool): Whether objects must have primary keys
            bypass_hooks (bool): Whether to bypass hooks
            bypass_validation (bool): Whether to bypass validation
            **log_kwargs: Additional parameters to log

        Returns:
            tuple: (model_cls, ctx, originals)
        """
        # Log operation start
        self._log_bulk_operation_start(operation_name, objs, **log_kwargs)

        # Validate objects
        self._validate_objects(
            objs, require_pks=require_pks, operation_name=operation_name
        )

        # Initialize hook context
        ctx, originals = self._init_hook_context(bypass_hooks, objs, operation_name)

        return self.model, ctx, originals

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
        Detect fields that were modified during BEFORE_UPDATE hooks by comparing
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

        # Remove custom hook kwargs before passing to Django internals
        django_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ["bypass_hooks", "bypass_validation"]
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
        # Get bypass_hooks from kwargs
        bypass_hooks = kwargs.get("bypass_hooks", False)
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
                    # Fire parent hooks for updates
                    if not bypass_hooks:
                        ctx = HookContext(model_class)
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

                    # Fire AFTER_UPDATE hooks for parent
                    if not bypass_hooks:
                        engine.run(model_class, AFTER_UPDATE, [parent_obj], ctx=ctx)
                else:
                    # For new records, create the parent object as before
                    # Fire parent hooks if not bypassed
                    if not bypass_hooks:
                        ctx = HookContext(model_class)
                        if not bypass_validation:
                            engine.run(
                                model_class, VALIDATE_CREATE, [parent_obj], ctx=ctx
                            )
                        engine.run(model_class, BEFORE_CREATE, [parent_obj], ctx=ctx)

                    # Use Django's base manager to create the object and get PKs back
                    # This bypasses hooks and the MTI exception
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
                    setattr(child_obj, field.name, field.value_from_object(child_obj))
            elif hasattr(field, "auto_now") and field.auto_now:
                field.pre_save(child_obj, add=True)

        return child_obj

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

        # Remove custom hook kwargs and unsupported parameters before passing to Django internals
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
            elif k not in ["bypass_hooks", "bypass_validation"]:
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

    @transaction.atomic
    def bulk_delete(self, objs, bypass_hooks=False, bypass_validation=False, **kwargs):
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
            bypass_hooks=bypass_hooks,
            bypass_validation=bypass_validation,
        )

        # Execute the database operation with hooks
        def delete_operation():
            pks = [obj.pk for obj in objs if obj.pk is not None]
            if pks:
                # Use the base manager to avoid recursion
                return self.model._base_manager.filter(pk__in=pks).delete()[0]
            else:
                return 0

        result = self._execute_delete_hooks_with_operation(
            delete_operation,
            objs,
            ctx=ctx,
            bypass_hooks=bypass_hooks,
            bypass_validation=bypass_validation,
        )

        return result


class HookQuerySet(HookQuerySetMixin, models.QuerySet):
    """
    A QuerySet that provides bulk hook functionality.
    This is the traditional approach for backward compatibility.
    """

    pass
