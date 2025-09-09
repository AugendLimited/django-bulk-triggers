import logging

from django.core.exceptions import ValidationError

from django_bulk_triggers.registry import get_triggers

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

    # Check if we're in a bypass context
    if ctx and hasattr(ctx, "bypass_triggers") and ctx.bypass_triggers:
        logger.debug("engine.run bypassed")
        return

    # Salesforce-style trigger execution: Allow nested triggers but prevent infinite recursion
    from django_bulk_triggers.handler import trigger_vars

    # Initialize trigger execution tracking if not present
    if not hasattr(trigger_vars, "trigger_depth"):
        trigger_vars.trigger_depth = 0
    if not hasattr(trigger_vars, "trigger_stack"):
        trigger_vars.trigger_stack = []

    # Create a unique key for this trigger execution context
    trigger_key = f"{model_name}.{event}"
    
    # Salesforce allows up to 200 levels of trigger depth - we'll use a conservative limit
    MAX_TRIGGER_DEPTH = 50
    
    if trigger_vars.trigger_depth >= MAX_TRIGGER_DEPTH:
        logger.error(
            f"FRAMEWORK ERROR: Maximum trigger depth ({MAX_TRIGGER_DEPTH}) exceeded for {trigger_key}. "
            "This indicates infinite recursion in triggers. Current stack: {trigger_vars.trigger_stack}"
        )
        raise RuntimeError(f"Maximum trigger depth exceeded for {trigger_key}")

    # Increment trigger depth and add to stack
    trigger_vars.trigger_depth += 1
    trigger_vars.trigger_stack.append(trigger_key)
    logger.debug(
        f"FRAMEWORK DEBUG: Starting {trigger_key} at depth {trigger_vars.trigger_depth}. "
        f"Current stack: {trigger_vars.trigger_stack}"
    )

    try:
        # For BEFORE_* events, run model.clean() first for validation
        if event.lower().startswith("before_"):
            for instance in new_records:
                try:
                    instance.clean()
                except ValidationError as e:
                    logger.error("Validation failed for %s: %s", instance, e)
                    raise

        # Process triggers
        for handler_cls, method_name, condition, priority in triggers:
            # Safely get handler class name
            handler_name = getattr(handler_cls, "__name__", str(handler_cls))
            logger.debug(f"Processing {handler_name}.{method_name}")
            logger.debug(
                f"FRAMEWORK DEBUG: Trigger {handler_name}.{method_name} - condition: {condition}, priority: {priority}"
            )
            handler_instance = handler_cls()
            func = getattr(handler_instance, method_name)

            to_process_new = []
            to_process_old = []

            for new, original in zip(
                new_records,
                old_records or [None] * len(new_records),
                strict=True,
            ):
                if not condition:
                    to_process_new.append(new)
                    to_process_old.append(original)
                    logger.debug(
                        f"FRAMEWORK DEBUG: No condition for {handler_name}.{method_name}, adding record pk={getattr(new, 'pk', 'No PK')}"
                    )
                else:
                    # DEBUG: Add extra logging for balance field to debug user's issue
                    if hasattr(condition, 'field') and condition.field == "balance":
                        logger.debug("🔍 ENGINE DEBUG: About to check HasChanged('balance') condition")
                        logger.debug(f"  - Handler: {handler_name}.{method_name}")
                        logger.debug(f"  - New record pk: {getattr(new, 'pk', 'No PK')}")
                        logger.debug(f"  - Original record: {original}")
                        logger.debug(f"  - Original record pk: {getattr(original, 'pk', 'No PK') if original else 'None'}")
                        if new and hasattr(new, 'balance'):
                            logger.debug(f"  - New record balance: {getattr(new, 'balance', 'NO_BALANCE_FIELD')} (type: {type(getattr(new, 'balance', 'NO_BALANCE_FIELD')).__name__})")
                        if original and hasattr(original, 'balance'):
                            logger.debug(f"  - Original record balance: {getattr(original, 'balance', 'NO_BALANCE_FIELD')} (type: {type(getattr(original, 'balance', 'NO_BALANCE_FIELD')).__name__})")
                        
                    condition_result = condition.check(new, original)
                    logger.debug(
                        f"FRAMEWORK DEBUG: Condition check for {handler_name}.{method_name} on record pk={getattr(new, 'pk', 'No PK')}: {condition_result}"
                    )
                    if condition_result:
                        to_process_new.append(new)
                        to_process_old.append(original)
                        logger.debug(
                            f"FRAMEWORK DEBUG: Condition passed, adding record pk={getattr(new, 'pk', 'No PK')}"
                        )
                    else:
                        logger.debug(
                            f"FRAMEWORK DEBUG: Condition failed, skipping record pk={getattr(new, 'pk', 'No PK')}"
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
        # Salesforce-style cleanup: decrement depth and remove from stack
        if hasattr(trigger_vars, "trigger_depth") and trigger_vars.trigger_depth > 0:
            trigger_vars.trigger_depth -= 1
            if hasattr(trigger_vars, "trigger_stack") and trigger_vars.trigger_stack:
                removed_trigger = trigger_vars.trigger_stack.pop()
                logger.debug(
                    f"FRAMEWORK DEBUG: Completed {removed_trigger} at depth {trigger_vars.trigger_depth + 1}. "
                    f"Remaining stack: {trigger_vars.trigger_stack}"
                )
            
            # Reset tracking variables when we're back to the top level
            if trigger_vars.trigger_depth == 0:
                trigger_vars.trigger_stack = []
                logger.debug("FRAMEWORK DEBUG: Reset trigger stack - back to top level")
