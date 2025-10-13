import logging
from unittest.mock import Mock

from django.core.exceptions import ValidationError

from django_bulk_triggers.registry import get_triggers
from django_bulk_triggers.debug_utils import QueryTracker, log_query_count

logger = logging.getLogger(__name__)


def run(model_cls, event, new_records, old_records=None, ctx=None):
    """
    Run triggers for a given model, event, and records.
    """
    if not new_records:
        return

    # Get triggers for this model and event
    triggers = get_triggers(model_cls, event)

    if not triggers:
        return

    # Safely get model name, fallback to str representation if __name__ not available
    model_name = getattr(model_cls, "__name__", str(model_cls))
    logger.debug(f"engine.run {model_name}.{event} {len(new_records)} records")
    
    # Track queries for this trigger execution
    with QueryTracker(f"engine.run {model_name}.{event}"):
        log_query_count(f"start of engine.run {model_name}.{event}")

        # Check if we're in a bypass context
        if ctx and hasattr(ctx, "bypass_triggers") and ctx.bypass_triggers:
            logger.debug("engine.run bypassed")
            return

        # Salesforce-style trigger execution: Allow nested triggers, let Django handle recursion
        try:
            # For BEFORE_* events, run model.clean() first for validation
            # Skip individual clean() calls to avoid N+1 queries - validation triggers will handle this
            if event.lower().startswith("before_"):
                # Note: Individual clean() calls are skipped to prevent N+1 queries
                # Validation triggers (VALIDATE_*) will handle validation instead
                pass

            # Process triggers
            for handler_cls, method_name, condition, priority in triggers:
                # Safely get handler class name
                handler_name = getattr(handler_cls, "__name__", str(handler_cls))
                logger.debug(f"Processing {handler_name}.{method_name}")
                logger.debug(
                    f"FRAMEWORK DEBUG: Trigger {handler_name}.{method_name} - condition: {condition}, priority: {priority}"
                )
                # Use factory pattern for DI support
                from django_bulk_triggers.factory import create_trigger_instance
                handler_instance = create_trigger_instance(handler_cls)
                func = getattr(handler_instance, method_name)

                preload_related = getattr(func, "_select_related_preload", None)
                if preload_related and new_records:
                    try:
                        from django_bulk_triggers.constants import BEFORE_CREATE

                        model_cls_override = getattr(handler_instance, "model_cls", None)

                        if event == BEFORE_CREATE:
                            preload_related(new_records, model_cls=model_cls_override)
                    except Exception:
                        logger.debug(
                            "select_related preload failed for %s.%s",
                            handler_name,
                            method_name,
                            exc_info=True,
                        )

                to_process_new = []
                to_process_old = []

                # CRITICAL FIX: Avoid N+1 queries by preloading relationships for condition evaluation
                if not condition:
                    # No condition - process all records
                    to_process_new = new_records
                    to_process_old = old_records or [None] * len(new_records)
                    logger.debug(
                        f"No condition for {handler_name}.{method_name}, processing all {len(new_records)} records"
                    )
                else:
                    # Preload relationships to avoid N+1 queries during condition evaluation
                    logger.debug(
                        f"Preloading relationships for condition evaluation on {len(new_records)} records"
                    )
                    
                    # Get all foreign key fields that might be accessed by conditions
                    fk_fields = [
                        field.name for field in model_cls._meta.concrete_fields
                        if field.is_relation and not field.many_to_many
                    ]
                    
                    # If we have foreign key fields, we need to ensure they're preloaded
                    if fk_fields and new_records:
                        logger.debug(f"N+1 DEBUG: Found {len(fk_fields)} FK fields: {fk_fields}")
                        
                        # Get primary keys of all records
                        pks = [getattr(record, 'pk', None) for record in new_records if hasattr(record, 'pk')]
                        logger.debug(f"N+1 DEBUG: Found {len(pks)} primary keys to reload")
                        
                        # CRITICAL FIX: Only reload existing records (with PKs) to prevent N+1 queries
                        # For new records (pk=None), we can't reload them, so we need to handle them differently
                        # Also skip Mock objects and other non-model instances
                        existing_records = []
                        for pk in pks:
                            if pk is not None and not isinstance(pk, Mock):
                                existing_records.append(pk)
                        new_records_count = len(pks) - len(existing_records)
                        
                        if existing_records:
                            logger.debug(f"N+1 DEBUG: Reloading {len(existing_records)} existing records with select_related for fields: {fk_fields}")
                            # Reload existing records with select_related to preload all FK relationships
                            reloaded_records = model_cls._base_manager.filter(pk__in=existing_records).select_related(*fk_fields)
                            logger.debug(f"N+1 DEBUG: Reloaded {len(reloaded_records)} existing records")
                            
                            # Create a mapping for quick lookup
                            reloaded_map = {record.pk: record for record in reloaded_records}
                            
                            # Create a new list with reloaded records instead of modifying in place
                            # This fixes the TypeError when new_records is a TriggerQuerySet
                            updated_records = []
                            for record in new_records:
                                if hasattr(record, 'pk') and record.pk in reloaded_map:
                                    updated_records.append(reloaded_map[record.pk])
                                    logger.debug(f"N+1 DEBUG: Replaced existing record with reloaded version")
                                else:
                                    updated_records.append(record)
                            new_records = updated_records
                        
                        if new_records_count > 0:
                            logger.debug(f"N+1 DEBUG: {new_records_count} new records (pk=None) - cannot reload, will handle in condition evaluation")
                            
                            # CRITICAL FIX: For new records, we need to preload FK relationships to avoid N+1 queries
                            # We'll collect all unique FK values and preload them in bulk
                            fk_values_to_preload = {}
                            for fk_field in fk_fields:
                                fk_values_to_preload[fk_field] = set()
                            
                            # Collect all FK values from new records
                            for record in new_records:
                                if getattr(record, 'pk', None) is None:  # Only new records
                                    for fk_field in fk_fields:
                                        fk_value = getattr(record, fk_field + '_id', None)
                                        if fk_value is not None:
                                            fk_values_to_preload[fk_field].add(fk_value)
                            
                            # Preload FK relationships in bulk
                            preloaded_fk_objects = {}
                            for fk_field, fk_values in fk_values_to_preload.items():
                                if fk_values:
                                    logger.debug(f"N+1 DEBUG: Preloading {len(fk_values)} {fk_field} objects")
                                    fk_model = model_cls._meta.get_field(fk_field).related_model
                                    preloaded_objects = fk_model._base_manager.filter(pk__in=fk_values)
                                    preloaded_fk_objects[fk_field] = {obj.pk: obj for obj in preloaded_objects}
                                    logger.debug(f"N+1 DEBUG: Preloaded {len(preloaded_objects)} {fk_field} objects")
                            
                            # Cache the preloaded objects on the records to avoid future queries
                            for record in new_records:
                                if getattr(record, 'pk', None) is None:  # Only new records
                                    for fk_field, preloaded_objects in preloaded_fk_objects.items():
                                        fk_value = getattr(record, fk_field + '_id', None)
                                        if fk_value is not None and fk_value in preloaded_objects:
                                            # Cache the preloaded object to avoid future queries
                                            setattr(record, fk_field, preloaded_objects[fk_value])
                                            logger.debug(f"N+1 DEBUG: Cached {fk_field} object for new record")
                    
                    # Now evaluate conditions - relationships should be preloaded
                    logger.debug(
                        f"Evaluating conditions for {handler_name}.{method_name} on {len(new_records)} records"
                    )
                    
                    for i, (new, original) in enumerate(zip(
                        new_records,
                        old_records or [None] * len(new_records),
                        strict=True,
                    )):
                        logger.debug(f"N+1 DEBUG: About to check condition for record {i} (pk={getattr(new, 'pk', 'No PK')})")
                        logger.debug(f"N+1 DEBUG: Record {i} type: {type(new).__name__}")
                        logger.debug(f"N+1 DEBUG: Record {i} has FK fields: {[f for f in fk_fields if hasattr(new, f)]}")
                        
                        # Log FK field access before condition check
                        for fk_field in fk_fields:
                            if hasattr(new, fk_field):
                                try:
                                    fk_value = getattr(new, fk_field)
                                    logger.debug(f"N+1 DEBUG: Record {i} FK field {fk_field} = {fk_value} (type: {type(fk_value).__name__})")
                                except Exception as e:
                                    logger.debug(f"N+1 DEBUG: Record {i} FK field {fk_field} access failed: {e}")
                        
                        # Add query count tracking before condition check
                        from django.db import connection
                        initial_query_count = len(connection.queries)
                        logger.debug(f"N+1 DEBUG: Query count before condition check: {initial_query_count}")
                        
                        condition_result = condition.check(new, original)
                        
                        # Check if any queries were executed during condition check
                        final_query_count = len(connection.queries)
                        queries_executed = final_query_count - initial_query_count
                        if queries_executed > 0:
                            logger.debug(f"N+1 DEBUG: {queries_executed} queries executed during condition check for record {i}")
                            for j, query in enumerate(connection.queries[initial_query_count:], 1):
                                logger.debug(f"N+1 DEBUG:   Query {j}: {query['sql'][:100]}...")
                        
                        logger.debug(
                            f"Condition check for {handler_name}.{method_name} on record pk={getattr(new, 'pk', 'No PK')}: {condition_result}"
                        )
                        if condition_result:
                            to_process_new.append(new)
                            to_process_old.append(original)
                            logger.debug(
                                f"Condition passed, adding record pk={getattr(new, 'pk', 'No PK')}"
                            )
                        else:
                            logger.debug(
                                f"Condition failed, skipping record pk={getattr(new, 'pk', 'No PK')}"
                            )

                if to_process_new:
                    logger.debug(
                        f"Executing {handler_name}.{method_name} for {len(to_process_new)} records"
                    )
                    logger.debug(
                        f"FRAMEWORK DEBUG: About to execute {handler_name}.{method_name}"
                    )
                    logger.debug(
                        f"FRAMEWORK DEBUG: Records to process: {[getattr(r, 'pk', 'No PK') for r in to_process_new]}"
                    )
                    try:
                        func(
                            new_records=to_process_new,
                            old_records=to_process_old if any(to_process_old) else None,
                        )
                        logger.debug(
                            f"FRAMEWORK DEBUG: Successfully executed {handler_name}.{method_name}"
                        )
                    except Exception as e:
                        logger.debug(f"Trigger execution failed: {e}")
                        logger.debug(
                            f"FRAMEWORK DEBUG: Exception in {handler_name}.{method_name}: {e}"
                        )
                        raise
        finally:
            # No cleanup needed - let Django handle recursion naturally
            pass
