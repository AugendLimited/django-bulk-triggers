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

    # Salesforce-style trigger execution: Allow nested triggers, let Django handle recursion
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

            for new, original in zip(
                new_records,
                old_records or [None] * len(new_records),
                strict=True,
            ):
                if not condition:
                    to_process_new.append(new)
                    to_process_old.append(original)
                    logger.debug(
                        f"No condition for {handler_name}.{method_name}, adding record pk={getattr(new, 'pk', 'No PK')}"
                    )
                else:
                    condition_result = condition.check(new, original)
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
