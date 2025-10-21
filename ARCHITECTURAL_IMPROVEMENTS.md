# Architectural Improvements - Django Bulk Triggers

## Overview
This document outlines architectural and code quality improvements that can be made to the framework without adding new features. These improvements focus on separation of concerns (SOC), maintainability, and reducing complexity.

## Priority 1: Critical Architectural Issues

### 1. **Eliminate Dual Architecture - handler.py vs dispatcher.py**

**Problem**: Two parallel trigger execution systems exist:
- `handler.py` - Old architecture with `Trigger` class, `TriggerMeta` metaclass, and queue-based execution
- `dispatcher.py` - New architecture with `TriggerDispatcher` and clean execution flow
- `engine.py` - Deprecated but still present

**Impact**: 
- Confusion about which system to use
- Maintenance burden (two codebases doing the same thing)
- Potential bugs from inconsistent behavior
- Tests need to cover both paths

**Solution**:
```python
# Option A: Deprecate handler.py completely
# - Move TriggerMeta registration logic to registry.py
# - Keep @trigger decorator but register directly to dispatcher
# - Remove Trigger base class (users don't need it with dispatcher)

# Option B: Keep handler.py as a thin wrapper
# - Trigger class becomes a pure registration mechanism
# - Execution always goes through dispatcher
# - Remove all execution logic from handler.py
```

**Recommendation**: Option A - Complete removal. The dispatcher is cleaner and more maintainable.

**Files Affected**:
- `django_bulk_triggers/handler.py` - Remove or heavily simplify
- `django_bulk_triggers/engine.py` - Remove completely
- `django_bulk_triggers/decorators.py` - Update to register directly
- `django_bulk_triggers/__init__.py` - Update exports

### 2. **Convert Registry from Module-Level Functions to Class**

**Problem**: Registry uses module-level functions and global dict:
```python
_triggers: dict = {}

def register_trigger(...):
    ...

def get_triggers(...):
    ...
```

**Issues**:
- Hard to test (global state)
- No clear ownership
- Difficult to extend or customize
- Thread-safety concerns with global dict

**Solution**:
```python
class TriggerRegistry:
    """
    Central registry for all trigger handlers.
    
    Provides thread-safe registration and lookup of triggers.
    Single instance used throughout the framework (singleton).
    """
    
    def __init__(self):
        self._triggers: Dict[Tuple[Type, str], List[TriggerInfo]] = {}
        self._lock = threading.RLock()
    
    def register(self, model: Type, event: str, handler_cls: Type, 
                 method_name: str, condition: Optional[TriggerCondition],
                 priority: int) -> None:
        """Register a trigger handler."""
        with self._lock:
            key = (model, event)
            triggers = self._triggers.setdefault(key, [])
            # ... registration logic
    
    def get_triggers(self, model: Type, event: str) -> List[TriggerInfo]:
        """Get all triggers for a model and event."""
        with self._lock:
            return self._triggers.get((model, event), [])
    
    def unregister(self, model: Type, event: str, 
                   handler_cls: Type, method_name: str) -> None:
        """Unregister a specific trigger."""
        # ... unregistration logic
    
    def clear(self) -> None:
        """Clear all registered triggers (useful for testing)."""
        with self._lock:
            self._triggers.clear()
    
    def list_all(self) -> Dict:
        """Get all registered triggers for debugging."""
        with self._lock:
            return dict(self._triggers)

# Singleton instance
_registry = TriggerRegistry()

def get_registry() -> TriggerRegistry:
    """Get the global registry instance."""
    return _registry
```

**Benefits**:
- Clear ownership and lifecycle
- Easier to test (can create test instances)
- Better thread-safety
- Can be extended or customized
- Type hints improve IDE support

**Files Affected**:
- `django_bulk_triggers/registry.py` - Rewrite as class
- `django_bulk_triggers/dispatcher.py` - Update to use registry instance
- `django_bulk_triggers/handler.py` - Update to use registry instance

