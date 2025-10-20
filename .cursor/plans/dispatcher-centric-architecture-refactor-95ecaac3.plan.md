<!-- 95ecaac3-180c-4140-a064-c12a4a59e492 3915f1a3-98a6-4bc1-a765-20dfe524183d -->
# Dispatcher-Centric Architecture Refactor

## Overview

Refactor the architecture to promote **Dispatcher** as the single execution path, demote Django signals to a thin compatibility edge, and elevate **ChangeSet** as a first-class data structure. This ensures deterministic ordering, fail-fast error propagation, and eliminates dual execution models.

## Target Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Hook Layer (User API)                     │
│  @trigger decorator │ Trigger classes │ Conditions          │
└────────────▲─────────────────────────────────────────────────┘
             │ registers / resolves (priority, on_commit, DI)
┌────────────┴─────────────────────────────────────────────────┐
│                 Dispatcher (Single Path)                     │
│  HookRegistry │ HookDispatcher │ ReentrancyGuard │ on_commit │
└────────────▲─────────────────────────────────────────────────┘
             │ invokes
┌────────────┴─────────────────────────────────────────────────┐
│     QuerySet & Manager Layer (entrypoint for ops)            │
│  TriggerQuerySet │ BulkTriggerManager │ Mixin                │
│  - builds ChangeSet once                                      │
│  - chunked dispatch for large batches                          │
│  - MTI routing & field-split                                   │
└────────────▲─────────────────────────────────────────────────┘
             │ fetches / computes
┌────────────┴─────────────────────────────────────────────────┐
│                Data Access & Analysis                         │
│  RecordFetcher │ FieldTracker │ MTIHandler │ QueryOptimizer   │
│  ChangeSet (RecordChange)                                      │
└────────────▲─────────────────────────────────────────────────┘
             │ executes DB calls
┌────────────┴─────────────────────────────────────────────────┐
│                Django ORM (unmodified)                        │
└───────────────────────────────────────────────────────────────┘

(Thin edge:)  Django Signals ↔ single receiver that forwards into Dispatcher
```

## Implementation Steps

### 1. Create ChangeSet Data Structures

**New file: `django_bulk_triggers/changeset.py`**

Create first-class ChangeSet and RecordChange classes with ergonomic O(1) helpers:

```python
class RecordChange:
    """Represents a single record change with old/new state."""
    
    def __init__(self, new_record, old_record=None, changed_fields=None):
        self.new_record = new_record
        self.old_record = old_record
        self._changed_fields = changed_fields
        self._pk = getattr(new_record, 'pk', None)
    
    @property
    def pk(self):
        """Primary key of the record."""
        return self._pk
    
    @property
    def changed_fields(self):
        """Lazy compute changed fields if not provided."""
        if self._changed_fields is None:
            self._changed_fields = self._compute_changed_fields()
        return self._changed_fields
    
    def _compute_changed_fields(self):
        """Compute changed fields using proper field comparison."""
        # Use existing field comparison logic from field_operations.py
        if self.old_record is None:
            return set()
        
        changed = set()
        model_cls = self.new_record.__class__
        for field in model_cls._meta.fields:
            if field.primary_key:
                continue
            
            old_val = getattr(self.old_record, field.name, None)
            new_val = getattr(self.new_record, field.name, None)
            
            # Use field's get_prep_value for proper comparison
            try:
                old_prep = field.get_prep_value(old_val)
                new_prep = field.get_prep_value(new_val)
                if old_prep != new_prep:
                    changed.add(field.name)
            except Exception:
                # Fallback to direct comparison
                if old_val != new_val:
                    changed.add(field.name)
        
        return changed
    
    def has_changed(self, field_name):
        """O(1) check if a field has changed."""
        return field_name in self.changed_fields
    
    def get_old_value(self, field_name):
        """Get old value for a field."""
        if self.old_record is None:
            return None
        return getattr(self.old_record, field_name, None)
    
    def get_new_value(self, field_name):
        """Get new value for a field."""
        return getattr(self.new_record, field_name, None)

