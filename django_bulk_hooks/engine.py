import logging

from django.core.exceptions import ValidationError

from django_bulk_hooks.registry import get_hooks

logger = logging.getLogger(__name__)


def run(model_cls, event, new_instances, original_instances=None, ctx=None):
    hooks = get_hooks(model_cls, event)

    if not hooks:
        return

    # For BEFORE_* events, run model.clean() first for validation
    if event.startswith("before_"):
        for instance in new_instances:
            try:
                instance.clean()
            except ValidationError as e:
                logger.error("Validation failed for %s: %s", instance, e)
                raise

    for handler_cls, method_name, condition, priority in hooks:
        handler_instance = handler_cls()
        func = getattr(handler_instance, method_name)

        to_process_new = []
        to_process_old = []

        for new, original in zip(
            new_instances,
            original_instances or [None] * len(new_instances),
            strict=True,
        ):
            if not condition or condition.check(new, original):
                to_process_new.append(new)
                to_process_old.append(original)

        if to_process_new:
            # Call the function with keyword arguments
            func(new_records=to_process_new, old_records=to_process_old if any(to_process_old) else None)