### 3. **Extract RecursionGuard to Separate Module**

**Problem**: `RecursionGuard` is embedded in `dispatcher.py` but is a self-contained concern.

**Current**:
```python
# In dispatcher.py
class RecursionGuard:
    # 100+ lines of recursion detection logic
    ...

class TriggerDispatcher:
    def __init__(self, registry):
        self.guard = RecursionGuard()
    ...
```

**Solution**:
```python
# django_bulk_triggers/recursion.py
class RecursionGuard:
    """
    Thread-safe recursion detection for trigger execution.
    
    Prevents infinite loops by tracking call stacks and depth limits.
    Similar to Salesforce's trigger recursion protection.
    """
    # ... existing logic, cleaned up

# dispatcher.py
from django_bulk_triggers.recursion import RecursionGuard

class TriggerDispatcher:
    def __init__(self, registry, recursion_guard=None):
        self.guard = recursion_guard or RecursionGuard()
```

**Benefits**:
- Better SOC (separate concern from dispatcher)
- Easier to test recursion logic in isolation
- Can inject custom guards for testing
- Smaller, more focused files

**Files Affected**:
- `django_bulk_triggers/recursion.py` - NEW, extract guard
- `django_bulk_triggers/dispatcher.py` - Import and use guard

## Priority 2: Code Quality Improvements

### 4. **Simplify Conditions Module with Base Factory Pattern**

**Problem**: Conditions have repetitive structure and excessive debug logging:
- Every condition class has similar `__init__`, `check`, etc.
- Debug logging clutters the code (80+ lines of logging in ~280 line file)
- `resolve_dotted_attr` has N+1 prevention logic mixed with resolution

**Solution**:
```python
# Clean separation of concerns

# django_bulk_triggers/conditions/base.py
class TriggerCondition:
    """Base class for all trigger conditions."""
    
    def check(self, instance, original_instance=None) -> bool:
        """Check if condition is satisfied."""
        raise NotImplementedError
    
    def __and__(self, other):
        return AndCondition(self, other)
    
    def __or__(self, other):
        return OrCondition(self, other)
    
    def __invert__(self):
        return NotCondition(self)

# django_bulk_triggers/conditions/field_resolver.py
class FieldResolver:
    """
    Resolves dotted field paths efficiently without N+1 queries.
    
    Uses attname for FK fields to avoid descriptor protocol.
    """
    
    @staticmethod
    def resolve(instance, dotted_path: str):
        """Resolve dotted attribute path."""
        # Clean implementation without debug logging
        # FK optimization logic
        ...

# django_bulk_triggers/conditions/comparisons.py
class ComparisonCondition(TriggerCondition):
    """Base class for comparison conditions."""
    
    def __init__(self, field: str, value: Any, only_on_change: bool = False):
        self.field = field
        self.value = value
        self.only_on_change = only_on_change
        self.resolver = FieldResolver()
    
    def _get_current_value(self, instance):
        return self.resolver.resolve(instance, self.field)
    
    def _compare(self, current, target):
        """Override in subclass."""
        raise NotImplementedError
    
    def check(self, instance, original_instance=None) -> bool:
        current = self._get_current_value(instance)
        
        if self.only_on_change:
            if original_instance is None:
                return False
            previous = self._get_current_value(original_instance)
            return self._check_change(previous, current)
        
        return self._compare(current, self.value)

class IsEqual(ComparisonCondition):
    def _compare(self, current, target):
        return current == target
    
    def _check_change(self, previous, current):
        return previous != self.value and current == self.value

class IsNotEqual(ComparisonCondition):
    def _compare(self, current, target):
        return current != target
    
    def _check_change(self, previous, current):
        return previous == self.value and current != self.value

# ... other conditions follow same pattern
```

**Benefits**:
- Eliminate 80% of code duplication
- Remove clutter from debug logging
- Clearer intent (comparison vs change detection)
- Easier to add new conditions
- Better testability