class ChangeSet:
    """Collection of RecordChanges for a bulk operation."""
    
    def __init__(self, model_cls, changes, operation_type, operation_meta=None):
        self.model_cls = model_cls
        self.changes = changes  # List[RecordChange]
        self.operation_type = operation_type  # 'create', 'update', 'delete'
        self.operation_meta = operation_meta or {}
        self._pk_to_change = {c.pk: c for c in changes if c.pk is not None}
    
    @property
    def new_records(self):
        return [c.new_record for c in self.changes]
    
    @property
    def old_records(self):
        return [c.old_record for c in self.changes]
    
    def has_field_changed(self, pk, field_name):
        """O(1) check if a field changed for a specific PK."""
        change = self._pk_to_change.get(pk)
        return change.has_changed(field_name) if change else False
    
    def get_old_value(self, pk, field_name):
        """Get old value for a specific PK and field."""
        change = self._pk_to_change.get(pk)
        return change.get_old_value(field_name) if change else None
    
    def get_new_value(self, pk, field_name):
        """Get new value for a specific PK and field."""
        change = self._pk_to_change.get(pk)
        return change.get_new_value(field_name) if change else None
    
    def chunk(self, chunk_size):
        """Split ChangeSet into smaller chunks for memory-efficient processing."""
        for i in range(0, len(self.changes), chunk_size):
            chunk_changes = self.changes[i:i + chunk_size]
            yield ChangeSet(
                self.model_cls,
                chunk_changes,
                self.operation_type,
                self.operation_meta
            )
```

### 2. Create Dispatcher Layer

**New file: `django_bulk_triggers/dispatcher.py`**

The single source of truth for hook execution with production-grade fixes:

```python
import threading
import logging
from typing import List, Tuple, Any

logger = logging.getLogger(__name__)

class ReentrancyGuard:
    """
    Thread-safe reentrancy detection with cycle detection across events/models.
    
    Tracks a per-thread call stack to detect cycles (A:AFTER→B:BEFORE→A:AFTER loops)
    and enforces depth thresholds per (model, event) pair.
    """
    
    _thread_local = threading.local()
    MAX_DEPTH_PER_EVENT = 10  # Configurable depth threshold
    
    @classmethod
    def enter(cls, model_cls, event):
        """Track entering a dispatch context with cycle detection."""
        if not hasattr(cls._thread_local, 'stack'):
            cls._thread_local.stack = []
        if not hasattr(cls._thread_local, 'depth'):
            cls._thread_local.depth = {}
        
        key = (model_cls, event)
        
        # Check for cycles in the call stack
        if key in cls._thread_local.stack:
            cycle_path = ' → '.join(
                f"{m.__name__}:{e}" for m, e in cls._thread_local.stack
            )
            cycle_path += f" → {model_cls.__name__}:{event}"
            raise RuntimeError(
                f"Reentrancy cycle detected: {cycle_path}. "
                f"This indicates an infinite loop in your trigger chain."
            )
        
        # Check depth threshold
        cls._thread_local.depth[key] = cls._thread_local.depth.get(key, 0) + 1
        depth = cls._thread_local.depth[key]
        
        if depth > cls.MAX_DEPTH_PER_EVENT:
            raise RuntimeError(
                f"Maximum trigger depth ({cls.MAX_DEPTH_PER_EVENT}) exceeded "
                f"for {model_cls.__name__}.{event}. "
                f"This likely indicates an infinite recursion in your triggers."
            )
        
        # Add to call stack
        cls._thread_local.stack.append(key)
        
        return depth
    
    @classmethod
    def exit(cls, model_cls, event):
        """Track exiting a dispatch context."""
        key = (model_cls, event)
        
        # Remove from call stack
        if hasattr(cls._thread_local, 'stack') and cls._thread_local.stack:
            if cls._thread_local.stack[-1] == key:
                cls._thread_local.stack.pop()
        
        # Decrement depth
        if hasattr(cls._thread_local, 'depth') and key in cls._thread_local.depth:
            cls._thread_local.depth[key] -= 1
    
    @classmethod
    def get_current_depth(cls, model_cls, event):
        """Get current depth for a (model, event) pair."""
        if not hasattr(cls._thread_local, 'depth'):
            return 0
        key = (model_cls, event)
        return cls._thread_local.depth.get(key, 0)
    
    @classmethod
    def get_call_stack(cls):
        """Get current call stack for debugging."""
        if not hasattr(cls._thread_local, 'stack'):
            return []
        return list(cls._thread_local.stack)

