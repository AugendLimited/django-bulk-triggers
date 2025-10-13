import logging
from unittest.mock import Mock

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
                    # SALESFORCE-LIKE BEHAVIOR: No automatic preloading
                    logger.debug(
                        f"SALESFORCE-LIKE: Evaluating conditions for {len(new_records)} records without preloading"
                    )
                    logger.debug("SALESFORCE-LIKE: If triggers need relationships, they should use @select_related decorator")
                    
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
                        
                        # SALESFORCE-LIKE: No automatic preloading, let conditions access what they need
                        
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