**Files Affected**:
- `django_bulk_triggers/conditions.py` - Split into multiple files
- `django_bulk_triggers/conditions/__init__.py` - NEW, exports
- `django_bulk_triggers/conditions/base.py` - NEW, base classes
- `django_bulk_triggers/conditions/field_resolver.py` - NEW, resolver
- `django_bulk_triggers/conditions/comparisons.py` - NEW, comparisons
- `django_bulk_triggers/conditions/change_tracking.py` - NEW, HasChanged, etc.
- `django_bulk_triggers/conditions/logical.py` - NEW, And/Or/Not

### 5. **Simplify Factory Module**

**Problem**: Factory is overly complex with multiple resolution strategies:
- Specific factories
- Container resolver
- Default factory
- Nested container resolver
- Thread-safety adds complexity

**Current Complexity**:
- 387 lines
- 4 resolution strategies
- Thread-local storage
- Complex container navigation

**Solution**:
```python
# Simplified factory with clear priority

class TriggerFactory:
    """
    Creates trigger handler instances with dependency injection.
    
    Resolution order:
    1. Specific factory for trigger class
    2. Container resolver (if configured)
    3. Direct instantiation
    """
    
    def __init__(self):
        self._specific_factories: Dict[Type, Callable] = {}
        self._container_resolver: Optional[Callable] = None
        self._lock = threading.RLock()
    
    def register_factory(self, trigger_cls: Type, factory: Callable) -> None:
        """Register a factory for a specific trigger class."""
        with self._lock:
            self._specific_factories[trigger_cls] = factory
    
    def configure_container(self, container: Any, 
                          name_resolver: Optional[Callable] = None) -> None:
        """Configure DI container for trigger resolution."""
        def resolver(trigger_cls: Type) -> Any:
            name = name_resolver(trigger_cls) if name_resolver else self._default_name(trigger_cls)
            if hasattr(container, name):
                return getattr(container, name)()
            return trigger_cls()  # Fallback to direct instantiation
        
        with self._lock:
            self._container_resolver = resolver
    
    def create(self, trigger_cls: Type) -> Any:
        """Create trigger instance using configured strategy."""
        with self._lock:
            # 1. Specific factory
            if trigger_cls in self._specific_factories:
                return self._specific_factories[trigger_cls]()
            
            # 2. Container resolver
            if self._container_resolver:
                return self._container_resolver(trigger_cls)
            
            # 3. Direct instantiation
            return trigger_cls()
    
    def clear(self) -> None:
        """Clear all configurations (for testing)."""
        with self._lock:
            self._specific_factories.clear()
            self._container_resolver = None
    
    @staticmethod
    def _default_name(trigger_cls: Type) -> str:
        """Convert TriggerClassName to trigger_class_name."""
        import re
        name = trigger_cls.__name__
        return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

# Global factory instance
_factory = TriggerFactory()

def get_factory() -> TriggerFactory:
    """Get the global factory instance."""
    return _factory

# Backward-compatible functions
def set_trigger_factory(trigger_cls: Type, factory: Callable) -> None:
    _factory.register_factory(trigger_cls, factory)

def configure_trigger_container(container: Any, **kwargs) -> None:
    _factory.configure_container(container, **kwargs)

def create_trigger_instance(trigger_cls: Type) -> Any:
    return _factory.create(trigger_cls)
```

**Benefits**:
- Reduce from 387 lines to ~150 lines
- Remove nested container complexity
- Clearer resolution priority
- Same functionality, simpler code
- Still thread-safe

**Files Affected**:
- `django_bulk_triggers/factory.py` - Simplify significantly

### 6. **Remove Excessive Debug Logging**

**Problem**: Debug logging clutters the code, especially in:
- `conditions.py` - 80+ lines of debug logging
- `dispatcher.py` - Excessive logging in hot paths
- `handler.py` - Queue processing logs

