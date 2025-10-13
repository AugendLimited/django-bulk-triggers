import logging

logger = logging.getLogger(__name__)


def resolve_dotted_attr(instance, dotted_path):
    """
    Recursively resolve a dotted attribute path, e.g., "type.category".
    """
    # Only log for foreign key relationships to avoid too much noise
    if '.' in dotted_path or any(field in dotted_path for field in ['user', 'account', 'currency', 'setting', 'business']):
        logger.debug(f"N+1 DEBUG: resolve_dotted_attr called with path '{dotted_path}' on instance {getattr(instance, 'pk', 'No PK')}")
    
    current_instance = instance
    for i, attr in enumerate(dotted_path.split(".")):
        if current_instance is None:
            if '.' in dotted_path or any(field in dotted_path for field in ['user', 'account', 'currency', 'setting', 'business']):
                logger.debug(f"N+1 DEBUG: resolve_dotted_attr - instance is None at step {i}, returning None")
            return None
        
        # Only log for foreign key relationships to avoid too much noise
        if '.' in dotted_path or any(field in dotted_path for field in ['user', 'account', 'currency', 'setting', 'business']):
            logger.debug(f"N+1 DEBUG: resolve_dotted_attr - accessing attr '{attr}' on {type(current_instance).__name__} (pk={getattr(current_instance, 'pk', 'No PK')})")
        
        try:
            current_instance = getattr(current_instance, attr, None)
            if '.' in dotted_path or any(field in dotted_path for field in ['user', 'account', 'currency', 'setting', 'business']):
                logger.debug(f"N+1 DEBUG: resolve_dotted_attr - got value {current_instance} (type: {type(current_instance).__name__})")
        except Exception as e:
            if '.' in dotted_path or any(field in dotted_path for field in ['user', 'account', 'currency', 'setting', 'business']):
                logger.debug(f"N+1 DEBUG: resolve_dotted_attr - exception accessing '{attr}': {e}")
            current_instance = None
    
    if '.' in dotted_path or any(field in dotted_path for field in ['user', 'account', 'currency', 'setting', 'business']):
        logger.debug(f"N+1 DEBUG: resolve_dotted_attr - final result: {current_instance}")
    return current_instance


class TriggerCondition:
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


class IsNotEqual(TriggerCondition):
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


class IsEqual(TriggerCondition):
    def __init__(self, field, value, only_on_change=False):
        self.field = field
        self.value = value
        self.only_on_change = only_on_change

    def check(self, instance, original_instance=None):
        # Only log for foreign key relationships to avoid too much noise
        if '.' in self.field or any(field in self.field for field in ['user', 'account', 'currency', 'setting', 'business']):
            logger.debug(f"N+1 DEBUG: IsEqual.check called for field '{self.field}' with value {self.value} on instance {getattr(instance, 'pk', 'No PK')}")
        
        current = resolve_dotted_attr(instance, self.field)
        
        if '.' in self.field or any(field in self.field for field in ['user', 'account', 'currency', 'setting', 'business']):
            logger.debug(f"N+1 DEBUG: IsEqual.check - resolved current value: {current}")
        
        if self.only_on_change:
            if original_instance is None:
                if '.' in self.field or any(field in self.field for field in ['user', 'account', 'currency', 'setting', 'business']):
                    logger.debug(f"N+1 DEBUG: IsEqual.check - only_on_change=True but no original_instance, returning False")
                return False
            previous = resolve_dotted_attr(original_instance, self.field)
            result = previous != self.value and current == self.value
            if '.' in self.field or any(field in self.field for field in ['user', 'account', 'currency', 'setting', 'business']):
                logger.debug(f"N+1 DEBUG: IsEqual.check - only_on_change result: {result} (previous={previous}, current={current}, target={self.value})")
            return result
        else:
            result = current == self.value
            if '.' in self.field or any(field in self.field for field in ['user', 'account', 'currency', 'setting', 'business']):
                logger.debug(f"N+1 DEBUG: IsEqual.check - simple comparison result: {result} (current={current}, target={self.value})")
            return result


class HasChanged(TriggerCondition):
    def __init__(self, field, has_changed=True):
        self.field = field
        self.has_changed = has_changed

    def check(self, instance, original_instance=None):
        if not original_instance:
            return False

        current = resolve_dotted_attr(instance, self.field)
        previous = resolve_dotted_attr(original_instance, self.field)

        result = (current != previous) == self.has_changed
        
        # Only log when there's an actual change to reduce noise
        if result:
            logger.debug(
                f"HasChanged {self.field} detected change on instance {getattr(instance, 'pk', 'No PK')}"
            )
        return result


class WasEqual(TriggerCondition):
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


class ChangesTo(TriggerCondition):
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


class IsGreaterThan(TriggerCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current > self.value


class IsGreaterThanOrEqual(TriggerCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current >= self.value


class IsLessThan(TriggerCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current < self.value


class IsLessThanOrEqual(TriggerCondition):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def check(self, instance, original_instance=None):
        current = resolve_dotted_attr(instance, self.field)
        return current is not None and current <= self.value


class AndCondition(TriggerCondition):
    def __init__(self, cond1, cond2):
        self.cond1 = cond1
        self.cond2 = cond2

    def check(self, instance, original_instance=None):
        return self.cond1.check(instance, original_instance) and self.cond2.check(
            instance, original_instance
        )


class OrCondition(TriggerCondition):
    def __init__(self, cond1, cond2):
        self.cond1 = cond1
        self.cond2 = cond2

    def check(self, instance, original_instance=None):
        return self.cond1.check(instance, original_instance) or self.cond2.check(
            instance, original_instance
        )


class NotCondition(TriggerCondition):
    def __init__(self, cond):
        self.cond = cond

    def check(self, instance, original_instance=None):
        return not self.cond.check(instance, original_instance)
