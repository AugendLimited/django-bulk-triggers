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


def is_field_set(instance, field_name):
    """
    Check if a field has been set on a model instance.
    
    This is useful for checking if a field has been explicitly set,
    even if it's been set to None.
    """
    return hasattr(instance, field_name)


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


class IsBlank(HookCondition):
    """
    Condition that checks if a field is blank (None or empty string).
    """
    def __init__(self, field_name):
        self.field_name = field_name

    def check(self, instance, original_instance=None):
        value = getattr(instance, self.field_name, None)
        return value is None or value == ""

    def get_required_fields(self):
        return {self.field_name}


class AndCondition(HookCondition):
    def __init__(self, *conditions):
        self.conditions = conditions

    def check(self, instance, original_instance=None):
        return all(c.check(instance, original_instance) for c in self.conditions)

    def get_required_fields(self):
        fields = set()
        for condition in self.conditions:
            fields.update(condition.get_required_fields())
        return fields


class OrCondition(HookCondition):
    def __init__(self, *conditions):
        self.conditions = conditions

    def check(self, instance, original_instance=None):
        return any(c.check(instance, original_instance) for c in self.conditions)

    def get_required_fields(self):
        fields = set()
        for condition in self.conditions:
            fields.update(condition.get_required_fields())
        return fields


class NotCondition(HookCondition):
    def __init__(self, condition):
        self.condition = condition

    def check(self, instance, original_instance=None):
        return not self.condition.check(instance, original_instance)

    def get_required_fields(self):
        return self.condition.get_required_fields()


class IsEqual(HookCondition):
    def __init__(self, field_name, value):
        self.field_name = field_name
        self.value = value

    def check(self, instance, original_instance=None):
        return getattr(instance, self.field_name, None) == self.value

    def get_required_fields(self):
        return {self.field_name}


class WasEqual(HookCondition):
    def __init__(self, field_name, value):
        self.field_name = field_name
        self.value = value

    def check(self, instance, original_instance=None):
        if original_instance is None:
            return False
        return getattr(original_instance, self.field_name, None) == self.value

    def get_required_fields(self):
        return {self.field_name}


class HasChanged(HookCondition):
    def __init__(self, field_name):
        self.field_name = field_name

    def check(self, instance, original_instance=None):
        if original_instance is None:
            return True
        return getattr(instance, self.field_name, None) != getattr(original_instance, self.field_name, None)

    def get_required_fields(self):
        return {self.field_name}


class ChangesTo(HookCondition):
    def __init__(self, field_name, value):
        self.field_name = field_name
        self.value = value

    def check(self, instance, original_instance=None):
        if original_instance is None:
            return getattr(instance, self.field_name, None) == self.value
        return (
            getattr(instance, self.field_name, None) == self.value
            and getattr(instance, self.field_name, None) != getattr(original_instance, self.field_name, None)
        )

    def get_required_fields(self):
        return {self.field_name}


class IsNotEqual(HookCondition):
    def __init__(self, field_name, value):
        self.field_name = field_name
        self.value = value

    def check(self, instance, original_instance=None):
        return getattr(instance, self.field_name, None) != self.value

    def get_required_fields(self):
        return {self.field_name}