**Solution**:
- Remove conditional debug logging that checks specific field names
- Keep only essential logs (errors, warnings, critical state changes)
- Use structured logging where needed
- Move verbose debugging to a separate debug utility

**Example**:
```python
# BEFORE (conditions.py)
if '.' in self.field or any(field in self.field for field in ['user', 'account', ...]):
    logger.debug(f"N+1 DEBUG: IsEqual.check called for field '{self.field}' ...")

# AFTER
# Remove completely - this is noise in production
# If needed for debugging, use a separate debug mode flag
```

**Files Affected**:
- `django_bulk_triggers/conditions.py` - Remove ~80 lines of debug logging
- `django_bulk_triggers/dispatcher.py` - Simplify logging
- `django_bulk_triggers/handler.py` - Remove queue processing logs

### 7. **Add Comprehensive Type Hints**

**Problem**: Type hints are inconsistent across the codebase.

**Solution**: Add type hints to all public methods and key internal methods:

```python
from typing import List, Optional, Type, Dict, Any, Callable

class TriggerDispatcher:
    def __init__(self, registry: TriggerRegistry) -> None:
        ...
    
    def dispatch(self, 
                changeset: ChangeSet, 
                event: str, 
                bypass_triggers: bool = False) -> None:
        ...
    
    def _execute_trigger(self,
                        handler_cls: Type,
                        method_name: str,
                        condition: Optional[TriggerCondition],
                        changeset: ChangeSet) -> None:
        ...
```

**Benefits**:
- Better IDE support
- Catch bugs earlier
- Self-documenting code
- Easier refactoring

**Files Affected**: All Python files

## Priority 3: Structural Improvements

### 8. **Organize Enums and Constants Better**

**Problem**: 
- `constants.py` only has event strings and one batch size
- `enums.py` only has Priority enum
- No validation that event strings match enum values

**Solution**:
```python
# django_bulk_triggers/enums.py
from enum import IntEnum, Enum

class Priority(IntEnum):
    """Trigger execution priority."""
    HIGHEST = 0
    HIGH = 25
    NORMAL = 50
    LOW = 75
    LOWEST = 100

DEFAULT_PRIORITY = Priority.NORMAL

class TriggerEvent(str, Enum):
    """All trigger events."""
    VALIDATE_CREATE = "validate_create"
    VALIDATE_UPDATE = "validate_update"
    VALIDATE_DELETE = "validate_delete"
    BEFORE_CREATE = "before_create"
    BEFORE_UPDATE = "before_update"
    BEFORE_DELETE = "before_delete"
    AFTER_CREATE = "after_create"
    AFTER_UPDATE = "after_update"
    AFTER_DELETE = "after_delete"
    
    @classmethod
    def is_before(cls, event: str) -> bool:
        return event.startswith("before_")
    
    @classmethod
    def is_after(cls, event: str) -> bool:
        return event.startswith("after_")
    
    @classmethod
    def is_validate(cls, event: str) -> bool:
        return event.startswith("validate_")
    
    @classmethod
    def get_operation(cls, event: str) -> str:
        """Extract operation from event (create/update/delete)."""
        for op in ["create", "update", "delete"]:
            if op in event:
                return op
        return "unknown"

class OperationType(str, Enum):
    """Operation types."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

# django_bulk_triggers/constants.py
from django_bulk_triggers.enums import TriggerEvent

# Export event strings for backward compatibility
BEFORE_CREATE = TriggerEvent.BEFORE_CREATE.value
AFTER_CREATE = TriggerEvent.AFTER_CREATE.value
BEFORE_UPDATE = TriggerEvent.BEFORE_UPDATE.value
AFTER_UPDATE = TriggerEvent.AFTER_UPDATE.value
BEFORE_DELETE = TriggerEvent.BEFORE_DELETE.value
AFTER_DELETE = TriggerEvent.AFTER_DELETE.value
VALIDATE_CREATE = TriggerEvent.VALIDATE_CREATE.value
VALIDATE_UPDATE = TriggerEvent.VALIDATE_UPDATE.value
VALIDATE_DELETE = TriggerEvent.VALIDATE_DELETE.value

DEFAULT_BULK_UPDATE_BATCH_SIZE = 1000
```

