from django.db import models


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


def is_field_set(instance, field_name):
    """
    Check if a foreign key field is set without raising RelatedObjectDoesNotExist.
    
    Args:
        instance: The model instance
        field_name: The foreign key field name
    
    Returns:
        True if the field is set, False otherwise
    """
    # Check the foreign key ID field first
    fk_field_name = f"{field_name}_id"
    if hasattr(instance, fk_field_name):
        fk_value = getattr(instance, fk_field_name, None)
        return fk_value is not None
    
    # Fallback to checking the field directly
    try:
        return getattr(instance, field_name) is not None
    except Exception:
        return False


def safe_get_related_attr(instance, field_name, attr_name=None):
    """
    Safely get a related object or its attribute without raising RelatedObjectDoesNotExist.
    
    This is particularly useful in hooks where objects might not have their related
    fields populated yet (e.g., during bulk_create operations or on unsaved objects).
    
    Args:
        instance: The model instance
        field_name: The foreign key field name
        attr_name: Optional attribute name to access on the related object
    
    Returns:
        The related object, the attribute value, or None if not available
        
    Example:
        # Instead of: loan_transaction.status.name (which might fail)
        # Use: safe_get_related_attr(loan_transaction, 'status', 'name')
        
        status_name = safe_get_related_attr(loan_transaction, 'status', 'name')
        if status_name in {Status.COMPLETE.value, Status.FAILED.value}:
            # Process the transaction
            pass
    """
    # For unsaved objects, check the foreign key ID field first
    if instance.pk is None:
        fk_field_name = f"{field_name}_id"
        if hasattr(instance, fk_field_name):
            fk_value = getattr(instance, fk_field_name, None)
            if fk_value is None:
                return None
            # If we have an ID but the object isn't loaded, try to load it
            try:
                field = instance._meta.get_field(field_name)
                if hasattr(field, 'related_model'):
                    related_obj = field.related_model.objects.get(id=fk_value)
                    if attr_name is None:
                        return related_obj
                    return getattr(related_obj, attr_name, None)
            except (field.related_model.DoesNotExist, AttributeError):
                return None
    
    # For saved objects or when the above doesn't work, use the original method
    related_obj = safe_get_related_object(instance, field_name)
    if related_obj is None:
        return None
    
    if attr_name is None:
        return related_obj
    
    return getattr(related_obj, attr_name, None)


def safe_get_related_attr_with_fallback(instance, field_name, attr_name=None, fallback_value=None):
    """
    Enhanced version of safe_get_related_attr that provides fallback handling.
    
    This function is especially useful for bulk operations where related objects
    might not be fully loaded or might not exist yet.
    
    Args:
        instance: The model instance
        field_name: The foreign key field name
        attr_name: Optional attribute name to access on the related object
        fallback_value: Value to return if the related object or attribute doesn't exist
    
    Returns:
        The related object, the attribute value, or fallback_value if not available
    """
    # First try the standard safe access
    result = safe_get_related_attr(instance, field_name, attr_name)
    if result is not None:
        return result
    
    # If that fails, try to get the foreign key ID and fetch the object directly
    fk_field_name = f"{field_name}_id"
    if hasattr(instance, fk_field_name):
        fk_id = getattr(instance, fk_field_name)
        if fk_id is not None:
            try:
                # Get the field to determine the related model
                field = instance._meta.get_field(field_name)
                if field.is_relation and not field.many_to_many and not field.one_to_many:
                    # Try to fetch the related object directly
                    related_obj = field.related_model.objects.get(pk=fk_id)
                    if attr_name is None:
                        return related_obj
                    return getattr(related_obj, attr_name, fallback_value)
            except (field.related_model.DoesNotExist, AttributeError):
                pass
    
    return fallback_value


