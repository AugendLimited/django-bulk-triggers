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
    for handler_cls, method_name, condition, priority, select_related_fields in hooks:
        # Get or create handler instance from cache
        handler_key = (handler_cls, method_name)
        if handler_key not in _handler_cache:
            handler_instance = handler_cls()
            func = getattr(handler_instance, method_name)
            _handler_cache[handler_key] = (handler_instance, func)
        else:
            handler_instance, func = _handler_cache[handler_key]

        # Apply select_related if specified
        if select_related_fields:
            new_instances_with_related = _apply_select_related(new_instances, select_related_fields)
        else:
            new_instances_with_related = new_instances

        # Filter instances based on condition
        if condition:
            to_process_new = []
            to_process_old = []

            logger.debug(f"Checking condition {condition.__class__.__name__} for {len(new_instances)} instances")
            for new, original in zip(new_instances_with_related, original_instances, strict=True):
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
            func(new_records=new_instances_with_related, old_records=original_instances if any(original_instances) else None)


def _apply_select_related(instances, related_fields):
    """
    Apply select_related to instances to prevent queries in loops.
    This function bulk loads related objects and caches them on the instances.
    """
    if not instances:
        return instances

    # Separate instances with and without PKs
    instances_with_pk = [obj for obj in instances if obj.pk is not None]
    instances_without_pk = [obj for obj in instances if obj.pk is None]

    # Bulk load related objects for instances with PKs
    if instances_with_pk:
        model_cls = instances_with_pk[0].__class__
        pks = [obj.pk for obj in instances_with_pk]
        
        # Bulk fetch with select_related
        fetched_instances = model_cls.objects.select_related(*related_fields).in_bulk(pks)
        
        # Apply cached related objects to original instances
        for obj in instances_with_pk:
            fetched_obj = fetched_instances.get(obj.pk)
            if fetched_obj:
                for field in related_fields:
                    if field not in obj._state.fields_cache:
                        try:
                            rel_obj = getattr(fetched_obj, field)
                            setattr(obj, field, rel_obj)
                            obj._state.fields_cache[field] = rel_obj
                        except AttributeError:
                            pass

    # Handle instances without PKs (e.g., BEFORE_CREATE)
    for obj in instances_without_pk:
        for field in related_fields:
            # Check if the foreign key field is set
            fk_field_name = f"{field}_id"
            if hasattr(obj, fk_field_name) and getattr(obj, fk_field_name) is not None:
                # The foreign key ID is set, so we can try to get the related object safely
                rel_obj = safe_get_related_object(obj, field)
                if rel_obj is not None:
                    # Ensure it's cached to prevent future queries
                    if not hasattr(obj._state, 'fields_cache'):
                        obj._state.fields_cache = {}
                    obj._state.fields_cache[field] = rel_obj

    return instances