**Benefits**:
- Type-safe event handling
- Utility methods for event checking
- Single source of truth
- Better validation

**Files Affected**:
- `django_bulk_triggers/enums.py` - Add TriggerEvent enum
- `django_bulk_triggers/constants.py` - Export from enums

### 9. **Extract Common Validation Logic**

**Problem**: Validation logic is scattered:
- `ModelAnalyzer` has type/PK checking
- `BulkExecutor` repeats validation calls
- `BulkOperationCoordinator` calls validation

**Solution**:
```python
# django_bulk_triggers/validation.py
class OperationValidator:
    """
    Validates operations before execution.
    
    Single responsibility: Ensure operations have valid inputs.
    """
    
    def __init__(self, model_cls: Type):
        self.model_cls = model_cls
    
    def validate_create(self, objs: List) -> None:
        """Validate bulk_create input."""
        self._check_not_empty(objs, "bulk_create")
        self._check_types(objs, "bulk_create")
    
    def validate_update(self, objs: List) -> None:
        """Validate bulk_update input."""
        self._check_not_empty(objs, "bulk_update")
        self._check_types(objs, "bulk_update")
        self._check_has_pks(objs, "bulk_update")
    
    def validate_delete(self, objs: List) -> None:
        """Validate delete input."""
        self._check_not_empty(objs, "delete")
        self._check_types(objs, "delete")
    
    def _check_not_empty(self, objs: List, operation: str) -> None:
        if not objs:
            raise ValueError(f"{operation} requires at least one object")
    
    def _check_types(self, objs: List, operation: str) -> None:
        invalid = {type(obj).__name__ for obj in objs if not isinstance(obj, self.model_cls)}
        if invalid:
            raise TypeError(
                f"{operation} expected {self.model_cls.__name__} instances, "
                f"got {invalid}"
            )
    
    def _check_has_pks(self, objs: List, operation: str) -> None:
        missing_pks = sum(1 for obj in objs if obj.pk is None)
        if missing_pks:
            raise ValueError(
                f"{operation} requires saved instances. "
                f"{missing_pks} object(s) have no primary key."
            )
```

**Benefits**:
- Single place for validation logic
- Consistent error messages
- Easier to test
- `ModelAnalyzer` can focus on analysis, not validation

**Files Affected**:
- `django_bulk_triggers/validation.py` - NEW
- `django_bulk_triggers/operations/analyzer.py` - Remove validation, keep analysis
- `django_bulk_triggers/operations/bulk_executor.py` - Use validator

### 10. **Fix models.py to Use New Dispatcher Architecture**

**Problem**: `models.py` still uses deprecated `engine.run()` in the `clean()` method:

```python
# models.py line 40
from django_bulk_triggers.engine import run
...
run(self.__class__, VALIDATE_CREATE, [self], ctx=ctx)
```

This bypasses the new dispatcher architecture completely!

**Solution**:
```python
# models.py (updated)
from django_bulk_triggers.helpers import (
    build_changeset_for_create,
    build_changeset_for_update,
)
from django_bulk_triggers.dispatcher import get_dispatcher

class TriggerModelMixin(models.Model):
    objects = BulkTriggerManager()

    class Meta:
        abstract = True

    def clean(self, bypass_triggers=False):
        """Override clean() to trigger validation triggers."""
        super().clean()

        if bypass_triggers:
            return

        dispatcher = get_dispatcher()
        is_create = self.pk is None

        if is_create:
            changeset = build_changeset_for_create(self.__class__, [self])
            dispatcher.dispatch(changeset, 'validate_create', bypass_triggers=False)
        else:
            # For update validation, we don't need old records
            # Validation triggers should handle field checks themselves
            changeset = build_changeset_for_update(self.__class__, [self], {})
            dispatcher.dispatch(changeset, 'validate_update', bypass_triggers=False)
```