class HookDispatcher:
    """Single source of truth for hook execution."""
    
    def __init__(self, registry):
        self.registry = registry
        self.guard = ReentrancyGuard()
    
    def dispatch(self, changeset, event, bypass_triggers=False, on_commit=False):
        """
        Dispatch hooks for a changeset with deterministic ordering.
        
        - Single execution path
        - Priority-ordered hook execution (with stable secondary sort)
        - Fail-fast error propagation
        - Cycle detection across events/models
        - Optional on_commit deferral with safe closure capture
        """
        if bypass_triggers:
            return
        
        # Get hooks sorted by priority (with stable secondary ordering)
        hooks = self.registry.get_hooks(changeset.model_cls, event)
        
        if not hooks:
            return
        
        # Track reentrancy depth and expose to handlers
        depth = self.guard.enter(changeset.model_cls, event)
        call_stack = self.guard.get_call_stack()
        
        # Augment operation_meta with reentrancy information
        changeset.operation_meta['reentrancy_depth'] = depth
        changeset.operation_meta['call_stack'] = call_stack
        
        try:
            # Execute hooks
            executor = self._execute_on_commit if on_commit else self._execute_immediately
            executor(hooks, changeset, event)
        finally:
            self.guard.exit(changeset.model_cls, event)
    
    def _execute_immediately(self, hooks, changeset, event):
        """Execute hooks immediately in current transaction."""
        for handler_cls, method_name, condition, priority, on_commit_flag in hooks:
            # Respect per-hook on_commit flag
            if on_commit_flag:
                self._defer_hook(handler_cls, method_name, condition, changeset)
            else:
                self._execute_hook(handler_cls, method_name, condition, changeset)
    
    def _execute_on_commit(self, hooks, changeset, event):
        """Defer ALL hook execution until transaction commit."""
        # FIX: Defensive copy - snapshot the changeset to prevent mutation
        changeset_snapshot = self._snapshot_changeset(changeset)
        
        for handler_cls, method_name, condition, priority, _ in hooks:
            # FIX: Bind loop variables as defaults to avoid closure capture bug
            self._defer_hook(
                handler_cls, method_name, condition, changeset_snapshot
            )
    
    def _defer_hook(self, handler_cls, method_name, condition, changeset):
        """Defer a single hook to on_commit with proper closure binding."""
        from django.db import transaction
        
        # FIX: Bind all loop variables as defaults to avoid late-binding closure bug
        transaction.on_commit(
            lambda h=handler_cls, m=method_name, c=condition, cs=changeset: 
                self._execute_hook(h, m, c, cs)
        )
    
    def _execute_hook(self, handler_cls, method_name, condition, changeset):
        """Execute a single hook with condition checking."""
        # Filter records based on condition
        if condition:
            filtered_changes = [
                change for change in changeset.changes
                if condition.check(change.new_record, change.old_record)
            ]
            if not filtered_changes:
                return
            
            # Create filtered changeset
            from django_bulk_triggers.changeset import ChangeSet
            filtered_changeset = ChangeSet(
                changeset.model_cls,
                filtered_changes,
                changeset.operation_type,
                changeset.operation_meta
            )
        else:
            filtered_changeset = changeset
        
        # Use DI factory to create handler instance
        from django_bulk_triggers.factory import create_trigger_instance
        handler = create_trigger_instance(handler_cls)
        method = getattr(handler, method_name)
        
        # Execute hook with ChangeSet
        try:
            method(
                changeset=filtered_changeset,
                new_records=filtered_changeset.new_records,
                old_records=filtered_changeset.old_records,
            )
        except Exception as e:
            # Fail-fast: re-raise to rollback transaction
            logger.error(
                f"Hook {handler_cls.__name__}.{method_name} failed: {e}",
                exc_info=True
            )
            raise
    
    def _snapshot_changeset(self, changeset):
        """
        Create an immutable snapshot of a ChangeSet for deferred execution.
        
        This prevents mutations to the original changeset from affecting
        deferred hooks.
        """
        from django_bulk_triggers.changeset import ChangeSet, RecordChange
        
        # Create deep copies of RecordChanges
        snapshot_changes = [
            RecordChange(
                new_record=change.new_record,
                old_record=change.old_record,
                changed_fields=set(change.changed_fields) if change._changed_fields else None
            )
            for change in changeset.changes
        ]
        
        # Copy operation_meta
        snapshot_meta = dict(changeset.operation_meta)
        
        return ChangeSet(
            changeset.model_cls,
            snapshot_changes,
            changeset.operation_type,
            snapshot_meta
        )