def resolve_dotted_attr(instance, dotted_path):
    """
    Recursively resolve a dotted attribute path, e.g., "type.category".
    This function is designed to work with pre-loaded foreign keys to avoid queries.
    """
    if instance is None:
        return None
    
    current = instance
    for attr in dotted_path.split("."):
        if current is None:
            return None
        
        # Check if this is a foreign key that might trigger a query
        if hasattr(current, '_meta') and hasattr(current._meta, 'get_field'):
            try:
                field = current._meta.get_field(attr)
                if field.is_relation and not field.many_to_many and not field.one_to_many:
                    # For foreign keys, use safe access to prevent RelatedObjectDoesNotExist
                    current = safe_get_related_object(current, attr)
                else:
                    current = getattr(current, attr, None)
            except Exception:
                # If field lookup fails, fall back to regular attribute access
                current = getattr(current, attr, None)
        else:
            # Not a model instance, use regular attribute access
            current = getattr(current, attr, None)
    
    return current


class HookCondition:
    def check(self, instance, original_instance=None):
        raise NotImplementedError

    def __call__(self, instance, original_instance=None):
        return self.check(instance, original_instance)

    def __and__(self, other):
        return AndCondition(self, other)

    def __or__(self, other):
        return OrCondition(self, other)

    def __invert__(self):
        return NotCondition(self)

    def get_required_fields(self):
        """
        Returns a set of field names that this condition needs to evaluate.
        Override in subclasses to specify required fields.
        """
        return set()


class IsEqual(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current_value = resolve_dotted_attr(instance, self.field)
        return current_value == self.value

    def get_required_fields(self):
        return {self.field.split('.')[0]}


class IsNotEqual(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current_value = resolve_dotted_attr(instance, self.field)
        return current_value != self.value

    def get_required_fields(self):
        return {self.field.split('.')[0]}


class WasEqual(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        if original_instance is None:
            return False
        original_value = resolve_dotted_attr(original_instance, self.field)
        return original_value == self.value

    def get_required_fields(self):
        return {self.field.split('.')[0]}


class HasChanged(HookCondition):
    def __init__(self, field):
        self.field = field

    def check(self, instance, original_instance=None):
        if original_instance is None:
            return True
        current_value = resolve_dotted_attr(instance, self.field)
        original_value = resolve_dotted_attr(original_instance, self.field)
        return current_value != original_value

    def get_required_fields(self):
        return {self.field.split('.')[0]}


class ChangesTo(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        if original_instance is None:
            current_value = resolve_dotted_attr(instance, self.field)
            return current_value == self.value

        current_value = resolve_dotted_attr(instance, self.field)
        original_value = resolve_dotted_attr(original_instance, self.field)
        return current_value == self.value and current_value != original_value

    def get_required_fields(self):
        return {self.field.split('.')[0]}


class IsGreaterThan(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current > self.value


class IsGreaterThanOrEqual(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current >= self.value


class IsLessThan(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current < self.value


class IsLessThanOrEqual(HookCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current <= self.value


class AndCondition(HookCondition):
    def __init__(self, condition1, condition2):
        self.condition1 = condition1
        self.condition2 = condition2

    def check(self, instance, original_instance=None):
        return (
            self.condition1.check(instance, original_instance)
            and self.condition2.check(instance, original_instance)
        )

    def get_required_fields(self):
        return self.condition1.get_required_fields() | self.condition2.get_required_fields()


class OrCondition(HookCondition):
    def __init__(self, condition1, condition2):
        self.condition1 = condition1
        self.condition2 = condition2

    def check(self, instance, original_instance=None):
        return (
            self.condition1.check(instance, original_instance)
            or self.condition2.check(instance, original_instance)
        )

    def get_required_fields(self):
        return self.condition1.get_required_fields() | self.condition2.get_required_fields()


class NotCondition(HookCondition):
    def __init__(self, condition):
        self.condition = condition

    def check(self, instance, original_instance=None):
        return not self.condition.check(instance, original_instance)

    def get_required_fields(self):
        return self.condition.get_required_fields()
