import logging

from django.db import models, transaction

from django_bulk_triggers import engine
from django_bulk_triggers.bulk_operations import BulkOperationsMixin
from django_bulk_triggers.constants import (
    AFTER_DELETE,
    BEFORE_DELETE,
    VALIDATE_DELETE,
)
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
        objs = list(self)
        if not objs:
            return 0

        model_cls = self.model
        ctx = TriggerContext(model_cls)

        # Run validation triggers first
        engine.run(model_cls, VALIDATE_DELETE, objs, ctx=ctx)

        # Then run business logic triggers
        engine.run(model_cls, BEFORE_DELETE, objs, ctx=ctx)

        # Before deletion, ensure all related fields are properly cached
        # to avoid DoesNotExist errors in AFTER_DELETE triggers
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

        # Run AFTER_DELETE triggers
        engine.run(model_cls, AFTER_DELETE, objs, ctx=ctx)

        return result

    @transaction.atomic
    def update(self, **kwargs):
        """
        Update QuerySet with trigger support.
        This method handles Subquery objects and complex expressions properly.
        """
        logger.debug(f"Entering update method with {len(kwargs)} kwargs")
        instances = list(self)
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
            logger.debug(
                f"FRAMEWORK DEBUG: Subquery update detected for {model_cls.__name__}"
            )
            logger.debug(f"FRAMEWORK DEBUG: Subquery kwargs = {list(kwargs.keys())}")
            for key, value in kwargs.items():
                logger.debug(
                    f"FRAMEWORK DEBUG: Subquery {key} = {type(value).__name__}"
                )
                if isinstance(value, Subquery):
                    logger.debug(
                        f"FRAMEWORK DEBUG: Subquery {key} detected (contains OuterRef - cannot log query string)"
                    )
                    logger.debug(
                        f"FRAMEWORK DEBUG: Subquery {key} output_field: {getattr(value, 'output_field', 'None')}"
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

        # For Subquery updates, skip all in-memory field assignments to prevent
        # expression objects from reaching triggers
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

        # Salesforce-style trigger behavior: Always run triggers, rely on Django's stack overflow protection
        from django_bulk_triggers.context import get_bypass_triggers

        current_bypass_triggers = get_bypass_triggers()

        # Only skip triggers if explicitly bypassed (not for recursion prevention)
        if current_bypass_triggers:
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
                from django.db.models import Case, Value, When

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
            logger.debug(
                f"FRAMEWORK DEBUG: Super update completed for {model_cls.__name__} with count {update_count}"
            )
            if has_subquery:
                logger.debug("FRAMEWORK DEBUG: Subquery update completed successfully")
                logger.debug(
                    "FRAMEWORK DEBUG: About to refresh instances to get computed values"
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
                f"FRAMEWORK DEBUG: Refreshing {len(instances)} instances for {model_cls.__name__} after Subquery update"
            )
            logger.debug(f"DEBUG: Subquery update kwargs were: {list(kwargs.keys())}")
            for key, value in kwargs.items():
                if isinstance(value, Subquery):
                    logger.debug(
                        f"DEBUG: Subquery {key} output_field: {getattr(value, 'output_field', 'None')}"
                    )
            # Simple refresh of model fields without fetching related objects
            # Subquery updates only affect the model's own fields, not relationships
            refreshed_instances = {
                obj.pk: obj for obj in model_cls._base_manager.filter(pk__in=pks)
            }

            # Bulk update all instances in memory and save pre-trigger state
            pre_trigger_state = {}
            for instance in instances:
                if instance.pk in refreshed_instances:
                    refreshed_instance = refreshed_instances[instance.pk]
                    logger.debug(
                        f"FRAMEWORK DEBUG: Refreshing instance pk={instance.pk}"
                    )
                    # Save current state before modifying for trigger comparison
                    pre_trigger_values = {}
                    for field in model_cls._meta.fields:
                        if field.name != "id":
                            try:
                                old_value = getattr(instance, field.name, None)
                            except Exception as e:
                                # Handle foreign key DoesNotExist errors gracefully
                                if field.is_relation and 'DoesNotExist' in str(type(e).__name__):
                                    old_value = None
                                else:
                                    raise
                            
                            try:
                                new_value = getattr(refreshed_instance, field.name, None)
                            except Exception as e:
                                # Handle foreign key DoesNotExist errors gracefully
                                if field.is_relation and 'DoesNotExist' in str(type(e).__name__):
                                    new_value = None
                                else:
                                    raise
                            if old_value != new_value:
                                logger.debug(
                                    f"FRAMEWORK DEBUG: Field {field.name} changed from {old_value} to {new_value}"
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
                            try:
                                refreshed_value = getattr(refreshed_instance, field.name)
                            except Exception as e:
                                # Handle foreign key DoesNotExist errors gracefully
                                if field.is_relation and 'DoesNotExist' in str(type(e).__name__):
                                    refreshed_value = None
                                else:
                                    raise
                            
                            setattr(
                                instance,
                                field.name,
                                refreshed_value,
                            )
                    pre_trigger_state[instance.pk] = pre_trigger_values
                    logger.debug(
                        f"FRAMEWORK DEBUG: Instance pk={instance.pk} refreshed successfully"
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
                        f"FRAMEWORK DEBUG: Could not find refreshed instance for pk={instance.pk}"
                    )

            # Now run BEFORE_UPDATE triggers with refreshed instances so conditions work
            logger.debug("Running BEFORE_UPDATE triggers after Subquery refresh")
            engine.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

            # Check if triggers modified any fields and persist them with bulk_update
            trigger_modified_fields = set()
            for instance in instances:
                if instance.pk in pre_trigger_state:
                    pre_trigger_values = pre_trigger_state[instance.pk]
                    for field_name, pre_trigger_value in pre_trigger_values.items():
                        current_value = getattr(instance, field_name)
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
                    f"FRAMEWORK DEBUG: About to call bulk_update with bypass_triggers=False for {model_cls.__name__}"
                )
                logger.debug(
                    f"FRAMEWORK DEBUG: trigger_modified_fields = {trigger_modified_fields}"
                )
                logger.debug(f"FRAMEWORK DEBUG: instances count = {len(instances)}")
                for i, instance in enumerate(instances):
                    logger.debug(
                        f"FRAMEWORK DEBUG: instance {i} pk={getattr(instance, 'pk', 'No PK')}"
                    )

                result = model_cls.objects.bulk_update(
                    instances, trigger_modified_fields, bypass_triggers=False
                )
                logger.debug(f"FRAMEWORK DEBUG: bulk_update result = {result}")

            # Run AFTER_UPDATE triggers for the Subquery update now that instances are refreshed
            # and any trigger modifications have been persisted
            logger.debug(
                "Running AFTER_UPDATE triggers after Subquery update and refresh"
            )
            logger.debug(
                "FRAMEWORK DEBUG: About to run AFTER_UPDATE for %s with %d instances",
                model_cls.__name__,
                len(instances),
            )
            logger.debug("FRAMEWORK DEBUG: Instance data before AFTER_UPDATE:")
            for i, instance in enumerate(instances):
                logger.debug(f"FRAMEWORK DEBUG: Instance {i} pk={instance.pk}")
                # Log key fields that might be relevant for aggregates
                for field_name in [
                    "disbursement",
                    "disbursements",
                    "amount",
                    "balance",
                ]:
                    if hasattr(instance, field_name):
                        value = getattr(instance, field_name)
                        logger.debug(
                            f"FRAMEWORK DEBUG: Instance {i} {field_name}={value} (type: {type(value).__name__})"
                        )

            from django_bulk_triggers.constants import AFTER_UPDATE

            # Save state before AFTER_UPDATE triggers so we can detect modifications
            pre_after_trigger_state = {}
            for instance in instances:
                if instance.pk is not None:
                    pre_after_trigger_values = {}
                    for field in model_cls._meta.fields:
                        if field.name != "id":
                            pre_after_trigger_values[field.name] = getattr(
                                instance, field.name, None
                            )
                    pre_after_trigger_state[instance.pk] = pre_after_trigger_values

            engine.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)
            logger.debug(
                f"FRAMEWORK DEBUG: AFTER_UPDATE completed for {model_cls.__name__}"
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
                        current_value = getattr(instance, field_name)
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
                    f"FRAMEWORK DEBUG: About to call bulk_update with triggers enabled for AFTER_UPDATE modifications on {model_cls.__name__}"
                )
                logger.debug(
                    f"FRAMEWORK DEBUG: after_trigger_modified_fields = {after_trigger_modified_fields}"
                )
                logger.debug(f"FRAMEWORK DEBUG: instances count = {len(instances)}")
                for i, instance in enumerate(instances):
                    logger.debug(
                        f"FRAMEWORK DEBUG: instance {i} pk={getattr(instance, 'pk', 'No PK')}"
                    )

                # Salesforce-style: Allow nested triggers to run for field modifications
                # The depth-based recursion detection in engine.py will prevent infinite loops
                result = model_cls.objects.bulk_update(instances, bypass_triggers=False)
                logger.debug(
                    f"FRAMEWORK DEBUG: AFTER_UPDATE bulk_update result = {result}"
                )

        # Salesforce-style: Always run AFTER_UPDATE triggers unless explicitly bypassed
        from django_bulk_triggers.constants import AFTER_UPDATE

        if not current_bypass_triggers:
            # For Subquery updates, AFTER_UPDATE triggers have already been run above
            if not has_subquery:
                logger.debug("update: running AFTER_UPDATE")
                logger.debug(
                    f"FRAMEWORK DEBUG: Running AFTER_UPDATE for {model_cls.__name__} with {len(instances)} instances"
                )
                engine.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)
            else:
                logger.debug("update: AFTER_UPDATE already run for Subquery update")
        else:
            logger.debug("update: AFTER_UPDATE explicitly bypassed")

        return update_count


class TriggerQuerySet(TriggerQuerySetMixin, models.QuerySet):
    """
    A QuerySet that provides bulk trigger functionality.
    This is the traditional approach for backward compatibility.
    """

    pass