# Global dispatcher instance
_dispatcher = None

def get_dispatcher():
    """Get the global dispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        from django_bulk_triggers.registry import HookRegistry
        _dispatcher = HookDispatcher(HookRegistry())
    return _dispatcher
```

### 3. Refactor Registry to HookRegistry

**Update `django_bulk_triggers/registry.py`:**

Rename and enhance to be dispatcher-focused:

```python
class HookRegistry:
    """Registry for lifecycle hooks."""
    
    def __init__(self):
        self._hooks = {}  # (model, event) -> [(handler_cls, method_name, condition, priority)]
    
    def register_hook(self, model, event, handler_cls, method_name, condition, priority):
        """Register a hook with priority ordering."""
        key = (model, event)
        hooks = self._hooks.setdefault(key, [])
        
        hook_info = (handler_cls, method_name, condition, priority)
        if hook_info not in hooks:
            hooks.append(hook_info)
            # Sort by priority (lower values first)
            hooks.sort(key=lambda x: x[3])
    
    def get_hooks(self, model, event):
        """Get hooks for a model and event, sorted by priority."""
        return self._hooks.get((model, event), [])
    
    def unregister_hook(self, model, event, handler_cls, method_name):
        """Unregister a specific hook."""
        key = (model, event)
        if key not in self._hooks:
            return
        
        self._hooks[key] = [
            h for h in self._hooks[key]
            if not (h[0] == handler_cls and h[1] == method_name)
        ]
    
    def clear(self):
        """Clear all hooks."""
        self._hooks.clear()

# Maintain backward compatibility
_registry = HookRegistry()

def register_trigger(model, event, handler_cls, method_name, condition, priority):
    _registry.register_hook(model, event, handler_cls, method_name, condition, priority)

def get_triggers(model, event):
    return _registry.get_hooks(model, event)

def unregister_trigger(model, event, handler_cls, method_name):
    _registry.unregister_hook(model, event, handler_cls, method_name)

def clear_triggers():
    _registry.clear()
```

### 4. Refactor QuerySet to Build ChangeSet Once

**Update `django_bulk_triggers/queryset.py`:**

Key changes:

- Build ChangeSet once per operation
- Pass ChangeSet through to dispatcher
- Use sorted PK order when lock_records=True
- Ensure update() uses optimized/locked queryset
```python
class TriggerQuerySetMixin:
    
    @transaction.atomic
    def update(self, **kwargs):
        """Update QuerySet with ChangeSet built once."""
        
        # Apply select_related for FK fields
        fk_fields = self._get_fk_fields()
        queryset = self.select_related(*fk_fields) if fk_fields else self
        
        # Get instances with sorted PK order for deadlock prevention
        instances = list(queryset.order_by('pk'))
        if not instances:
            return 0
        
        # Build ChangeSet ONCE
        changeset = self._build_changeset_for_update(instances, kwargs)
        
        # Check bypass
        from django_bulk_triggers.context import get_bypass_triggers
        bypass = get_bypass_triggers()
        
        if not bypass:
            # Dispatch VALIDATE_UPDATE
            from django_bulk_triggers.dispatcher import get_dispatcher
            from django_bulk_triggers.constants import VALIDATE_UPDATE, BEFORE_UPDATE
            
            dispatcher = get_dispatcher()
            dispatcher.dispatch(changeset, VALIDATE_UPDATE, bypass_triggers=bypass)
            
            # Dispatch BEFORE_UPDATE
            dispatcher.dispatch(changeset, BEFORE_UPDATE, bypass_triggers=bypass)
        
        # Execute the actual update on the OPTIMIZED QUERYSET
        # NOT on self (which may not have select_related applied)
        update_count = queryset.update(**kwargs)
        
        # Handle Subquery refresh if needed
        if self._has_subquery(kwargs):
            self._refresh_and_dispatch_for_subquery(changeset, kwargs)
        elif not bypass:
            # Dispatch AFTER_UPDATE
            from django_bulk_triggers.constants import AFTER_UPDATE
            dispatcher.dispatch(changeset, AFTER_UPDATE, bypass_triggers=bypass)
        
        return update_count
    
    def _build_changeset_for_update(self, instances, update_kwargs):
        """Build ChangeSet once with all change information."""
        model_cls = self.model
        pks = [obj.pk for obj in instances]
        
        # Fetch originals
        original_map = {
            obj.pk: obj for obj in model_cls._base_manager.filter(pk__in=pks)
        }
        originals = [original_map.get(obj.pk) for obj in instances]
        
        # Build RecordChanges
        changes = []
        for new, old in zip(instances, originals):
            # Compute changed fields once
            changed_fields = list(update_kwargs.keys())
            change = RecordChange(new, old, changed_fields)
            changes.append(change)
        
        # Build ChangeSet
        from django_bulk_triggers.changeset import ChangeSet
        return ChangeSet(
            model_cls=model_cls,
            changes=changes,
            operation_type='update',
            operation_meta={'update_kwargs': update_kwargs}
        )
```


### 5. Create Signals Compatibility Layer

**New file: `django_bulk_triggers/signals_compat.py`**

Thin wrapper that forwards Django signals to dispatcher:

```python
"""
Thin compatibility layer for Django signals.