**Files Affected**:
- `django_bulk_triggers/models.py` - Update to use dispatcher
- Remove dependency on deprecated `engine.py`

### 11. **Refactor context.py or Remove It**

**Problem**: `context.py` serves two purposes:
1. Old trigger queue system (used by deprecated handler.py)
2. Thread-local state for bulk_update value maps and bypass flags

**Current Usage**:
- `TriggerContext` class - Used in models.py (but models.py should be refactored)
- `trigger_vars` - Used only by handler.py (old architecture)
- Bulk update helpers - Used by queryset operations
- `get_bypass_triggers()`/`set_bypass_triggers()` - Used in tests

**Solution Option A - Split into separate modules**:
```python
# django_bulk_triggers/thread_local_state.py
"""Thread-local state management for bulk operations."""
import threading

_state = threading.local()

def set_bypass_triggers(bypass: bool) -> None:
    _state.bypass_triggers = bypass

def get_bypass_triggers() -> bool:
    return getattr(_state, "bypass_triggers", False)

def set_bulk_update_value_map(value_map: dict) -> None:
    _state.bulk_update_value_map = value_map

def get_bulk_update_value_map() -> dict:
    return getattr(_state, "bulk_update_value_map", None)

# ... other bulk_update helpers
```

**Solution Option B - Remove completely**:
- If dispatcher metadata can replace this, remove context.py
- Move bypass flags to operation kwargs (already supported)
- Move bulk_update value maps to operation metadata

**Recommendation**: Option A - Keep thread-local helpers for bulk_update, remove old trigger queue system.

**Files Affected**:
- `django_bulk_triggers/context.py` - Refactor or remove
- `django_bulk_triggers/thread_local_state.py` - NEW (if Option A)
- `django_bulk_triggers/models.py` - Remove TriggerContext usage
- Tests - Update imports

## Implementation Priority

### Phase 1 (Week 1): Critical Architecture
1. Registry class conversion
2. Extract RecursionGuard
3. Deprecate/remove handler.py

### Phase 2 (Week 2): Code Quality  
4. Simplify conditions module
5. Simplify factory module
6. Remove excessive logging

### Phase 3 (Week 3): Polish
7. Add type hints throughout
8. Organize enums/constants
9. Extract validation logic
10. Review and remove unused code

## Testing Strategy

For each change:
1. Run existing test suite (should pass)
2. Add tests for new classes/modules
3. Verify no performance regression
4. Update documentation

## Expected Benefits

### Code Metrics:
- **Lines of Code**: Reduce by ~20-25%
- **Cyclomatic Complexity**: Reduce average by ~30%
- **Files**: Increase slightly (better organization)
- **Test Coverage**: Maintain >95%

### Maintainability:
- **Clearer responsibilities**: Each class has one job
- **Less duplication**: DRY principle applied
- **Better testability**: Easier to test in isolation
- **Easier onboarding**: Clearer structure for new contributors

### Performance:
- **No regression**: Changes are structural, not algorithmic
- **Same query counts**: No change to database operations
- **Potential improvements**: Simpler code may optimize better

## Notes

1. **Backward Compatibility**: All changes maintain the public API
2. **Incremental**: Can be done in phases
3. **Low Risk**: Structural changes with high test coverage
4. **High Value**: Significant improvement in maintainability

## Questions to Consider

1. Is `context.py` still used? If not, remove it.
2. Should we keep `engine.py` for backward compatibility or remove it?
3. Do we want to keep `handler.py` as a thin wrapper or remove completely?
4. Should we add a deprecation period for any removed functionality?

