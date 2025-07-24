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

        # Filter instances based on condition
        if condition:
            to_process_new = []
            to_process_old = []

            logger.debug(f"Checking condition {condition.__class__.__name__} for {len(new_instances)} instances")
            for new, original in zip(new_instances, original_instances, strict=True):
                logger.debug(f"Checking instance {new.__class__.__name__}(pk={new.pk})")
                try:
                    matches = condition.check(new, original)
                    logger.debug(f"Condition check result: {matches}")
                    if matches:
                        to_process_new.append(new)
                        to_process_old.append(original)
                except Exception as e:
                    logger.error(f"Error checking condition: {e}")
                    raise

            # Only call if we have matching instances
            if to_process_new:
                logger.debug(f"Running hook for {len(to_process_new)} matching instances")
                func(new_records=to_process_new, old_records=to_process_old if any(to_process_old) else None)
            else:
                logger.debug("No instances matched condition")
        else:
            # No condition, process all instances
            logger.debug("No condition, processing all instances")
            func(new_records=new_instances, old_records=original_instances if any(original_instances) else None)