This module provides Django signal definitions that forward to the
dispatcher. This ensures backward compatibility while making the
dispatcher the single source of truth.
"""

from django.dispatch import Signal

# Define Django signals for compatibility
bulk_pre_create = Signal()
bulk_post_create = Signal()
bulk_pre_update = Signal()
bulk_post_update = Signal()
bulk_pre_delete = Signal()
bulk_post_delete = Signal()

def _setup_signal_forwarding():
    """
    Set up signal receivers that forward to the dispatcher.
    
    This is called once during module initialization to ensure
    all signal receivers are registered.
    """
    from django.dispatch import receiver
    from django_bulk_triggers.dispatcher import get_dispatcher
    from django_bulk_triggers.changeset import ChangeSet, RecordChange
    
    @receiver(bulk_pre_create)
    def forward_pre_create_to_dispatcher(sender, new_records, **kwargs):
        """Forward bulk_pre_create signal to dispatcher."""
        changes = [RecordChange(rec) for rec in new_records]
        changeset = ChangeSet(sender, changes, 'create', kwargs)
        dispatcher = get_dispatcher()
        dispatcher.dispatch(changeset, 'before_create')
    
    # Similar for other signals...

# Initialize signal forwarding
_setup_signal_forwarding()
```

### 6. Update Conditions to Use ChangeSet

**Update `django_bulk_triggers/conditions.py`:**

Make conditions use RecordChange for O(1) field checks:

```python
class HasChanged:
    """Condition that checks if a field has changed."""
    
    def __init__(self, field_name):
        self.field_name = field_name
    
    def check(self, new_record, old_record):
        """Check using RecordChange if available, fallback to comparison."""
        # O(1) check if new_record is a RecordChange
        if hasattr(new_record, 'has_changed'):
            return new_record.has_changed(self.field_name)
        
        # Fallback to direct comparison
        if old_record is None:
            return False
        
        old_value = getattr(old_record, self.field_name, None)
        new_value = getattr(new_record, self.field_name, None)
        return old_value != new_value
```

### 7. Update Handler to Use Dispatcher

**Update `django_bulk_triggers/handler.py`:**

Make Trigger class delegate to dispatcher instead of having its own execution logic:

```python
class Trigger(metaclass=TriggerMeta):
    @classmethod
    def handle(cls, event, model, *, new_records=None, old_records=None, **kwargs):
        """
        Handle trigger execution by delegating to the dispatcher.
        
        This is the backward-compatibility entry point.
        """
        from django_bulk_triggers.dispatcher import get_dispatcher
        from django_bulk_triggers.changeset import ChangeSet, RecordChange
        
        # Build ChangeSet
        changes = [
            RecordChange(new, old) 
            for new, old in zip(new_records, old_records or [None] * len(new_records))
        ]
        changeset = ChangeSet(model, changes, _infer_operation_type(event), kwargs)
        
        # Delegate to dispatcher
        dispatcher = get_dispatcher()
        dispatcher.dispatch(changeset, event, bypass_triggers=kwargs.get('bypass_triggers', False))
```

### 8. Deprecate engine.py

**Mark `django_bulk_triggers/engine.py` as deprecated:**

Add deprecation notice and redirect to dispatcher:

```python
"""
DEPRECATED: This module is deprecated in favor of dispatcher.py.

