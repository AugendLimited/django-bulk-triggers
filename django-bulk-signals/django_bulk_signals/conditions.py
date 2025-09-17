"""
Trigger conditions for bulk operations.

This module provides utility classes for common trigger conditions,
similar to Salesforce's trigger conditions.
"""

import logging
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


class TriggerCondition:
    """
    Base class for trigger conditions.

    Conditions determine whether a trigger should fire for a specific instance
    in a bulk operation, similar to Salesforce trigger conditions.
    """

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """
        Check if the condition is met for the given instance.

        Args:
            instance: The current instance (NEW values)
            original_instance: The original instance (OLD values), if available

        Returns:
            True if the condition is met, False otherwise
        """
        raise NotImplementedError

    def __call__(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Allow conditions to be called directly."""
        return self.check(instance, original_instance)


class HasChanged(TriggerCondition):
    """
    Check if a field has changed between OLD and NEW values.

    Similar to Salesforce's Trigger.oldMap and Trigger.newMap comparison.
    """

    def __init__(self, field: str, has_changed: bool = True):
        """
        Initialize the condition.

        Args:
            field: The field name to check
            has_changed: If True, returns True when field has changed.
                        If False, returns True when field has not changed.
        """
        self.field = field
        self.has_changed = has_changed

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field has changed."""
        if not original_instance:
            return False

        current_value = getattr(instance, self.field, None)
        previous_value = getattr(original_instance, self.field, None)

        result = (current_value != previous_value) == self.has_changed

        if result:
            logger.debug(
                f"HasChanged({self.field}): {previous_value} -> {current_value}"
            )

        return result


class IsEqual(TriggerCondition):
    """
    Check if a field equals a specific value.

    Similar to Salesforce's field comparison conditions.
    """

    def __init__(self, field: str, value: Any, only_on_change: bool = False):
        """
        Initialize the condition.

        Args:
            field: The field name to check
            value: The value to compare against
            only_on_change: If True, only returns True when the field changes to this value
        """
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field equals the specified value."""
        current_value = getattr(instance, self.field, None)

        if self.only_on_change:
            if not original_instance:
                return False
            previous_value = getattr(original_instance, self.field, None)
            return previous_value != self.value and current_value == self.value
        else:
            return current_value == self.value


class IsNotEqual(TriggerCondition):
    """
    Check if a field does not equal a specific value.
    """

    def __init__(self, field: str, value: Any, only_on_change: bool = False):
        """
        Initialize the condition.

        Args:
            field: The field name to check
            value: The value to compare against
            only_on_change: If True, only returns True when the field changes away from this value
        """
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field does not equal the specified value."""
        current_value = getattr(instance, self.field, None)

        if self.only_on_change:
            if not original_instance:
                return False
            previous_value = getattr(original_instance, self.field, None)
            return previous_value == self.value and current_value != self.value
        else:
            return current_value != self.value


class WasEqual(TriggerCondition):
    """
    Check if a field's original value was equal to a specific value.
    """

    def __init__(self, field: str, value: Any, only_on_change: bool = False):
        """
        Initialize the condition.

        Args:
            field: The field name to check
            value: The value to compare against
            only_on_change: If True, only returns True when the field has changed away from this value
        """
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field's original value was equal to the specified value."""
        if not original_instance:
            return False

        previous_value = getattr(original_instance, self.field, None)

        if self.only_on_change:
            current_value = getattr(instance, self.field, None)
            return previous_value == self.value and current_value != self.value
        else:
            return previous_value == self.value


class ChangesTo(TriggerCondition):
    """
    Check if a field's value has changed to a specific value.
    """

    def __init__(self, field: str, value: Any):
        """
        Initialize the condition.

        Args:
            field: The field name to check
            value: The value the field should change to
        """
        self.field = field
        self.value = value

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field has changed to the specified value."""
        if not original_instance:
            return False

        current_value = getattr(instance, self.field, None)
        previous_value = getattr(original_instance, self.field, None)

        return previous_value != self.value and current_value == self.value


class CustomCondition(TriggerCondition):
    """
    Custom condition using a callable function.

    Allows for complex custom logic in trigger conditions.
    """

    def __init__(self, func: Callable[[Any, Optional[Any]], bool]):
        """
        Initialize the condition.

        Args:
            func: A callable that takes (instance, original_instance) and returns bool
        """
        self.func = func

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check the custom condition."""
        return self.func(instance, original_instance)


# Utility functions for common conditions
def has_changed(field: str) -> HasChanged:
    """Convenience function for HasChanged condition."""
    return HasChanged(field, has_changed=True)


def has_not_changed(field: str) -> HasChanged:
    """Convenience function for HasChanged condition (inverted)."""
    return HasChanged(field, has_changed=False)


def is_equal(field: str, value: Any) -> IsEqual:
    """Convenience function for IsEqual condition."""
    return IsEqual(field, value)


def is_not_equal(field: str, value: Any) -> IsNotEqual:
    """Convenience function for IsNotEqual condition."""
    return IsNotEqual(field, value)


def changes_to(field: str, value: Any) -> ChangesTo:
    """Convenience function for ChangesTo condition."""
    return ChangesTo(field, value)
