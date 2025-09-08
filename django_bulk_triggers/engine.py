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

    # Salesforce-style recursion detection: Check if we're already executing this trigger
    from django_bulk_triggers.handler import trigger_vars

    # Create a unique key for this trigger execution
    trigger_key = f"{model_name}.{event}"

    # Check if this trigger is already executing (Salesforce-style recursion prevention)
    if hasattr(trigger_vars, "executing_triggers"):
        if trigger_key in trigger_vars.executing_triggers:
            logger.debug(
                f"engine.run skipping {trigger_key} - already executing (Salesforce-style recursion prevention)"
            )
            return
    else:
        trigger_vars.executing_triggers = set()

    # Mark this trigger as executing
    trigger_vars.executing_triggers.add(trigger_key)

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
                else:
                    condition_result = condition.check(new, original)
                    if condition_result:
                        to_process_new.append(new)
                        to_process_old.append(original)

            if to_process_new:
                logger.debug(
                    f"Executing {handler_name}.{method_name} for {len(to_process_new)} records"
                )
                try:
                    func(
                        new_records=to_process_new,
                        old_records=to_process_old if any(to_process_old) else None,
                    )
                except Exception as e:
                    logger.debug(f"Trigger execution failed: {e}")
                    raise
    finally:
        # Always remove this trigger from the executing set (Salesforce-style cleanup)
        if hasattr(trigger_vars, "executing_triggers"):
            trigger_vars.executing_triggers.discard(trigger_key)
