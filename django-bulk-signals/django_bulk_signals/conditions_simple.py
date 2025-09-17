"""
Simple trigger conditions for bulk operations.

These conditions have ZERO dependencies on services, executors, or configuration.
They are pure functions that check instance state.
"""

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TriggerCondition:
    """
    Base class for trigger conditions.

    This has ZERO dependencies on other components.
    It only knows about instance comparison logic.
    """

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the condition is met for the given instance."""
        raise NotImplementedError

    def __call__(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Allow conditions to be called directly."""
        return self.check(instance, original_instance)


class HasChanged(TriggerCondition):
    """Check if a field has changed between OLD and NEW values."""

    def __init__(self, field: str, has_changed: bool = True):
        self.field = field
        self.has_changed = has_changed

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field has changed."""
        if not original_instance:
            return False

        if not hasattr(instance, self.field) or not hasattr(
            original_instance, self.field
        ):
            return False

        current_value = getattr(instance, self.field, None)
        previous_value = getattr(original_instance, self.field, None)

        return (current_value != previous_value) == self.has_changed


class IsEqual(TriggerCondition):
    """Check if a field equals a specific value."""

    def __init__(self, field: str, value: Any, only_on_change: bool = False):
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field equals the specified value."""
        if not hasattr(instance, self.field):
            return False

        current_value = getattr(instance, self.field, None)

        if self.only_on_change:
            if not original_instance or not hasattr(original_instance, self.field):
                return False
            previous_value = getattr(original_instance, self.field, None)
            return previous_value != self.value and current_value == self.value
        else:
            return current_value == self.value


class IsNotEqual(TriggerCondition):
    """Check if a field does not equal a specific value."""

    def __init__(self, field: str, value: Any, only_on_change: bool = False):
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field does not equal the specified value."""
        if not hasattr(instance, self.field):
            return False

        current_value = getattr(instance, self.field, None)

        if self.only_on_change:
            if not original_instance or not hasattr(original_instance, self.field):
                return False
            previous_value = getattr(original_instance, self.field, None)
            return previous_value == self.value and current_value != self.value
        else:
            return current_value != self.value


class ChangesTo(TriggerCondition):
    """Check if a field's value has changed to a specific value."""

    def __init__(self, field: str, value: Any):
        self.field = field
        self.value = value

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check if the field has changed to the specified value."""
        if not original_instance:
            return False

        if not hasattr(instance, self.field) or not hasattr(
            original_instance, self.field
        ):
            return False

        current_value = getattr(instance, self.field, None)
        previous_value = getattr(original_instance, self.field, None)

        return previous_value != self.value and current_value == self.value


class CustomCondition(TriggerCondition):
    """Custom condition using a callable function."""

    def __init__(self, func: Callable[[Any, Optional[Any]], bool]):
        self.func = func

    def check(self, instance: Any, original_instance: Optional[Any] = None) -> bool:
        """Check the custom condition."""
        return self.func(instance, original_instance)


# Convenience functions
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
