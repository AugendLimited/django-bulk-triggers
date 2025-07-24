import logging

from django.core.exceptions import ValidationError
from django.db import models
from django_bulk_hooks.registry import get_hooks
from django_bulk_hooks.conditions import safe_get_related_object, safe_get_related_attr

logger = logging.getLogger(__name__)


# Cache for hook handlers to avoid creating them repeatedly
_handler_cache = {}

def run(model_cls, event, new_instances, original_instances=None, ctx=None):
    # Get hooks from cache or fetch them
    cache_key = (model_cls, event)
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
            except Exception as e:
                # Handle RelatedObjectDoesNotExist and other exceptions that might occur
                # when accessing foreign key fields on unsaved objects
                if "RelatedObjectDoesNotExist" in str(type(e).__name__):
                    logger.debug("Skipping validation for unsaved object with unset foreign keys: %s", e)
                    continue
                else:
                    logger.error("Unexpected error during validation for %s: %s", instance, e)
                    raise

    # Pre-create None list for originals if needed
    if original_instances is None:
        original_instances = [None] * len(new_instances)

    # Process all hooks
    for handler_cls, method_name, condition, priority in hooks:
        # Get or create handler instance from cache
        handler_key = (handler_cls, method_name)
        if handler_key not in _handler_cache:
            handler_instance = handler_cls()
            func = getattr(handler_instance, method_name)
            _handler_cache[handler_key] = (handler_instance, func)
        else:
            handler_instance, func = _handler_cache[handler_key]

        # If no condition, process all instances at once
        if not condition:
            func(new_records=new_instances, old_records=original_instances if any(original_instances) else None)
            continue

        # For conditional hooks, filter instances first
        to_process_new = []
        to_process_old = []

        for new, original in zip(new_instances, original_instances, strict=True):
            if condition.check(new, original):
                to_process_new.append(new)
                to_process_old.append(original)

        if to_process_new:
            # Call the function with keyword arguments
            func(new_records=to_process_new, old_records=to_process_old if any(to_process_old) else None)
