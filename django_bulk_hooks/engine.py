import logging

from django.core.exceptions import ValidationError

from django_bulk_hooks.registry import get_hooks

logger = logging.getLogger(__name__)


def run(model_cls, event, new_records, old_records=None, ctx=None):
    """
    Run hooks for a given model, event, and records.
    """
    print(f"DEBUG: engine.run called for {model_cls} with event {event}")
    print(f"DEBUG: Number of new_records: {len(new_records) if new_records else 0}")
    print(f"DEBUG: Number of old_records: {len(old_records) if old_records else 0}")
    
    if not new_records:
        print(f"DEBUG: No new_records, skipping hooks")
        return

    # Get hooks for this model and event
    hooks = get_hooks(model_cls, event)
    print(f"DEBUG: Found {len(hooks)} hooks for {model_cls}.{event}")
    
    if not hooks:
        print(f"DEBUG: No hooks found for {model_cls}.{event}")
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
        print(f"DEBUG: Processing hook: {handler_cls.__name__}.{method_name}")
        handler_instance = handler_cls()
        func = getattr(handler_instance, method_name)

        to_process_new = []
        to_process_old = []

        for new, original in zip(
            new_records,
            old_records or [None] * len(new_records),
            strict=True,
        ):
            print(f"DEBUG: Checking condition for {handler_cls.__name__}.{method_name}")
            print(f"DEBUG:  - new: {type(new)}")
            print(f"DEBUG:  - original: {type(original)}")
            print(f"DEBUG:  - condition: {condition}")
            if not condition or condition.check(new, original):
                print(f"DEBUG:  - condition passed, adding to process list")
                to_process_new.append(new)
                to_process_old.append(original)
            else:
                print(f"DEBUG:  - condition failed, skipping")

        if to_process_new:
            print(f"DEBUG: Executing hook {handler_cls.__name__}.{method_name} with {len(to_process_new)} records")
            try:
                func(new_records=to_process_new, old_records=to_process_old if any(to_process_old) else None)
                print(f"DEBUG: Hook {handler_cls.__name__}.{method_name} executed successfully")
            except Exception as e:
                print(f"DEBUG: Hook {handler_cls.__name__}.{method_name} failed with error: {e}")
                raise
        else:
            print(f"DEBUG: Skipping hook {handler_cls.__name__}.{method_name} - no records to process")
