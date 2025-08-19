import logging

from django.core.exceptions import ValidationError

from django_bulk_hooks.registry import get_hooks

logger = logging.getLogger(__name__)


def run(model_cls, event, new_records, old_records=None, ctx=None):
    """
    Run hooks for a given model, event, and records.
    """
    if not new_records:
        return

    # Get hooks for this model and event
    hooks = get_hooks(model_cls, event)

    if not hooks:
        return

    import traceback

    stack = traceback.format_stack()
    print(f"DEBUG: engine.run {model_cls.__name__}.{event} {len(new_records)} records")
    
    # Check if we're in a bypass context
    if ctx and hasattr(ctx, 'bypass_hooks') and ctx.bypass_hooks:
        print(f"DEBUG: engine.run bypassed")
        return

    # For BEFORE_* events, run model.clean() first for validation
    if event.startswith("before_"):
        for instance in new_records:
            try:
                instance.clean()
            except ValidationError as e:
                logger.error("Validation failed for %s: %s", instance, e)
                raise

    # Process hooks
    for handler_cls, method_name, condition, priority in hooks:
        print(f"DEBUG: Processing {handler_cls.__name__}.{method_name}")
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
            print(f"DEBUG: Executing {handler_cls.__name__}.{method_name} for {len(to_process_new)} records")
            try:
                func(
                    new_records=to_process_new,
                    old_records=to_process_old if any(to_process_old) else None,
                )
            except Exception as e:
                print(f"DEBUG: Hook execution failed: {e}")
                raise
