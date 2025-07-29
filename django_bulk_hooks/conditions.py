def resolve_dotted_attr(instance, dotted_path):
    """
    Recursively resolve a dotted attribute path, e.g., "type.category".
    """
    for attr in dotted_path.split("."):
        if instance is None:
            return None
        instance = getattr(instance, attr, None)
    return instance


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


class IsNotEqual(HookCondition):
    def __init__(self, field, value, only_on_change=False):
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        if self.only_on_change:
            if original_instance is None:
                return False
            previous = resolve_dotted_attr(original_instance, self.field)
            return previous == self.value and current != self.value
        else:
            return current != self.value


class IsEqual(HookCondition):
    def __init__(self, field, value, only_on_change=False):
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        if self.only_on_change:
            if original_instance is None:
                return False
            previous = resolve_dotted_attr(original_instance, self.field)
            return previous != self.value and current == self.value
        else:
            return current == self.value


class HasChanged(HookCondition):
    def __init__(self, field, has_changed=True):
        self.field = field
        self.has_changed = has_changed

    def check(self, instance, original_instance=None):
        if not original_instance:
            return False
        current = resolve_dotted_attr(instance, self.field)
        previous = resolve_dotted_attr(original_instance, self.field)
        return (current != previous) == self.has_changed


class WasEqual(HookCondition):
    def __init__(self, field, value, only_on_change=False):
        """
        Check if a field's original value was `value`.
        If only_on_change is True, only return True when the field has changed away from that value.
        """
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance, original_instance=None):
        if original_instance is None:
            return False
        previous = resolve_dotted_attr(original_instance, self.field)
        if self.only_on_change:
            current = resolve_dotted_attr(instance, self.field)
            return previous == self.value and current != self.value
        else:
            return previous == self.value


class ChangesTo(HookCondition):
    def __init__(self, field, value):
        """
        Check if a field's value has changed to `value`.
        Only returns True when original value != value and current value == value.
        """
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        if original_instance is None:
            return False
        previous = resolve_dotted_attr(original_instance, self.field)
        current = resolve_dotted_attr(instance, self.field)
        return previous != self.value and current == self.value


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
    def __init__(self, cond1, cond2):
        self.cond1 = cond1
        self.cond2 = cond2

    def check(self, instance, original_instance=None):
        return self.cond1.check(instance, original_instance) and self.cond2.check(
            instance, original_instance
        )


class OrCondition(HookCondition):
    def __init__(self, cond1, cond2):
        self.cond1 = cond1
        self.cond2 = cond2

    def check(self, instance, original_instance=None):
        return self.cond1.check(instance, original_instance) or self.cond2.check(
            instance, original_instance
        )


class NotCondition(HookCondition):
    def __init__(self, cond):
        self.cond = cond

    def check(self, instance, original_instance=None):
        return not self.cond.check(instance, original_instance)
