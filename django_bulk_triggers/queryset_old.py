import logging

from django.db import models, transaction

from django_bulk_triggers import engine
from django_bulk_triggers.bulk_operations import BulkOperationsMixin
from django_bulk_triggers.context import TriggerContext
from django_bulk_triggers.field_operations import FieldOperationsMixin
from django_bulk_triggers.mti_operations import MTIOperationsMixin
from django_bulk_triggers.trigger_operations import TriggerOperationsMixin
from django_bulk_triggers.validation_operations import ValidationOperationsMixin

logger = logging.getLogger(__name__)


class TriggerQuerySetMixin(
    BulkOperationsMixin,
    FieldOperationsMixin,
    MTIOperationsMixin,
    TriggerOperationsMixin,
    ValidationOperationsMixin,
):
    """
    A mixin that provides bulk trigger functionality to any QuerySet.
    This can be dynamically injected into querysets from other managers.
    """

    @transaction.atomic
    def delete(self):
        # Get all foreign key fields to optimize the initial query
        fk_fields = [
            field.name for field in self.model._meta.concrete_fields
            if field.is_relation and not field.many_to_many
        ]
        
        # Apply select_related to prevent N+1 queries when accessing foreign key relationships
        queryset = self
        if fk_fields:
            queryset = queryset.select_related(*fk_fields)
            logger.debug(f"Applied select_related for FK fields in delete: {fk_fields}")
        
        objs = list(queryset)
        if not objs:
            return 0
        ctx = TriggerContext(self.model)
        return self._execute_delete_triggers_with_operation(
            lambda: super(TriggerQuerySetMixin, self).delete(),
            objs,
            ctx=ctx,
        )

    @transaction.atomic
    def update(self, **kwargs):
        """
        Update QuerySet with trigger support.
        This method handles Subquery objects and complex expressions properly.
        """
        logger.debug(f"Entering update method with {len(kwargs)} kwargs")
        
        # Get all foreign key fields to optimize the initial query
        fk_fields = [
            field.name for field in self.model._meta.concrete_fields
            if field.is_relation and not field.many_to_many
        ]
        
        # Apply select_related to prevent N+1 queries when accessing foreign key relationships
        queryset = self
        if fk_fields:
            queryset = queryset.select_related(*fk_fields)
            logger.debug(f"Applied select_related for FK fields: {fk_fields}")
        
        instances = list(queryset)
        if not instances:
            return 0

        model_cls = self.model
        pks = [obj.pk for obj in instances]

        # Load originals for trigger comparison and ensure they match the order of instances
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

        has_subquery, subquery_detected = self._detect_subquery_fields(kwargs, Subquery)

        # Debug logging for Subquery detection
        logger.debug(f"Update kwargs: {list(kwargs.keys())}")
        logger.debug(
            f"Update kwargs types: {[(k, type(v).__name__) for k, v in kwargs.items()]}"
        )

        if has_subquery:
            logger.debug(
                f"Detected Subquery in update: {[k for k, v in kwargs.items() if isinstance(v, Subquery)]}"
            )
            logger.debug(
                f"Subquery update detected for {model_cls.__name__}"
            )
            logger.debug(f"Subquery kwargs = {list(kwargs.keys())}")
            for key, value in kwargs.items():
                logger.debug(
                    f"Subquery {key} = {type(value).__name__}"
                )
                if isinstance(value, Subquery):
                    logger.debug(
                        f"Subquery {key} detected (contains OuterRef - cannot log query string)"
                    )
                    try:
                        output_field = value.output_field
                        logger.debug(
                            f"Subquery {key} output_field: {output_field}"
                        )
                    except Exception as e:
                        logger.debug(
                            f"Subquery {key} output_field: Could not determine ({type(e).__name__}: {e})"
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
        # to in-memory instances before running BEFORE_UPDATE triggers. Triggers must not
        # receive unresolved expression objects.
        from django_bulk_triggers.context import get_bulk_update_value_map

        per_object_values = get_bulk_update_value_map()

        # For Subquery updates, skip in-memory assignments; otherwise apply safely
        self._apply_in_memory_assignments(
            instances, kwargs, per_object_values, has_subquery
        )

        # Salesforce-style trigger behavior: Always run triggers, rely on Django's stack overflow protection
        from django_bulk_triggers.context import (
            get_bulk_update_active,
            get_bypass_triggers,
        )

        current_bypass_triggers = get_bypass_triggers()
        bulk_update_active = get_bulk_update_active()

        # Skip triggers if we're in a bulk_update operation (to avoid double execution)
        if bulk_update_active:
            logger.debug("update: skipping triggers because we're in bulk_update")
            ctx = TriggerContext(model_cls, bypass_triggers=True)
        elif current_bypass_triggers:
            logger.debug("update: triggers explicitly bypassed")
            ctx = TriggerContext(model_cls, bypass_triggers=True)
        else:
            # Always run triggers - Django will handle stack overflow protection
            logger.debug("update: running triggers with Salesforce-style behavior")
            ctx = TriggerContext(model_cls, bypass_triggers=False)

            # Run validation triggers first
            from django_bulk_triggers.constants import BEFORE_UPDATE, VALIDATE_UPDATE

            engine.run(model_cls, VALIDATE_UPDATE, instances, originals, ctx=ctx)

            # For Subquery updates, skip BEFORE_UPDATE triggers here - they'll run after refresh
            if not has_subquery:
                # Then run BEFORE_UPDATE triggers for non-Subquery updates
                engine.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

            # Persist any additional field mutations made by BEFORE_UPDATE triggers.
            # Build CASE statements per modified field not already present in kwargs.
            # Note: For Subquery updates, this will be empty since triggers haven't run yet
            # For Subquery updates, trigger modifications are handled later via bulk_update
            if not has_subquery:
                modified_fields = self._detect_modified_fields(instances, originals)
                extra_fields = [f for f in modified_fields if f not in kwargs]
            else:
                extra_fields = []  # Skip for Subquery updates

            if extra_fields:
                case_statements = self._build_case_statements_for_extra_fields(
                    instances, extra_fields, model_cls
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
        safe_kwargs = self._make_safe_kwargs(kwargs, model_cls)

        logger.debug(f"Calling super().update() with {len(safe_kwargs)} kwargs")
        try:
            update_count = super().update(**safe_kwargs)
            logger.debug(f"Super update successful, count: {update_count}")
            logger.debug(
                f"Super update completed for {model_cls.__name__} with count {update_count}"
            )
            if has_subquery:
                logger.debug("Subquery update completed successfully")
                logger.debug(
                    "About to refresh instances to get computed values"
                )
        except Exception as e:
            logger.error(f"Super update failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Safe kwargs that caused failure: {safe_kwargs}")
            raise

        # If we used Subquery objects, refresh the instances to get computed values
        # and run BEFORE_UPDATE triggers so HasChanged conditions work correctly
        if has_subquery and instances and not current_bypass_triggers:
            logger.debug(
                "Refreshing instances with Subquery computed values before running triggers"
            )
            logger.debug(
                f"Refreshing {len(instances)} instances for {model_cls.__name__} after Subquery update"
            )
            logger.debug(f"Subquery update kwargs were: {list(kwargs.keys())}")
            for key, value in kwargs.items():
                if isinstance(value, Subquery):
                    logger.debug(
                        f"DEBUG: Subquery {key} output_field: {getattr(value, 'output_field', 'None')}"
                    )
            # Simple refresh of model fields with select_related optimization
            # Get all foreign key fields to optimize the query
            fk_fields = [
                field.name for field in model_cls._meta.concrete_fields
                if field.is_relation and not field.many_to_many
            ]
            
            logger.debug(f"FK fields for {model_cls.__name__}: {fk_fields}")
            
            # Build select_related query if there are foreign key fields
            queryset = model_cls._base_manager.filter(pk__in=pks)
            if fk_fields:
                queryset = queryset.select_related(*fk_fields)
                logger.debug(f"Applied select_related for fields: {fk_fields}")
            
            refreshed_instances = {obj.pk: obj for obj in queryset}

            # Bulk update all instances in memory and save pre-trigger state
            pre_trigger_state = {}
            for instance in instances:
                if instance.pk in refreshed_instances:
                    refreshed_instance = refreshed_instances[instance.pk]
                    logger.debug(
                        f"Refreshing instance pk={instance.pk}"
                    )
                    # Save current state before modifying for trigger comparison
                    pre_trigger_values = {}
                    for field in model_cls._meta.fields:
                        if field.name != "id":
                            # For foreign key fields, compare the ID values to avoid N+1 queries
                            if field.is_relation and not field.many_to_many:
                                try:
                                    old_value = getattr(instance, field.attname, None)
                                except Exception:
                                    old_value = None
                                
                                try:
                                    new_value = getattr(refreshed_instance, field.attname, None)
                                except Exception:
                                    new_value = None
                            else:
                                try:
                                    # For non-relation fields, use field.name
                                    old_value = getattr(instance, field.name, None)
                                except Exception as e:
                                    # Handle foreign key DoesNotExist errors gracefully
                                    if field.is_relation and "DoesNotExist" in str(
                                        type(e).__name__
                                    ):
                                        old_value = None
                                    else:
                                        raise

                                try:
                                    # For non-relation fields, use field.name
                                    new_value = getattr(
                                        refreshed_instance, field.name, None
                                    )
                                except Exception as e:
                                    # Handle foreign key DoesNotExist errors gracefully
                                    if field.is_relation and "DoesNotExist" in str(
                                        type(e).__name__
                                    ):
                                        new_value = None
                                    else:
                                        raise
                            if old_value != new_value:
                                logger.debug(
                                    f"Field {field.name} changed from {old_value} to {new_value}"
                                )
                                # Extra debug for aggregate fields
                                if field.name in [
                                    "disbursement",
                                    "disbursements",
                                    "balance",
                                    "amount",
                                ]:
                                    logger.debug(
                                        f"DEBUG: AGGREGATE FIELD {field.name} changed from {old_value} (type: {type(old_value).__name__}) to {new_value} (type: {type(new_value).__name__})"
                                    )
                            pre_trigger_values[field.name] = new_value
                            
                            # CRITICAL: For FK fields, copy the ID value to avoid N+1 queries
                            # For non-FK fields, copy the value directly
                            if field.is_relation and not field.many_to_many:
                                # For foreign key fields, copy the ID value (e.g., currency_id)
                                # This avoids triggering relationship access which would cause N+1 queries
                                try:
                                    refreshed_fk_id = getattr(refreshed_instance, field.attname, None)
                                    setattr(instance, field.attname, refreshed_fk_id)
                                    logger.debug(f"Copied FK ID for {field.name}: {field.attname}={refreshed_fk_id} for instance pk={instance.pk}")
                                except Exception as e:
                                    logger.warning(f"Could not copy FK ID for field {field.name}: {e}")
                                    continue
                            else:
                                # For non-relation fields, it's safe to access and set the value
                                try:
                                    refreshed_value = getattr(refreshed_instance, field.name)
                                except Exception as e:
                                    # Handle any errors gracefully
                                    logger.warning(f"Could not access field {field.name}: {e}")
                                    continue

                                setattr(
                                    instance,
                                    field.name,
                                    refreshed_value,
                                )
                    pre_trigger_state[instance.pk] = pre_trigger_values
                    logger.debug(
                        f"Instance pk={instance.pk} refreshed successfully"
                    )
                    # Log final state of key aggregate fields
                    for field_name in [
                        "disbursement",
                        "disbursements",
                        "balance",
                        "amount",
                    ]:
                        if hasattr(instance, field_name):
                            final_value = getattr(instance, field_name)
                            logger.debug(
                                f"DEBUG: Final {field_name} value after refresh: {final_value} (type: {type(final_value).__name__})"
                            )
                else:
                    logger.warning(
                        f"Could not find refreshed instance for pk={instance.pk}"
                    )

            # Now run BEFORE_UPDATE triggers with refreshed instances so conditions work
            logger.debug("Running BEFORE_UPDATE triggers after Subquery refresh")
            from django_bulk_triggers.constants import BEFORE_UPDATE

            engine.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

            # Check if triggers modified any fields and persist them with bulk_update
            trigger_modified_fields = set()
            for instance in instances:
                if instance.pk in pre_trigger_state:
                    pre_trigger_values = pre_trigger_state[instance.pk]
                    for field_name, pre_trigger_value in pre_trigger_values.items():
                        field = instance._meta.get_field(field_name)
                        # For foreign key fields, compare the ID values to avoid N+1 queries
                        if field.is_relation and not field.many_to_many:
                            try:
                                current_value = getattr(instance, field.attname)
                            except Exception:
                                current_value = None
                        else:
                            try:
                                current_value = getattr(instance, field_name)
                            except Exception as e:
                                # Handle foreign key DoesNotExist errors gracefully
                                if field.is_relation and "DoesNotExist" in str(
                                    type(e).__name__
                                ):
                                    current_value = None
                                else:
                                    raise

                        if current_value != pre_trigger_value:
                            trigger_modified_fields.add(field_name)

            trigger_modified_fields = list(trigger_modified_fields)
            if trigger_modified_fields:
                logger.debug(
                    f"Running bulk_update for trigger-modified fields: {trigger_modified_fields}"
                )
                # Use bulk_update to persist trigger modifications
                # Let Django handle recursion naturally - triggers will detect if they're already executing
                logger.debug(
                    f"About to call bulk_update with bypass_triggers=False for {model_cls.__name__}"
                )
                logger.debug(
                    f"trigger_modified_fields = {trigger_modified_fields}"
                )
                logger.debug(f"Instances count = {len(instances)}")
                for i, instance in enumerate(instances):
                    logger.debug(
                        f"instance {i} pk={getattr(instance, 'pk', 'No PK')}"
                    )

                # Retrieve batch_size from parent context
                from django_bulk_triggers.context import get_bulk_update_batch_size
                
                parent_batch_size = get_bulk_update_batch_size()
                
                # Build kwargs for recursive call
                update_kwargs = {'bypass_triggers': False}
                if parent_batch_size is not None:
                    update_kwargs['batch_size'] = parent_batch_size
                    logger.debug(f"Passing batch_size={parent_batch_size} to recursive bulk_update")

                result = model_cls.objects.bulk_update(
                    instances, trigger_modified_fields, **update_kwargs
                )
                logger.debug(f"Bulk_update result = {result}")

            # Run AFTER_UPDATE triggers for the Subquery update now that instances are refreshed
            # and any trigger modifications have been persisted
            logger.debug(
                "Running AFTER_UPDATE triggers after Subquery update and refresh"
            )
            logger.debug(
                "About to run AFTER_UPDATE for %s with %d instances",
                model_cls.__name__,
                len(instances),
            )
            logger.debug("Running AFTER_UPDATE triggers for %d instances", len(instances))

            from django_bulk_triggers.constants import AFTER_UPDATE

            # Save state before AFTER_UPDATE triggers so we can detect modifications
            pre_after_trigger_state = {}
            for instance in instances:
                if instance.pk is not None:
                    pre_after_trigger_values = {}
                    for field in model_cls._meta.fields:
                        if field.name != "id":
                            # For foreign key fields, use attname to avoid N+1 queries
                            if field.is_relation and not field.many_to_many:
                                pre_after_trigger_values[field.name] = getattr(
                                    instance, field.attname, None
                                )
                            else:
                                pre_after_trigger_values[field.name] = getattr(
                                    instance, field.name, None
                                )
                    pre_after_trigger_state[instance.pk] = pre_after_trigger_values

            engine.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)
            logger.debug(
                f"AFTER_UPDATE completed for {model_cls.__name__}"
            )

            # Check if AFTER_UPDATE triggers modified any fields and persist them with bulk_update
            after_trigger_modified_fields = set()
            for instance in instances:
                if instance.pk in pre_after_trigger_state:
                    pre_after_trigger_values = pre_after_trigger_state[instance.pk]
                    for (
                        field_name,
                        pre_after_trigger_value,
                    ) in pre_after_trigger_values.items():
                        field = instance._meta.get_field(field_name)
                        # For foreign key fields, compare the ID values to avoid N+1 queries
                        if field.is_relation and not field.many_to_many:
                            try:
                                current_value = getattr(instance, field.attname)
                            except Exception:
                                current_value = None
                        else:
                            try:
                                current_value = getattr(instance, field_name)
                            except Exception as e:
                                # Handle foreign key DoesNotExist errors gracefully
                                if field.is_relation and "DoesNotExist" in str(
                                    type(e).__name__
                                ):
                                    current_value = None
                                else:
                                    raise

                        if current_value != pre_after_trigger_value:
                            after_trigger_modified_fields.add(field_name)

            after_trigger_modified_fields = list(after_trigger_modified_fields)
            if after_trigger_modified_fields:
                logger.debug(
                    f"Running bulk_update for AFTER_UPDATE trigger-modified fields: {after_trigger_modified_fields}"
                )
                # Use bulk_update to persist AFTER_UPDATE trigger modifications
                # Allow triggers to run - our new depth-based recursion detection will prevent infinite loops
                logger.debug(
                    f"About to call bulk_update with triggers enabled for AFTER_UPDATE modifications on {model_cls.__name__}"
                )
                logger.debug(
                    f"after_trigger_modified_fields = {after_trigger_modified_fields}"
                )
                logger.debug(f"Instances count = {len(instances)}")
                for i, instance in enumerate(instances):
                    logger.debug(
                        f"instance {i} pk={getattr(instance, 'pk', 'No PK')}"
                    )

                # Salesforce-style: Allow nested triggers to run for field modifications
                # The depth-based recursion detection in engine.py will prevent infinite loops
                
                # Retrieve batch_size from parent context
                from django_bulk_triggers.context import get_bulk_update_batch_size
                
                parent_batch_size = get_bulk_update_batch_size()
                
                # Build kwargs for recursive call
                update_kwargs = {'bypass_triggers': False}
                if parent_batch_size is not None:
                    update_kwargs['batch_size'] = parent_batch_size
                    logger.debug(f"Passing batch_size={parent_batch_size} to recursive AFTER_UPDATE bulk_update")
                
                result = model_cls.objects.bulk_update(
                    instances, after_trigger_modified_fields, **update_kwargs
                )
                logger.debug(
                    f"AFTER_UPDATE bulk_update result = {result}"
                )

        # Salesforce-style: Always run AFTER_UPDATE triggers unless explicitly bypassed
        from django_bulk_triggers.constants import AFTER_UPDATE

        if not current_bypass_triggers:
            # For Subquery updates, AFTER_UPDATE triggers have already been run above
            if not has_subquery:
                logger.debug("update: running AFTER_UPDATE")
                logger.debug(
                    f"Running AFTER_UPDATE for {model_cls.__name__} with {len(instances)} instances"
                )
                engine.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)
            else:
                logger.debug("update: AFTER_UPDATE already run for Subquery update")
        else:
            logger.debug("update: AFTER_UPDATE explicitly bypassed")

        return update_count

    def _build_case_statements_for_extra_fields(
        self, instances, extra_fields, model_cls
    ):
        from django.db.models import Case, Subquery, Value, When

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
                    target_name = field_obj.attname  # use column name (e.g., fk_id)
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
                    if not hasattr(value, "output_field") or value.output_field is None:
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

        return case_statements

    def _make_safe_kwargs(self, kwargs, model_cls):
        from django.db.models import Subquery

        logger.debug(f"Processing {len(kwargs)} kwargs for safety check")
        safe_kwargs = {}

        for key, value in kwargs.items():
            logger.debug(
                f"Processing key '{key}' with value type {type(value).__name__}"
            )

            if isinstance(value, Subquery):
                logger.debug(f"Found Subquery for field {key}")
                # Ensure Subquery has proper output_field
                # Check if output_field exists and is not None
                has_output_field = False
                try:
                    has_output_field = hasattr(value, "output_field") and value.output_field is not None
                except Exception:
                    # output_field property may raise OutputFieldIsNoneError
                    has_output_field = False
                
                if not has_output_field:
                    logger.warning(
                        f"Subquery for field {key} missing output_field, attempting to infer"
                    )
                    # Try to infer from the model field
                    try:
                        field = model_cls._meta.get_field(key)
                        logger.debug(f"Inferred field type: {type(field).__name__}")
                        value.output_field = field
                        logger.debug(f"Set output_field to {field}")
                    except Exception as e:
                        logger.error(
                            f"Failed to infer output_field for Subquery on {key}: {e}"
                        )
                        raise
                else:
                    try:
                        output_field_value = value.output_field
                        logger.debug(
                            f"Subquery for field {key} already has output_field: {output_field_value}"
                        )
                    except Exception:
                        # If we can't access it for logging, that's okay
                        logger.debug(
                            f"Subquery for field {key} has output_field (could not log value)"
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

                for expr in source_expressions:
                    if isinstance(expr, Subquery):
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

                # No need to resolve expression with None parameters
                # The nested Subquery output_field has already been set above if needed
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
        return safe_kwargs

    def _apply_in_memory_assignments(
        self, instances, kwargs, per_object_values, has_subquery
    ):
        """
        Apply field values to in-memory instances prior to DB update when safe.

        - Skips assignment entirely if a Subquery is present in kwargs
        - Uses per_object_values (from bulk_update) when provided
        - Avoids assigning unresolved expression objects to Python instances
        """
        if has_subquery:
            logger.debug(
                "Skipping in-memory field assignments due to Subquery detection"
            )
            return

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
                        from django.db.models import Value

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

    def _detect_subquery_fields(self, update_kwargs, Subquery):
        """
        Detect Subquery-valued fields in update kwargs.

        Returns:
            (bool, list[str]): (has_subquery, detected_field_names)
        """
        logger.debug(f"Checking for Subquery objects in {len(update_kwargs)} kwargs")

        subquery_detected = []
        for key, value in update_kwargs.items():
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

        if not has_subquery:
            # Check if we missed any Subquery-like objects for visibility
            for k, v in update_kwargs.items():
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

        return has_subquery, subquery_detected


class TriggerQuerySet(TriggerQuerySetMixin, models.QuerySet):
    """
    A QuerySet that provides bulk trigger functionality.
    This is the traditional approach for backward compatibility.
    """

    pass
