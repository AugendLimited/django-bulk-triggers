import logging

from django.core.exceptions import ValidationError
from django.db import models
from django_bulk_hooks.registry import get_hooks

logger = logging.getLogger(__name__)


def safe_get_related_object(instance, field_name):
    """
    Safely get a related object without raising RelatedObjectDoesNotExist.
    Returns None if the foreign key field is None or the related object doesn't exist.
    """
    if not hasattr(instance, field_name):
        return None
    
    # Get the foreign key field
    try:
        field = instance._meta.get_field(field_name)
        if not field.is_relation or field.many_to_many or field.one_to_many:
            return getattr(instance, field_name, None)
    except models.FieldDoesNotExist:
        return getattr(instance, field_name, None)
    
    # Check if the foreign key field is None
    fk_field_name = f"{field_name}_id"
    if hasattr(instance, fk_field_name) and getattr(instance, fk_field_name) is None:
        return None
    
    # Try to get the related object, but catch RelatedObjectDoesNotExist
    try:
        return getattr(instance, field_name)
    except field.related_model.RelatedObjectDoesNotExist:
        return None


def safe_get_related_attr(instance, field_name, attr_name=None):
    """
    Safely get a related object or its attribute without raising RelatedObjectDoesNotExist.
    
    Args:
        instance: The model instance
        field_name: The foreign key field name
        attr_name: Optional attribute name to access on the related object
    
    Returns:
        The related object, the attribute value, or None if not available
    """
    related_obj = safe_get_related_object(instance, field_name)
    if related_obj is None:
        return None
    
    if attr_name is None:
        return related_obj
    
    return getattr(related_obj, attr_name, None)


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