The dispatcher is now the single source of truth for hook execution.
This module is kept for backward compatibility only.
"""

import warnings

def run(model_cls, event, new_records, old_records=None, ctx=None):
    """
    DEPRECATED: Use dispatcher.get_dispatcher().dispatch() instead.
    """
    warnings.warn(
        "engine.run() is deprecated. Use dispatcher.get_dispatcher().dispatch() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    from django_bulk_triggers.dispatcher import get_dispatcher
    from django_bulk_triggers.changeset import ChangeSet, RecordChange
    
    # Build ChangeSet
    changes = [
        RecordChange(new, old) 
        for new, old in zip(new_records, old_records or [None] * len(new_records))
    ]
    changeset = ChangeSet(model_cls, changes, _infer_operation_type(event), {})
    
    # Delegate to dispatcher
    dispatcher = get_dispatcher()
    bypass = ctx.bypass_triggers if ctx and hasattr(ctx, 'bypass_triggers') else False
    dispatcher.dispatch(changeset, event, bypass_triggers=bypass)
```

### 9. Add on_commit Support

**Update dispatcher to support on_commit as a hook decorator option:**

```python
# In decorators.py
def trigger(event, *, model, condition=None, priority=DEFAULT_PRIORITY, on_commit=False):
    """
    Decorator to register a trigger.
    
    Args:
        on_commit: If True, defer execution until transaction commit
    """
    def decorator(fn):
        if not hasattr(fn, "triggers_triggers"):
            fn.triggers_triggers = []
        # Store on_commit flag in trigger metadata
        fn.triggers_triggers.append((model, event, condition, priority, on_commit))
        return fn
    return decorator
```

### 10. Update Documentation

**Update `README.md` and create `ARCHITECTURE.md`:**

Document the new architecture with:

- Dispatcher as single source of truth
- ChangeSet usage
- Cross-cutting concerns (DI, on_commit, observability)
- Migration guide from old architecture
- Signals compatibility layer

## Key Benefits

1. **Single execution path**: Dispatcher is the ONLY runner; signals just forward
2. **ChangeSet built once**: Passed to every hook/condition (O(1) field checks)
3. **Deterministic ordering**: Priority ordering enforced in one place
4. **Fail-fast**: Clear error propagation with transaction rollback
5. **Reentrancy detection**: ReentrancyGuard prevents infinite loops
6. **on_commit support**: Optional deferral of side-effects
7. **Testability**: Clear boundaries make mocking and testing easier
8. **Performance**: Zero re-diff in hooks, chunked dispatch for memory safety

## Testing Strategy

1. Update all existing tests to use new ChangeSet API
2. Add tests for ReentrancyGuard
3. Add tests for on_commit functionality
4. Add tests for signals compatibility layer
5. Add performance benchmarks for ChangeSet caching
6. Add integration tests for full dispatcher flow

## Backward Compatibility

- Keep `engine.run()` with deprecation warning
- Keep existing signal definitions
- Keep existing `@trigger` decorator syntax (extend with on_commit)
- Keep existing `Trigger` class (delegate to dispatcher)
- Provide migration guide for users

### To-dos

- [ ] Create changeset.py with ChangeSet and RecordChange classes for first-class change tracking
- [ ] Create dispatcher.py with TriggerDispatcher, ReentrancyGuard, and single execution path
- [ ] Refactor registry.py to TriggerRegistry focused on dispatcher
- [ ] Update queryset.py to build ChangeSet once and use dispatcher
- [ ] Create signals_compat.py as thin compatibility layer forwarding to dispatcher
- [ ] Update conditions.py to use RecordChange for O(1) field checks
- [ ] Update handler.py Trigger class to delegate to dispatcher
- [ ] Mark engine.py as deprecated and redirect to dispatcher
- [ ] Add on_commit support to decorators and dispatcher
- [ ] Update README.md and create ARCHITECTURE.md documenting new design
- [ ] Update all tests to use new ChangeSet API and test new components