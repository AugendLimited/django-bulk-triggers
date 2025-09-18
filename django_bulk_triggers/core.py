"""
Core trigger engine for django-bulk-triggers.

This module contains the TriggerEngine class that encapsulates all trigger execution
logic, extracted from queryset.py to eliminate tight coupling and improve maintainability.

Mission-critical requirements:
- Zero hacks or shortcuts
- Maintain exact same behavior as original
- Use dependency injection to prevent circular imports
- Comprehensive error handling
- Production-grade code quality
"""

from typing import List, Dict, Any, Tuple

from django.db import models
from django.db.models import Subquery, Case, Value, When

from django_bulk_triggers.constants import (
    AFTER_DELETE,
    BEFORE_DELETE,
    VALIDATE_DELETE,
    BEFORE_UPDATE,
    AFTER_UPDATE,
    VALIDATE_UPDATE,
)
from django_bulk_triggers.logging_config import get_logger

logger = get_logger(__name__)


class TriggerEngine:
    """
    Core engine for executing triggers around database operations.
    
    This class encapsulates all trigger execution logic, providing a clean
    interface for bulk operations while maintaining the exact same behavior
    as the original queryset implementation.
    
    Responsibilities:
    - Execute triggers around database operations
    - Handle complex Subquery updates
    - Manage trigger contexts and bypass states
    - Detect field modifications
    - Build CASE statements for field updates
    """
    
    def __init__(self, model_cls: type):
        """
        Initialize the trigger engine for a specific model.
        
        Args:
            model_cls: The Django model class this engine operates on
        """
        self.model_cls = model_cls
        self._engine_module = None
        self._context_module = None
        self._mti_operations = None
    
    @property
    def engine_module(self):
        """Get engine module with lazy import."""
        if self._engine_module is None:
            from django_bulk_triggers.services import get_engine_module
            self._engine_module = get_engine_module()
        return self._engine_module
    
    @property
    def context_module(self):
        """Get context module with lazy import."""
        if self._context_module is None:
            from django_bulk_triggers.services import get_context_module
            self._context_module = get_context_module()
        return self._context_module
    
    @property
    def mti_operations(self):
        """Get MTI operations with lazy import."""
        if self._mti_operations is None:
            from django_bulk_triggers.services import get_mti_operations
            self._mti_operations = get_mti_operations()
        return self._mti_operations
    
    
    def execute_delete_triggers(self, instances: List[models.Model], delete_operation_func):
        """
        Execute triggers around a delete operation.
        
        Args:
            instances: List of model instances to delete
            delete_operation_func: Function that performs the actual delete operation
            
        Returns:
            Result of the delete operation
        """
        if not instances:
            return 0

        model_cls = self.model_cls
        ctx = self.context_module['TriggerContext'](model_cls)

        # Run validation triggers first
        self.engine_module.run(model_cls, VALIDATE_DELETE, instances, ctx=ctx)

        # Then run business logic triggers
        self.engine_module.run(model_cls, BEFORE_DELETE, instances, ctx=ctx)

        # Before deletion, ensure all related fields are properly cached
        # to avoid DoesNotExist errors in AFTER_DELETE triggers
        for obj in instances:
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

        # Execute the actual delete operation
        result = delete_operation_func()

        # Run AFTER_DELETE triggers
        self.engine_module.run(model_cls, AFTER_DELETE, instances, ctx=ctx)

        return result
    
    def execute_update_triggers(self, instances: List[models.Model], update_operation_func, **kwargs) -> int:
        """
        Execute triggers around an update operation.
        
        This method handles:
        - Subquery detection and processing
        - Trigger execution (validation, before, after)
        - Field modification detection
        - CASE statement building for complex updates
        - Proper context management
        
        Args:
            instances: List of model instances to update
            update_operation_func: Function that performs the actual update operation
            **kwargs: Update field values
            
        Returns:
            Number of updated objects
        """
        logger.debug(f"Entering update method with {len(kwargs)} kwargs")
        
        if not instances:
            return 0

        model_cls = self.model_cls
        pks = [obj.pk for obj in instances]

        # Load originals for trigger comparison and ensure they match the order of instances
        # Use the base manager to avoid recursion
        original_map = {
            obj.pk: obj for obj in model_cls._base_manager.filter(pk__in=pks)
        }
        originals = [original_map.get(obj.pk) for obj in instances]

        # Detect Subquery objects
        has_subquery, subquery_detected = self._detect_subqueries(kwargs)
        
        # Apply field updates to instances
        self._apply_field_updates(instances, kwargs, has_subquery)
        
        # Determine trigger execution context
        ctx = self._determine_trigger_context(model_cls, has_subquery)
        
        # Execute triggers and database operations
        update_count = self._execute_update_with_triggers(
            instances, originals, kwargs, has_subquery, ctx, update_operation_func
        )
        
        return update_count
    
    def _detect_subqueries(self, kwargs: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Detect Subquery objects in update kwargs.
        
        Args:
            kwargs: Update field values
            
        Returns:
            Tuple of (has_subquery, detected_keys)
        """
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
                f"FRAMEWORK Subquery update detected for {self.model_cls.__name__}"
            )
            logger.debug(f"FRAMEWORK Subquery kwargs = {list(kwargs.keys())}")
            for key, value in kwargs.items():
                logger.debug(
                    f"FRAMEWORK Subquery {key} = {type(value).__name__}"
                )
                if isinstance(value, Subquery):
                    logger.debug(
                        f"FRAMEWORK Subquery {key} detected (contains OuterRef - cannot log query string)"
                    )
                    logger.debug(
                        f"FRAMEWORK Subquery {key} output_field: {getattr(value, 'output_field', 'None')}"
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

        return has_subquery, subquery_detected
    
    def _apply_field_updates(self, instances: List[models.Model], kwargs: Dict[str, Any], has_subquery: bool):
        """
        Apply field updates to instances, handling Subquery objects properly.
        
        Args:
            instances: Model instances to update
            kwargs: Update field values
            has_subquery: Whether Subquery objects are present
        """
        # If a per-object value map exists (from bulk_update), prefer it over kwargs
        # IMPORTANT: Do not assign Django expression objects (e.g., Subquery/Case/F)
        # to in-memory instances before running BEFORE_UPDATE triggers. Triggers must not
        # receive unresolved expression objects.
        per_object_values = self.context_module['get_bulk_update_value_map']()

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
    
    def _determine_trigger_context(self, model_cls: type, has_subquery: bool):
        """
        Determine the appropriate trigger context based on current state.
        
        Args:
            model_cls: The model class
            has_subquery: Whether Subquery objects are present
            
        Returns:
            TriggerContext instance
        """
        # Salesforce-style trigger behavior: Always run triggers, rely on Django's stack overflow protection
        current_bypass_triggers = self.context_module['get_bypass_triggers']()
        bulk_update_active = self.context_module['get_bulk_update_active']()

        # Skip triggers if we're in a bulk_update operation (to avoid double execution)
        if bulk_update_active:
            logger.debug("update: skipping triggers because we're in bulk_update")
            ctx = self.context_module['TriggerContext'](model_cls, bypass_triggers=True)
        elif current_bypass_triggers:
            logger.debug("update: triggers explicitly bypassed")
            ctx = self.context_module['TriggerContext'](model_cls, bypass_triggers=True)
        else:
            # Always run triggers - Django will handle stack overflow protection
            logger.debug("update: running triggers with Salesforce-style behavior")
            ctx = self.context_module['TriggerContext'](model_cls, bypass_triggers=False)

        return ctx
    
    def _execute_update_with_triggers(
        self, 
        instances: List[models.Model], 
        originals: List[models.Model], 
        kwargs: Dict[str, Any], 
        has_subquery: bool, 
        ctx,
        update_operation_func
    ) -> int:
        """
        Execute the complete update operation with trigger handling.
        
        Args:
            instances: Model instances to update
            originals: Original instances for comparison
            kwargs: Update field values
            has_subquery: Whether Subquery objects are present
            ctx: Trigger context
            update_operation_func: Function that performs the actual update
            
        Returns:
            Number of updated objects
        """
        model_cls = self.model_cls
        
        # Run validation triggers first
        self.engine_module.run(model_cls, VALIDATE_UPDATE, instances, originals, ctx=ctx)

        # For Subquery updates, skip BEFORE_UPDATE triggers here - they'll run after refresh
        if not has_subquery:
            # Then run BEFORE_UPDATE triggers for non-Subquery updates
            self.engine_module.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

        # Persist any additional field mutations made by BEFORE_UPDATE triggers.
        # Build CASE statements per modified field not already present in kwargs.
        # Note: For Subquery updates, this will be empty since triggers haven't run yet
        # For Subquery updates, trigger modifications are handled later via bulk_update
        if not has_subquery:
            modified_fields = self.mti_operations.detect_modified_fields(instances, originals)
            extra_fields = [f for f in modified_fields if f not in kwargs]
        else:
            extra_fields = []  # Skip for Subquery updates

        if extra_fields:
            kwargs = self._build_case_statements(instances, kwargs, extra_fields, model_cls)

        # Execute the database update
        update_count = self._execute_database_update(instances, kwargs, has_subquery, model_cls, update_operation_func)

        # Handle Subquery-specific post-processing
        if has_subquery and instances and not ctx.bypass_triggers:
            self._handle_subquery_post_processing(instances, originals, ctx, model_cls)

        # Salesforce-style: Always run AFTER_UPDATE triggers unless explicitly bypassed
        if not ctx.bypass_triggers:
            # For Subquery updates, AFTER_UPDATE triggers have already been run above
            if not has_subquery:
                logger.debug("update: running AFTER_UPDATE")
                logger.debug(
                    f"FRAMEWORK Running AFTER_UPDATE for {model_cls.__name__} with {len(instances)} instances"
                )
                self.engine_module.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)
            else:
                logger.debug("update: AFTER_UPDATE already run for Subquery update")
        else:
            logger.debug("update: AFTER_UPDATE explicitly bypassed")

        return update_count
    
    def _build_case_statements(
        self, 
        instances: List[models.Model], 
        kwargs: Dict[str, Any], 
        extra_fields: List[str], 
        model_cls: type
    ) -> Dict[str, Any]:
        """
        Build CASE statements for fields modified by triggers.
        
        Args:
            instances: Model instances
            kwargs: Original update kwargs
            extra_fields: Fields modified by triggers
            model_cls: Model class
            
        Returns:
            Updated kwargs with CASE statements
        """
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

        return kwargs
    
    def _execute_database_update(
        self, 
        instances: List[models.Model], 
        kwargs: Dict[str, Any], 
        has_subquery: bool, 
        model_cls: type,
        update_operation_func
    ) -> int:
        """
        Execute the actual database update operation.
        
        Args:
            instances: Model instances
            kwargs: Update field values
            has_subquery: Whether Subquery objects are present
            model_cls: Model class
            update_operation_func: Function that performs the actual update
            
        Returns:
            Number of updated objects
        """
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

        logger.debug(f"Calling update operation with {len(safe_kwargs)} kwargs")
        try:
            # Use the provided update operation function
            update_count = update_operation_func(**safe_kwargs)
            logger.debug(f"Super update successful, count: {update_count}")
            logger.debug(
                f"FRAMEWORK Super update completed for {model_cls.__name__} with count {update_count}"
            )
            if has_subquery:
                logger.debug("FRAMEWORK Subquery update completed successfully")
                logger.debug(
                    "FRAMEWORK About to refresh instances to get computed values"
                )
        except Exception as e:
            logger.error(f"Super update failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Safe kwargs that caused failure: {safe_kwargs}")
            raise

        return update_count
    
    def _handle_subquery_post_processing(
        self, 
        instances: List[models.Model], 
        originals: List[models.Model], 
        ctx, 
        model_cls: type
    ):
        """
        Handle post-processing for Subquery updates.
        
        This includes refreshing instances and running triggers with computed values.
        
        Args:
            instances: Model instances
            originals: Original instances
            ctx: Trigger context
            model_cls: Model class
        """
        logger.debug(
            "Refreshing instances with Subquery computed values before running triggers"
        )
        logger.debug(
            f"FRAMEWORK Refreshing {len(instances)} instances for {model_cls.__name__} after Subquery update"
        )
        
        pks = [obj.pk for obj in instances]
        
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
                    f"FRAMEWORK Refreshing instance pk={instance.pk}"
                )
                # Save current state before modifying for trigger comparison
                pre_trigger_values = {}
                for field in model_cls._meta.fields:
                    if field.name != "id":
                        try:
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
                                    f"FRAMEWORK Field {field.name} changed from {old_value} to {new_value}"
                                )
                                # Extra debug for aggregate fields
                                if field.name in [
                                    "disbursement",
                                    "disbursements",
                                    "balance",
                                    "amount",
                                ]:
                                    logger.debug(
                                        f"AGGREGATE FIELD {field.name} changed from {old_value} (type: {type(old_value).__name__}) to {new_value} (type: {type(new_value).__name__})"
                                    )
                            pre_trigger_values[field.name] = new_value
                            try:
                                refreshed_value = getattr(
                                    refreshed_instance, field.name
                                )
                            except Exception as e:
                                # Handle foreign key DoesNotExist errors gracefully
                                if field.is_relation and "DoesNotExist" in str(
                                    type(e).__name__
                                ):
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
                        f"FRAMEWORK Instance pk={instance.pk} refreshed successfully"
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
                                f"Final {field_name} value after refresh: {final_value} (type: {type(final_value).__name__})"
                            )
            else:
                logger.warning(
                    f"FRAMEWORK Could not find refreshed instance for pk={instance.pk}"
                )

        # Now run BEFORE_UPDATE triggers with refreshed instances so conditions work
        logger.debug("Running BEFORE_UPDATE triggers after Subquery refresh")
        self.engine_module.run(model_cls, BEFORE_UPDATE, instances, originals, ctx=ctx)

        # Check if triggers modified any fields and persist them with bulk_update
        trigger_modified_fields = set()
        for instance in instances:
            if instance.pk in pre_trigger_state:
                pre_trigger_values = pre_trigger_state[instance.pk]
                for field_name, pre_trigger_value in pre_trigger_values.items():
                    try:
                        current_value = getattr(instance, field_name)
                    except Exception as e:
                        # Handle foreign key DoesNotExist errors gracefully
                        field = instance._meta.get_field(field_name)
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
                f"FRAMEWORK About to call bulk_update with bypass_triggers=False for {model_cls.__name__}"
            )
            logger.debug(
                f"FRAMEWORK trigger_modified_fields = {trigger_modified_fields}"
            )
            logger.debug(f"FRAMEWORK instances count = {len(instances)}")
            for i, instance in enumerate(instances):
                logger.debug(
                    f"FRAMEWORK instance {i} pk={getattr(instance, 'pk', 'No PK')}"
                )

            result = model_cls.objects.bulk_update(
                instances, trigger_modified_fields, bypass_triggers=False
            )
            logger.debug(f"FRAMEWORK bulk_update result = {result}")

        # Run AFTER_UPDATE triggers for the Subquery update now that instances are refreshed
        # and any trigger modifications have been persisted
        logger.debug(
            "Running AFTER_UPDATE triggers after Subquery update and refresh"
        )
        logger.debug(
            "FRAMEWORK About to run AFTER_UPDATE for %s with %d instances",
            model_cls.__name__,
            len(instances),
        )
        logger.debug("FRAMEWORK Instance data before AFTER_UPDATE:")
        for i, instance in enumerate(instances):
            logger.debug(f"FRAMEWORK Instance {i} pk={instance.pk}")
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
                        f"FRAMEWORK Instance {i} {field_name}={value} (type: {type(value).__name__})"
                    )

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

        self.engine_module.run(model_cls, AFTER_UPDATE, instances, originals, ctx=ctx)
        logger.debug(
            f"FRAMEWORK AFTER_UPDATE completed for {model_cls.__name__}"
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
                    try:
                        current_value = getattr(instance, field_name)
                    except Exception as e:
                        # Handle foreign key DoesNotExist errors gracefully
                        field = instance._meta.get_field(field_name)
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
                f"FRAMEWORK About to call bulk_update with triggers enabled for AFTER_UPDATE modifications on {model_cls.__name__}"
            )
            logger.debug(
                f"FRAMEWORK after_trigger_modified_fields = {after_trigger_modified_fields}"
            )
            logger.debug(f"FRAMEWORK instances count = {len(instances)}")
            for i, instance in enumerate(instances):
                logger.debug(
                    f"FRAMEWORK instance {i} pk={getattr(instance, 'pk', 'No PK')}"
                )

            # Salesforce-style: Allow nested triggers to run for field modifications
            # The depth-based recursion detection in engine.py will prevent infinite loops
            result = model_cls.objects.bulk_update(instances, bypass_triggers=False)
            logger.debug(
                f"FRAMEWORK AFTER_UPDATE bulk_update result = {result}"
            )
