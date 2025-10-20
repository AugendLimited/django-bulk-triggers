<!-- 50f55cb2-c969-4c89-a486-b9f00fc26561 51c47a77-5616-4ee7-aebb-4209a3487488 -->
# 🚀 django-bulk-lifecycle V2 - Implementation Plan

## 📋 Project Overview

**Package Name**: `django-bulk-lifecycle`

**Goal**: Create a clean, performant, and maintainable framework that provides reliable lifecycle hooks for all Django ORM operations, including bulk methods and Multi-Table Inheritance (MTI).

**Core Principle**: Single Responsibility - The framework provides signals and hooks, business logic stays in hook handlers.

**Inspiration**: Combines the declarative hook pattern from [django-lifecycle](https://github.com/rsinger86/django-lifecycle) with bulk operation support and MTI cascading.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Hook Layer (User API)                      │
├─────────────────────────────────────────────────────────────┤
│  @hook Decorator │ LifecycleHook Class │ Hook Registry      │
├─────────────────────────────────────────────────────────────┤
│                  Signal Layer (Core)                        │
├─────────────────────────────────────────────────────────────┤
│  bulk_pre_create │ bulk_post_update │ bulk_pre_delete      │
├─────────────────────────────────────────────────────────────┤
│              QuerySet & Manager Layer                       │
├─────────────────────────────────────────────────────────────┤
│  BulkLifecycleQuerySet │ BulkLifecycleManager │ Mixins     │
├─────────────────────────────────────────────────────────────┤
│                Data Access Layer                            │
├─────────────────────────────────────────────────────────────┤
│  RecordFetcher │ FieldTracker │ MTIHandler │ QueryOptimizer │
├─────────────────────────────────────────────────────────────┤
│                Django ORM (Unmodified)                      │
└─────────────────────────────────────────────────────────────┘
```

## 📁 Module Structure

```
django_bulk_lifecycle/
├── __init__.py                 # Public API exports
├── signals.py                  # Django Signal definitions
├── hooks.py                    # @hook decorator and LifecycleHook base class
├── constants.py                # Event constants (BEFORE_CREATE, AFTER_UPDATE, etc.)
├── conditions.py               # Hook conditions (WhenFieldHasChanged, etc.)
├── mixins.py                   # BulkLifecycleModelMixin
├── managers.py                 # BulkLifecycleManager
├── querysets.py                # BulkLifecycleQuerySet
├── data_access/                # Data access layer
│   ├── __init__.py
│   ├── record_fetcher.py       # RecordFetcher
│   ├── field_tracker.py        # FieldTracker
│   ├── mti_handler.py          # MTIHandler (MTI detection & cascading)
│   └── query_optimizer.py      # QueryOptimizer
├── utils/                      # Utility functions
│   ├── __init__.py
│   ├── warnings.py             # Performance warnings
│   └── helpers.py              # Helper functions
└── exceptions.py               # Custom exceptions
```

## 🎯 Core Interfaces

### 1. Signal Interface (Core Layer)

```python
# signals.py
from django.dispatch import Signal

# Lifecycle signals (6 total - clean and simple)
bulk_pre_create = Signal()
bulk_post_create = Signal()
bulk_pre_update = Signal()
bulk_post_update = Signal()
bulk_pre_delete = Signal()
bulk_post_delete = Signal()

# Signal payload structure (consistent across all):
# sender: Model class
# new_records: List[Model instances] (actual child instances in MTI)
# old_records: List[Model instances] (actual child instances in MTI)
# update_fields: List[str] | None
# operation_meta: Dict with additional context

# NOTE: Validation is handled in BEFORE hooks, not separate signals.
# This keeps the API simple and aligns with django-lifecycle patterns.
```

### 2. Constants Interface

```python
# constants.py
# Lifecycle event constants
BEFORE_CREATE = "before_create"
AFTER_CREATE = "after_create"
BEFORE_UPDATE = "before_update"
AFTER_UPDATE = "after_update"
BEFORE_DELETE = "before_delete"
AFTER_DELETE = "after_delete"

# Map events to signals
EVENT_TO_SIGNAL = {
    BEFORE_CREATE: bulk_pre_create,
    AFTER_CREATE: bulk_post_create,
    BEFORE_UPDATE: bulk_pre_update,
    AFTER_UPDATE: bulk_post_update,
    BEFORE_DELETE: bulk_pre_delete,
    AFTER_DELETE: bulk_post_delete,
}
```

### 3. Hook Interface (User-Facing API)

```python
# hooks.py
from django.dispatch import receiver

def hook(event, model=None, condition=None):
    """
    Decorator that registers a hook for a lifecycle event.
    Hooks are wrappers around Django signal receivers.
    
    Example:
        @hook(AFTER_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
        def audit_balance_change(self, new_records, old_records, **kwargs):
            for new, old in zip(new_records, old_records):
                log_change(old.balance, new.balance)
    """
    def decorator(func):
        signal = EVENT_TO_SIGNAL.get(event)
        if not signal:
            raise ValueError(f"Unknown event: {event}")
        
        # Register as Django signal receiver
        @receiver(signal, sender=model)
        def wrapper(sender, new_records, old_records, **kwargs):
            # Evaluate condition if provided
            if condition and not condition.evaluate(new_records, old_records):
                return
            
            # Call the hook function
            return func(new_records, old_records, **kwargs)
        
        wrapper._hook_event = event
        wrapper._hook_model = model
        wrapper._hook_condition = condition
        return wrapper
    
    return decorator


class LifecycleHook:
    """
    Base class for organizing hooks (similar to Salesforce trigger handlers).
    
    Example:
        class AccountHooks(LifecycleHook):
            @hook(AFTER_UPDATE, model=Account)
            def audit_changes(self, new_records, old_records):
                # Hook logic here
                pass
    """
    pass
```

### 4. Conditions Interface

```python
# conditions.py
from abc import ABC, abstractmethod

class HookCondition(ABC):
    """Base class for hook conditions."""
    
    @abstractmethod
    def evaluate(self, new_records, old_records):
        """Return True if condition is met."""
        pass


class WhenFieldHasChanged(HookCondition):
    """Condition: Field value has changed."""
    
    def __init__(self, field_name, has_changed=True):
        self.field_name = field_name
        self.has_changed = has_changed
    
    def evaluate(self, new_records, old_records):
        if not old_records:
            return not self.has_changed  # No old records = no change
        
        for new, old in zip(new_records, old_records):
            new_val = getattr(new, self.field_name, None)
            old_val = getattr(old, self.field_name, None)
            if (new_val != old_val) == self.has_changed:
                return True
        return False


class WhenFieldValueIs(HookCondition):
    """Condition: Field value equals a specific value."""
    
    def __init__(self, field_name, value):
        self.field_name = field_name
        self.value = value
    
    def evaluate(self, new_records, old_records):
        for record in new_records:
            if getattr(record, self.field_name, None) == self.value:
                return True
        return False


class WhenFieldValueWas(HookCondition):
    """Condition: Field value was a specific value (old records)."""
    
    def __init__(self, field_name, value):
        self.field_name = field_name
        self.value = value
    
    def evaluate(self, new_records, old_records):
        if not old_records:
            return False
        for record in old_records:
            if getattr(record, self.field_name, None) == self.value:
                return True
        return False
```

### 5. Model Mixin Interface

```python
# mixins.py
from django.db import models

class BulkLifecycleModelMixin(models.Model):
    """Clean, simple mixin that adds lifecycle hook support to models."""
    
    objects = BulkLifecycleManager()
    
    class Meta:
        abstract = True
    
    def save(self, update_fields=None, bypass_hooks=False, *args, **kwargs):
        """Override save to fire lifecycle hooks."""
        if bypass_hooks:
            return super().save(update_fields=update_fields, *args, **kwargs)
        
        is_create = self.pk is None
        
        if is_create:
            # CREATE operation
            self._fire_hooks_for_inheritance_chain(BEFORE_CREATE, new_records=[self])
            result = super().save(update_fields=update_fields, *args, **kwargs)
            self._fire_hooks_for_inheritance_chain(AFTER_CREATE, new_records=[self])
        else:
            # UPDATE operation
            old_instance = self._fetch_old_instance()
            
            # Auto-detect changed fields if not provided
            if update_fields is None:
                update_fields = self._get_changed_fields(old_instance)
            
            self._fire_hooks_for_inheritance_chain(
                BEFORE_UPDATE, 
                new_records=[self], 
                old_records=[old_instance],
                update_fields=update_fields
            )
            result = super().save(update_fields=update_fields, *args, **kwargs)
            self._fire_hooks_for_inheritance_chain(
                AFTER_UPDATE, 
                new_records=[self], 
                old_records=[old_instance],
                update_fields=update_fields
            )
        
        return result
    
    def delete(self, bypass_hooks=False, *args, **kwargs):
        """Override delete to fire lifecycle hooks."""
        if not bypass_hooks:
            self._fire_hooks_for_inheritance_chain(
                BEFORE_DELETE, 
                new_records=[], 
                old_records=[self]
            )
        
        result = super().delete(*args, **kwargs)
        
        if not bypass_hooks:
            self._fire_hooks_for_inheritance_chain(
                AFTER_DELETE, 
                new_records=[], 
                old_records=[self]
            )
        
        return result
    
    def _fire_hooks_for_inheritance_chain(self, event, new_records, old_records=None, **kwargs):
        """
        Fire hooks for all models in the MTI inheritance chain.
        Parent hooks fire first, then child hooks (polymorphic behavior).
        """
        inheritance_chain = self._get_inheritance_chain()
        signal = EVENT_TO_SIGNAL[event]
        
        for model_class in inheritance_chain:
            signal.send(
                sender=model_class,
                new_records=new_records,  # Always the actual child instances
                old_records=old_records or [],
                **kwargs
            )
    
    def _get_inheritance_chain(self):
        """Get inheritance chain from root parent to current model."""
        from django_bulk_lifecycle.data_access.mti_handler import MTIHandler
        handler = MTIHandler(self.__class__)
        return handler.get_inheritance_chain()
    
    def _fetch_old_instance(self):
        """Fetch the old instance from database for comparison."""
        if self.pk is None:
            return None
        return self.__class__._base_manager.get(pk=self.pk)
    
    def _get_changed_fields(self, old_instance):
        """Get list of changed fields."""
        from django_bulk_lifecycle.data_access.field_tracker import FieldTracker
        tracker = FieldTracker(self, old_instance)
        return tracker.get_changed_fields()
```

### 6. Manager Interface

```python
# managers.py
class BulkLifecycleManager(models.Manager):
    """Manager that provides lifecycle hook support for bulk operations."""
    
    def get_queryset(self):
        """Return queryset with lifecycle hook support."""
        return BulkLifecycleQuerySet(self.model, using=self._db)
    
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, 
                   update_conflicts=False, update_fields=None, unique_fields=None,
                   bypass_hooks=False, **kwargs):
        """Bulk create with lifecycle hooks."""
        return self.get_queryset().bulk_create(
            objs, 
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            bypass_hooks=bypass_hooks,
            **kwargs
        )
    
    def bulk_update(self, objs, fields=None, batch_size=None, bypass_hooks=False, **kwargs):
        """Bulk update with lifecycle hooks."""
        return self.get_queryset().bulk_update(
            objs, 
            fields=fields,
            batch_size=batch_size,
            bypass_hooks=bypass_hooks,
            **kwargs
        )
```

### 7. QuerySet Interface

```python
# querysets.py
from django.db import transaction

class BulkLifecycleQuerySet(models.QuerySet):
    """QuerySet with lifecycle hook support for bulk operations."""
    
    @transaction.atomic
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                   update_conflicts=False, update_fields=None, unique_fields=None,
                   bypass_hooks=False, **kwargs):
        """Override bulk_create with hook support and MTI handling."""
        if bypass_hooks:
            return super().bulk_create(objs, batch_size=batch_size, **kwargs)
        
        # Check if MTI model
        if self._is_mti_model():
            return self._mti_bulk_create(objs, **kwargs)
        
        # Standard bulk create with hooks (wrapped in transaction)
        try:
            self._fire_hooks_for_chain(BEFORE_CREATE, new_records=objs)
            result = super().bulk_create(objs, batch_size=batch_size, **kwargs)
            self._fire_hooks_for_chain(AFTER_CREATE, new_records=objs)
            return result
        except Exception as e:
            # Transaction will auto-rollback, re-raise for caller
            logger.error(f"Hook or create failed: {e}")
            raise
    
    @transaction.atomic
    def bulk_update(self, objs, fields=None, batch_size=None, bypass_hooks=False, 
                   lock_records=False, **kwargs):
        """
        Override bulk_update with hook support and MTI handling.
        
        Args:
            objs: Model instances to update
            fields: List of field names to update (auto-detected if None)
            batch_size: Number of objects to update per query
            bypass_hooks: Skip firing lifecycle hooks if True
            lock_records: Use select_for_update() for pessimistic locking
                         Default False (optimistic, better concurrency)
        """
        if not objs:
            return 0
            
        if bypass_hooks:
            return super().bulk_update(objs, fields=fields, batch_size=batch_size, **kwargs)
        
        try:
            # Step 1: Fetch old records FIRST (single query with optional locking)
            old_records_map = self._fetch_old_records_map(objs, lock_records=lock_records)
            
            # Step 2: Auto-detect fields if needed (using already-fetched old_records)
            if fields is None:
                if not old_records_map:
                    raise ValueError(
                        "Cannot auto-detect fields for objects without PKs. "
                        "Either provide explicit 'fields' parameter or ensure objects have PKs."
                    )
                fields = self._detect_changed_fields(objs, old_records_map)
            
            # Convert map to ordered list for signal payload
            old_records = [old_records_map.get(obj.pk) for obj in objs]
            
            # Check if MTI model
            if self._is_mti_model():
                return self._mti_bulk_update(objs, fields, old_records, **kwargs)
            
            # Step 3: Fire BEFORE hooks
            self._fire_hooks_for_chain(
                BEFORE_UPDATE, 
                new_records=objs, 
                old_records=old_records, 
                update_fields=fields
            )
            
            # Step 4: Execute database update
            result = super().bulk_update(objs, fields=fields, batch_size=batch_size, **kwargs)
            
            # Step 5: Fire AFTER hooks
            self._fire_hooks_for_chain(
                AFTER_UPDATE, 
                new_records=objs, 
                old_records=old_records, 
                update_fields=fields
            )
            
            return result
        except Exception as e:
            # Transaction will auto-rollback on any exception
            logger.error(f"Hook or update failed: {e}")
            raise
    
    @transaction.atomic
    def update(self, lock_records=False, **kwargs):
        """
        Override update with hook support.
        
        Args:
            lock_records: Use select_for_update() for pessimistic locking
            **kwargs: Field updates
        """
        try:
            # Step 1: Get instances with optional locking (single query)
            queryset = self._optimize_queryset()
            if lock_records:
                queryset = queryset.select_for_update()
            
            instances = list(queryset)
            if not instances:
                return 0
            
            # Step 2: Fetch old records (already done above if not locked)
            if lock_records:
                old_records = instances  # Already fetched with lock
            else:
                old_records_map = self._fetch_old_records_map(instances, lock_records=False)
                old_records = [old_records_map.get(obj.pk) for obj in instances]
            
            # Step 3: Fire BEFORE hooks
            self._fire_hooks_for_chain(
                BEFORE_UPDATE, 
                new_records=instances, 
                old_records=old_records, 
                update_fields=list(kwargs.keys())
            )
            
            # Step 4: Execute update
            result = super().update(**kwargs)
            
            # Step 5: Refresh instances to get new values
            refreshed = list(self.model.objects.filter(pk__in=[obj.pk for obj in instances]))
            
            # Step 6: Fire AFTER hooks
            self._fire_hooks_for_chain(
                AFTER_UPDATE, 
                new_records=refreshed, 
                old_records=old_records, 
                update_fields=list(kwargs.keys())
            )
            
            return result
        except Exception as e:
            logger.error(f"Hook or update failed: {e}")
            raise
    
    @transaction.atomic
    def delete(self):
        """Override delete with hook support."""
        try:
            instances = list(self._optimize_queryset())
            if not instances:
                return (0, {})
            
            # Fire BEFORE hooks
            self._fire_hooks_for_chain(BEFORE_DELETE, new_records=[], old_records=instances)
            
            # Execute delete
            result = super().delete()
            
            # Fire AFTER hooks
            self._fire_hooks_for_chain(AFTER_DELETE, new_records=[], old_records=instances)
            
            return result
        except Exception as e:
            logger.error(f"Hook or delete failed: {e}")
            raise
    
    def _is_mti_model(self):
        """Check if this is a Multi-Table Inheritance model."""
        from django_bulk_lifecycle.data_access.mti_handler import MTIHandler
        handler = MTIHandler(self.model)
        return handler.is_mti_model()
    
    def _fire_hooks_for_chain(self, event, new_records, old_records=None, **kwargs):
        """
        Fire hooks for all models in the MTI inheritance chain.
        
        CRITICAL: Parent hooks fire first, then child hooks.
        This allows parent hooks to execute for both parent and child updates.
        Handlers receive actual child instances (polymorphic).
        
        ERROR HANDLING:
        - If any hook raises an exception, the transaction rolls back
        - All subsequent hooks are skipped
        - Exception propagates to caller
        - This ensures atomic behavior: either all hooks succeed or none do
        """
        from django_bulk_lifecycle.data_access.mti_handler import MTIHandler
        
        handler = MTIHandler(self.model)
        inheritance_chain = handler.get_inheritance_chain()
        signal = EVENT_TO_SIGNAL[event]
        
        # Fire signal for each model in the chain (parent → child)
        for model_class in inheritance_chain:
            signal.send(
                sender=model_class,
                new_records=new_records,  # Always actual child instances
                old_records=old_records or [],
                **kwargs
            )
    
    def _optimize_queryset(self):
        """Optimize queryset with select_related for FK fields."""
        from django_bulk_lifecycle.data_access.query_optimizer import QueryOptimizer
        optimizer = QueryOptimizer(self.model)
        return optimizer.optimize_queryset(self)
    
    def _fetch_old_records_map(self, objs, lock_records=False):
        """
        Fetch old records in a single optimized query.
        Returns Dict[pk, instance] for O(1) lookups.
        
        Args:
            objs: Model instances to fetch
            lock_records: If True, use select_for_update()
        
        Returns:
            Dict mapping PK to old instance
        """
        from django_bulk_lifecycle.data_access.record_fetcher import RecordFetcher
        fetcher = RecordFetcher(self.model)
        return fetcher.fetch_old_records_map(objs, lock_records=lock_records)
    
    def _detect_changed_fields(self, objs, old_records_map):
        """
        Auto-detect which fields have changed.
        Uses already-fetched old_records_map for efficiency (no extra query).
        
        Args:
            objs: New instances
            old_records_map: Dict[pk, old_instance]
        
        Returns:
            List of field names that changed
        """
        from django_bulk_lifecycle.data_access.field_tracker import FieldTracker
        return FieldTracker.detect_changed_fields(objs, old_records_map)
```

## 🔗 MTI Hook Cascading Behavior

### Critical Design: Inheritance-Based Hook Execution

**User Mental Model**: When using Multi-Table Inheritance, parent hooks should automatically fire for child model operations, just like method inheritance in Python.

### Example Scenario:

```python
# ===== Core Repository (Parent Model) =====
class Account(BulkLifecycleModelMixin):
    name = models.CharField(max_length=100)
    balance = models.DecimalField(max_digits=10, decimal_places=2)

class AccountHooks(LifecycleHook):
    @hook(AFTER_UPDATE, model=Account)
    def audit_balance_changes(self, new_records, old_records):
        """
        This hook fires for:
        - Account.objects.bulk_update([account])
        - LoanAccount.objects.bulk_update([loan])  ← Child model update!
        """
        for new, old in zip(new_records, old_records):
            if new.balance != old.balance:
                AuditLog.create(...)


# ===== Your Application (Child Model) =====
class LoanAccount(Account):  # MTI
    loan_type = models.CharField(max_length=50)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)

class LoanAccountHooks(LifecycleHook):
    @hook(AFTER_UPDATE, model=LoanAccount)
    def recalculate_interest(self, new_records, old_records):
        """
        This hook fires ONLY for:
        - LoanAccount.objects.bulk_update([loan])
        """
        for loan in new_records:
            loan.recalculate_interest_schedule()
```

### Hook Execution Order:

When `LoanAccount.objects.bulk_update([loan], fields=['balance'])` is called:

```
1. BEFORE_UPDATE Phase:
   → Fire: bulk_pre_update(sender=Account, new_records=[loan], ...)
      • AccountHooks.audit_balance_changes() [if BEFORE_UPDATE]
   → Fire: bulk_pre_update(sender=LoanAccount, new_records=[loan], ...)
      • LoanAccountHooks.recalculate_interest() [if BEFORE_UPDATE]

2. DATABASE UPDATE Phase:
   → Update `account` table (parent fields)
   → Update `loanaccount` table (child fields)

3. AFTER_UPDATE Phase:
   → Fire: bulk_post_update(sender=Account, new_records=[loan], ...)
      • AccountHooks.audit_balance_changes() ✓
   → Fire: bulk_post_update(sender=LoanAccount, new_records=[loan], ...)
      • LoanAccountHooks.recalculate_interest() ✓
```

### Key Guarantees:

1. **Parent → Child Order**: Parent hooks always execute before child hooks (both BEFORE and AFTER)
2. **Polymorphic Instances**: Hooks receive actual child instances (LoanAccount), not parent instances
3. **Field Access**: Parent hooks can safely access parent fields; child hooks can access all fields
4. **Power User Option**: Handlers can use `isinstance(record, LoanAccount)` to detect child types if needed
5. **Update Trigger**: Updating ANY field (parent or child) fires hooks for entire inheritance chain

### Why This Matters:

```python
# Core library defines parent validation
class AccountHooks(LifecycleHook):
    @hook(BEFORE_UPDATE, model=Account)
    def validate_balance(self, new_records, old_records):
        for account in new_records:
            if account.balance < 0:
                raise ValidationError("Negative balance not allowed")

# Your app extends with child model
class LoanAccount(Account):
    min_balance = models.DecimalField(...)

# ✓ Parent validation STILL WORKS automatically!
# You don't need to re-implement balance validation in LoanAccount hooks
loan.balance = -100
LoanAccount.objects.bulk_update([loan])  # ← Raises ValidationError from parent hook!
```

## 🗄️ Data Access Layer

### 1. MTI Handler

```python
# data_access/mti_handler.py
class MTIHandler:
    """
    Handles Multi-Table Inheritance detection and hook cascading.
    
    Responsibilities:
    - Detect if model uses MTI
    - Get complete inheritance chain (root → child)
    - Coordinate hook firing across chain
    - Split update fields by table
    """
    
    def __init__(self, model_cls):
        self.model_cls = model_cls
    
    def is_mti_model(self):
        """Check if this model uses Multi-Table Inheritance."""
        return bool(self.model_cls._meta.parents)
    
    def get_inheritance_chain(self):
        """
        Get inheritance chain from root parent to current model.
        
        Returns: [RootParent, Parent, Child]
        
        Example:
            Account → Business → LoanAccount
            Returns: [Account, Business, LoanAccount]
        """
        chain = []
        current = self.model_cls
        
        while current:
            if not current._meta.proxy:
                chain.append(current)
            
            parents = [p for p in current._meta.parents.keys() if not p._meta.proxy]
            current = parents[0] if parents else None
        
        chain.reverse()  # Root → Child
        return chain
    
    def split_fields_by_table(self, update_fields):
        """
        Split update fields by which table they belong to.
        
        Returns: {Model: [field_names]}
        """
        chain = self.get_inheritance_chain()
        field_map = {}
        
        for field_name in update_fields:
            field = self.model_cls._meta.get_field(field_name)
            for model in chain:
                if field in model._meta.local_fields:
                    if model not in field_map:
                        field_map[model] = []
                    field_map[model].append(field_name)
                    break
        
        return field_map
```

## 🏗️ MTI Bulk Operations Implementation

### Critical Multi-Step Process

MTI bulk operations are **non-trivial** because Django requires inserting into parent table(s) first to obtain primary keys before inserting into child tables. This section details the exact algorithm.

### _mti_bulk_create Algorithm

```python
def _mti_bulk_create(self, objs, **kwargs):
    """
    Multi-table inheritance bulk create algorithm.
    
    CRITICAL: Parent tables must be inserted BEFORE child tables to get PKs.
    
    Algorithm:
    1. Fire BEFORE_CREATE hooks for entire inheritance chain (parent → child)
    2. For each parent model in chain:
       a. Create parent instances from child object data
       b. Bulk insert into parent table (gets PKs via RETURNING)
       c. Map returned PKs back to child objects
    3. Create child instances with parent PKs
    4. Bulk insert into child table
    5. Fire AFTER_CREATE hooks for entire inheritance chain (parent → child)
    
    All steps wrapped in transaction.atomic() from caller.
    """
    inheritance_chain = self._get_inheritance_chain()  # [Account, Business, LoanAccount]
    
    with transaction.atomic(using=self.db, savepoint=False):
        # Step 1: Fire BEFORE hooks for all models in chain
        for model_class in inheritance_chain:
            self._fire_signal(
                BEFORE_CREATE,
                sender=model_class,
                new_records=objs
            )
        
        # Step 2: Create parent instances and get PKs
        parent_pk_map = {}  # Maps: child_obj_id → {ParentModel: parent_pk}
        
        for parent_model in inheritance_chain[:-1]:  # All except child
            # 2a. Create parent instances
            parent_instances = []
            for obj in objs:
                parent_inst = self._create_parent_instance(obj, parent_model, parent_pk_map)
                parent_instances.append(parent_inst)
            
            # 2b. Bulk insert into parent table
            created_parents = parent_model._base_manager.using(self.db).bulk_create(
                parent_instances,
                batch_size=kwargs.get('batch_size')
            )
            
            # 2c. Map PKs back to child objects
            for obj, created_parent in zip(objs, created_parents):
                obj_id = id(obj)
                if obj_id not in parent_pk_map:
                    parent_pk_map[obj_id] = {}
                parent_pk_map[obj_id][parent_model] = created_parent.pk
        
        # Step 3: Create child instances with parent PKs
        child_model = inheritance_chain[-1]
        child_instances = []
        for obj in objs:
            child_inst = self._create_child_instance(obj, child_model, parent_pk_map.get(id(obj), {}))
            child_instances.append(child_inst)
        
        # Step 4: Bulk insert child table
        created_children = child_model._base_manager.using(self.db).bulk_create(
            child_instances,
            batch_size=kwargs.get('batch_size')
        )
        
        # Step 5: Copy PKs and auto-generated fields back to original objects
        for obj, child in zip(objs, created_children):
            obj.pk = child.pk
            # Copy any auto-generated fields (auto_now_add, etc.)
            for field in child_model._meta.fields:
                if hasattr(field, 'auto_now_add') and field.auto_now_add:
                    setattr(obj, field.name, getattr(child, field.name))
        
        # Step 6: Fire AFTER hooks for all models in chain
        for model_class in inheritance_chain:
            self._fire_signal(
                AFTER_CREATE,
                sender=model_class,
                new_records=objs
            )
        
        return objs

def _create_parent_instance(self, source_obj, parent_model, parent_pk_map):
    """
    Create parent model instance from child object.
    Only copies fields that exist in parent model's local_fields.
    """
    parent_obj = parent_model()
    
    # Copy parent's local fields from source
    for field in parent_model._meta.local_fields:
        if hasattr(source_obj, field.name):
            value = getattr(source_obj, field.name)
            if value is not None:
                setattr(parent_obj, field.name, value)
    
    # Link to grandparent if exists
    obj_id = id(source_obj)
    if obj_id in parent_pk_map:
        for ancestor_model, ancestor_pk in parent_pk_map[obj_id].items():
            parent_link = parent_model._meta.get_ancestor_link(ancestor_model)
            if parent_link:
                setattr(parent_obj, parent_link.attname, ancestor_pk)
    
    return parent_obj

def _create_child_instance(self, source_obj, child_model, parent_pks):
    """
    Create child model instance with parent PKs.
    Links child to all parent tables via parent_ptr fields.
    """
    child_obj = child_model()
    
    # Copy child's local fields
    for field in child_model._meta.local_fields:
        if not field.primary_key and hasattr(source_obj, field.name):
            value = getattr(source_obj, field.name)
            if value is not None:
                setattr(child_obj, field.name, value)
    
    # Set parent links (parent_ptr fields)
    for parent_model, parent_pk in parent_pks.items():
        parent_link = child_model._meta.get_ancestor_link(parent_model)
        if parent_link:
            setattr(child_obj, parent_link.attname, parent_pk)
    
    return child_obj
```

### _mti_bulk_update Algorithm

```python
def _mti_bulk_update(self, objs, fields, old_records, **kwargs):
    """
    Multi-table inheritance bulk update algorithm.
    
    CRITICAL: Updates must be split by table and executed separately.
    
    Algorithm:
    1. Fire BEFORE_UPDATE hooks for entire inheritance chain
    2. Split update fields by which table they belong to
    3. For each table in inheritance chain:
       a. Filter fields for this table
       b. Build UPDATE query for this table
       c. Execute update
    4. Fire AFTER_UPDATE hooks for entire inheritance chain
    
    All steps wrapped in transaction.atomic() from caller.
    """
    inheritance_chain = self._get_inheritance_chain()
    
    with transaction.atomic(using=self.db, savepoint=False):
        # Step 1: Fire BEFORE hooks
        for model_class in inheritance_chain:
            self._fire_signal(
                BEFORE_UPDATE,
                sender=model_class,
                new_records=objs,
                old_records=old_records,
                update_fields=fields
            )
        
        # Step 2: Split fields by table
        field_map = self._split_fields_by_table(fields)  # {Model: [field_names]}
        
        # Step 3: Update each table
        for model_class, model_fields in field_map.items():
            if not model_fields:
                continue
            
            # Build PK list for this table
            pks = [obj.pk for obj in objs]
            
            # Use Django's bulk_update on base manager
            # For child tables, use parent_ptr field to filter
            if model_class == inheritance_chain[0]:
                # Root model - use PK directly
                queryset = model_class._base_manager.filter(pk__in=pks)
            else:
                # Child model - use parent link
                parent_link = model_class._meta.get_ancestor_link(inheritance_chain[0])
                queryset = model_class._base_manager.filter(**{f'{parent_link.attname}__in': pks})
            
            # Build update dict for this table
            # Use CASE/WHEN for bulk update
            update_data = self._build_case_statements(model_class, objs, model_fields)
            queryset.update(**update_data)
        
        # Step 4: Fire AFTER hooks
        for model_class in inheritance_chain:
            self._fire_signal(
                AFTER_UPDATE,
                sender=model_class,
                new_records=objs,
                old_records=old_records,
                update_fields=fields
            )
        
        return len(objs)

def _split_fields_by_table(self, fields):
    """
    Split update fields by which table they belong to.
    
    Returns: {Model: [field_names]}
    
    Example:
        fields = ['balance', 'interest_rate']
        Returns: {
            Account: ['balance'],
            LoanAccount: ['interest_rate']
        }
    """
    chain = self._get_inheritance_chain()
    field_map = {}
    
    for field_name in fields:
        field = self.model._meta.get_field(field_name)
        for model in chain:
            if field in model._meta.local_fields:
                if model not in field_map:
                    field_map[model] = []
                field_map[model].append(field_name)
                break
    
    return field_map

def _build_case_statements(self, model_class, objs, fields):
    """
    Build CASE/WHEN statements for bulk update.
    
    Returns: Dict suitable for queryset.update(**dict)
    """
    from django.db.models import Case, When, Value
    
    update_dict = {}
    for field_name in fields:
        field = model_class._meta.get_field(field_name)
        
        # Build WHEN clauses
        when_clauses = [
            When(pk=obj.pk, then=Value(getattr(obj, field_name), output_field=field))
            for obj in objs
        ]
        
        # Build CASE statement
        update_dict[field_name] = Case(*when_clauses, output_field=field)
    
    return update_dict
```

### Key Implementation Notes

1. **Transaction Atomicity**: Both algorithms are called within `@transaction.atomic` from the queryset method
2. **PK Retrieval**: Parent inserts use `bulk_create` which returns instances with PKs (via RETURNING on PostgreSQL)
3. **Field Mapping**: Each field belongs to exactly one table in the inheritance chain
4. **Hook Ordering**: Parent hooks always fire before child hooks
5. **Referential Integrity**: Parent PKs must exist before child inserts
6. **Performance**: O(k) queries where k = inheritance depth, not O(n) where n = number of objects

### 2. Record Fetcher

```python
# data_access/record_fetcher.py
class RecordFetcher:
    """Efficiently fetch records with query optimization."""
    
    def __init__(self, model_cls):
        self.model_cls = model_cls
    
    def fetch_old_records(self, objs):
        """
        Fetch old records for comparison - SINGLE optimized query.
        
        Returns records in same order as input objects.
        """
        pks = [obj.pk for obj in objs if obj.pk]
        if not pks:
            return []
        
        # Single query with select_related for FK fields
        old_records_map = {
            obj.pk: obj 
            for obj in self.model_cls._base_manager.filter(pk__in=pks).select_related(
                *self._get_fk_fields()
            )
        }
        
        # Return in same order as input
        return [old_records_map.get(obj.pk) for obj in objs]
    
    def _get_fk_fields(self):
        """Get FK field names for select_related optimization."""
        return [
            f.name for f in self.model_cls._meta.get_fields()
            if f.is_relation and not f.many_to_many and not f.one_to_many
        ]
```

### 3. Field Tracker

```python
# data_access/field_tracker.py
class FieldTracker:
    """Track field changes without N+1 queries."""
    
    def __init__(self, new_instance, old_instance=None):
        self.new_instance = new_instance
        self.old_instance = old_instance
    
    def get_changed_fields(self):
        """Get list of fields that have changed."""
        if not self.old_instance:
            return []
        
        changed = []
        for field in self.new_instance._meta.fields:
            if field.primary_key:
                continue
            
            new_val = self._get_field_value(self.new_instance, field)
            old_val = self._get_field_value(self.old_instance, field)
            
            if new_val != old_val:
                changed.append(field.name)
        
        return changed
    
    def _get_field_value(self, instance, field):
        """Get field value using proper comparison."""
        if field.is_relation and not field.many_to_many:
            # Use attname for FK to compare IDs
            return getattr(instance, field.attname, None)
        return field.get_prep_value(getattr(instance, field.name, None))
    
    @staticmethod
    def detect_changed_fields(objs):
        """
        Auto-detect changed fields across multiple objects.
        Used in bulk_update when fields=None.
        """
        if not objs:
            return []
        
        # Collect all field names that have changed across all objects
        all_changed = set()
        for obj in objs:
            tracker = FieldTracker(obj, obj._state.db)  # Simplified
            all_changed.update(tracker.get_changed_fields())
        
        return list(all_changed)
```

### 4. Query Optimizer

```python
# data_access/query_optimizer.py
class QueryOptimizer:
    """Optimize queries to prevent N+1 problems."""
    
    def __init__(self, model_cls):
        self.model_cls = model_cls
    
    def optimize_queryset(self, queryset):
        """Add select_related for all FK fields."""
        fk_fields = [
            f.name for f in self.model_cls._meta.get_fields()
            if f.is_relation and not f.many_to_many and not f.one_to_many
        ]
        
        if fk_fields:
            return queryset.select_related(*fk_fields)
        return queryset
```

## 📝 Usage Examples

### 1. Basic Model Setup

```python
# models.py
from django.db import models
from django_bulk_lifecycle import BulkLifecycleModelMixin

class Account(BulkLifecycleModelMixin):
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    name = models.CharField(max_length=100)
```

### 2. Hook Handlers (Recommended Pattern)

```python
# hooks.py
from django_bulk_lifecycle import hook, LifecycleHook, AFTER_UPDATE, BEFORE_CREATE
from django_bulk_lifecycle.conditions import WhenFieldHasChanged
from .models import Account

class AccountHooks(LifecycleHook):
    @hook(AFTER_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    def audit_balance_change(self, new_records, old_records):
        """Audit balance changes."""
        for new_account, old_account in zip(new_records, old_records):
            AuditLog.objects.create(
                model='Account',
                instance_id=new_account.pk,
                field='balance',
                old_value=old_account.balance,
                new_value=new_account.balance
            )
    
    @hook(BEFORE_CREATE, model=Account)
    def validate_initial_balance(self, new_records, old_records):
        """Validate account creation."""
        for account in new_records:
            if account.balance < 0:
                raise ValidationError("Account cannot have negative balance")
```

### 3. Direct Signal Receivers (Alternative)

```python
# signals.py
from django.dispatch import receiver
from django_bulk_lifecycle.signals import bulk_post_update
from .models import Account

@receiver(bulk_post_update, sender=Account)
def audit_balance_changes(sender, new_records, old_records, **kwargs):
    """Direct signal receiver - no hook decorator."""
    for new_account, old_account in zip(new_records, old_records):
        if old_account.balance != new_account.balance:
            AuditLog.objects.create(...)
```

### 4. MTI Example

```python
# models.py
class Account(BulkLifecycleModelMixin):
    balance = models.DecimalField(max_digits=10, decimal_places=2)

class LoanAccount(Account):  # MTI
    loan_type = models.CharField(max_length=50)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)

# hooks.py
class AccountHooks(LifecycleHook):
    @hook(AFTER_UPDATE, model=Account)
    def audit_all_account_changes(self, new_records, old_records):
        """Fires for Account AND LoanAccount updates."""
        pass

class LoanAccountHooks(LifecycleHook):
    @hook(AFTER_UPDATE, model=LoanAccount)
    def recalculate_loan_schedule(self, new_records, old_records):
        """Fires ONLY for LoanAccount updates."""
        pass

# Usage
loan = LoanAccount.objects.get(pk=1)
loan.balance = 5000
LoanAccount.objects.bulk_update([loan])
# ✓ Both AccountHooks and LoanAccountHooks fire!
```

## 🔒 Transaction Safety

### Overview

All bulk operations in `django-bulk-lifecycle` follow Django's transaction philosophy: **explicit is better than implicit**. Bulk operations are automatically atomic, while single-instance operations let you control transaction boundaries.

### Guarantees

#### 1. **Bulk Operations Are Atomic**

All bulk operations (`bulk_create`, `bulk_update`, `update()`, `delete()`) are wrapped in `transaction.atomic()`:

- Either ALL hooks + DB operation succeed, or EVERYTHING rolls back
- No partial updates
- Complete atomicity

#### 2. **Single Instance Operations**

`model.save()` and `model.delete()` are NOT automatically wrapped:

- Follows Django convention - user controls transaction boundaries
- To ensure atomicity, wrap in your own transaction:
  ```python
  with transaction.atomic():
      account.save()  # Now hooks + save are atomic
  ```


#### 3. **MTI Operations**

MTI bulk operations update multiple tables:

- Always called within existing transaction (from bulk operations)
- Fully atomic - all tables update or none do
- Maintains referential integrity

#### 4. **Nested Transactions**

- If caller is already in a transaction, Django uses savepoints automatically
- No special handling needed
- Hooks can start their own transactions (will use savepoints)

#### 5. **Hook Failures**

- If ANY hook raises an exception, transaction rolls back
- Database changes are reverted
- Exception propagates to caller
- **All receivers at same priority level execute** (Django signal behavior), but transaction still rolls back if any fail

#### 6. **Read Your Own Writes**

- AFTER hooks see committed data within the transaction
- Other transactions do NOT see changes until COMMIT
- Isolation level matters for concurrent access

### Transaction Timeline

```python
"""
Transaction Timeline for bulk_update():

START TRANSACTION (@transaction.atomic)
  ↓
  1. Fetch old_records (SELECT ... [FOR UPDATE if lock_records=True])
     ← Single query with select_related optimization
  ↓
  2. Auto-detect changed fields (if fields=None)
     ← No query, uses already-fetched old_records
  ↓
  3. Fire BEFORE hooks (bulk_pre_update)
     ← All parent → child hooks fire in order
  ↓
  4. Execute operation (UPDATE ... or multiple UPDATEs for MTI)
     ← Actual database modification
  ↓
  5. Fire AFTER hooks (bulk_post_update)
     ← All parent → child hooks fire in order
  ↓
COMMIT (or ROLLBACK if any step fails)

All queries happen INSIDE the transaction for consistency.
"""
```

### Best Practices

```python
# ✓ Good - bulk operations are safe
Account.objects.bulk_update([account1, account2])  # Atomic

# ✓ Good - single instance with explicit transaction
with transaction.atomic():
    account.save()  # Atomic

# ⚠️ Caution - single instance without transaction
account.save()  # If AFTER hook fails, save succeeded but hook didn't run

# ✓ Good - hooks can use transactions
@hook(AFTER_CREATE, model=Account)
def create_audit_log(self, new_records, old_records):
    # This is fine - creates nested transaction/savepoint
    with transaction.atomic():
        AuditLog.objects.bulk_create([...])

# ✓ Good - validation in BEFORE hooks
@hook(BEFORE_CREATE, model=Account)
def validate_balance(self, new_records, old_records):
    for account in new_records:
        if account.balance < 0:
            raise ValidationError("Negative balance")
    # If this raises, DB operation rolls back

# ⚠️ Caution - slow hooks extend lock duration
@hook(AFTER_UPDATE, model=Account, lock_records=True)
def slow_processing(self, new_records, old_records):
    # Records stay locked during this hook
    time.sleep(5)  # Bad - holds locks for 5 seconds!
    
# ✓ Better - defer non-critical work
@hook(AFTER_UPDATE, model=Account)
def fast_hook(self, new_records, old_records):
    # Queue background task instead
    process_accounts_task.delay([acc.pk for acc in new_records])
```

### Exception Handling

#### Hook Exceptions Propagate

```python
@hook(AFTER_UPDATE, model=Account)
def failing_hook(self, new_records, old_records):
    raise ValueError("Something broke")

try:
    Account.objects.bulk_update([account])
except ValueError:
    # Transaction rolled back
    # Database unchanged
    # Can retry or handle
    pass
```

#### Multiple Hook Failures

```python
# If multiple hooks fail:
# - All receivers at same priority execute (Django signal behavior)
# - First exception propagates
# - Other exceptions are logged but not raised
# - Use logging to debug multi-hook failures

@hook(AFTER_UPDATE, model=Account, priority=10)
def hook1(self, new_records, old_records):
    raise ValueError("Error 1")  # This propagates

@hook(AFTER_UPDATE, model=Account, priority=10)
def hook2(self, new_records, old_records):
    raise ValueError("Error 2")  # This is logged but not raised

@hook(AFTER_UPDATE, model=Account, priority=20)
def hook3(self, new_records, old_records):
    # Never executes - priority 10 failed
    pass
```

#### Silent Failures (Antipattern)

```python
# ⚠️ BAD - Don't catch exceptions silently
@hook(AFTER_UPDATE, model=Account)
def risky_hook(self, new_records, old_records):
    try:
        risky_operation()
    except Exception:
        pass  # BAD - hides problems, transaction commits anyway

# ✓ GOOD - Log and re-raise
@hook(AFTER_UPDATE, model=Account)
def risky_hook(self, new_records, old_records):
    try:
        risky_operation()
    except Exception as e:
        logger.error(f"Hook failed: {e}")
        raise  # GOOD - transaction rolls back properly
```

### Locking and Concurrency

#### Optional Pessimistic Locking

```python
# Default: Optimistic (no locks, better concurrency)
Account.objects.bulk_update(accounts, fields=['balance'])

# Pessimistic: Lock records during update
Account.objects.bulk_update(
    accounts, 
    fields=['balance'],
    lock_records=True  # Uses SELECT ... FOR UPDATE
)
```

#### Deadlock Risk

```python
"""
⚠️ Deadlock Risk with lock_records=True:

# Process A
Account.objects.bulk_update([acc1, acc2], lock_records=True)
  # Locks acc1, then acc2

# Process B (simultaneous)
Account.objects.bulk_update([acc2, acc1], lock_records=True)
  # Locks acc2, then acc1
  # 💥 DEADLOCK - each process waiting for other's lock

Solution: Always update records in consistent order (e.g., sorted by PK)

# ✓ Good - consistent ordering prevents deadlocks
accounts = sorted(accounts, key=lambda a: a.pk)
Account.objects.bulk_update(accounts, lock_records=True)
"""
```

#### Lock Duration = Hook Duration

```python
"""
When using lock_records=True:
- Records stay locked during ENTIRE operation
- This includes hook execution time
- Slow hooks = longer locks = more contention

Timeline with locking:
START TRANSACTION
  ↓
  SELECT ... FOR UPDATE  ← Records locked here
  ↓
  Fire BEFORE hooks     ← Still locked
  ↓
  UPDATE ...            ← Still locked
  ↓
  Fire AFTER hooks      ← Still locked (slow hooks hurt here!)
  ↓
COMMIT                  ← Records unlocked

Keep AFTER hooks FAST or don't use lock_records=True.
"""
```

### Performance Considerations

#### 1. Hook Latency Impact

```python
# ⚠️ Slow hook extends transaction and locks
@hook(AFTER_UPDATE, model=Account)
def send_notification(self, new_records, old_records):
    # BAD - holds transaction open
    send_email(...)  # Network call, slow
    
# ✓ Better - defer to background
@hook(AFTER_UPDATE, model=Account)
def queue_notification(self, new_records, old_records):
    # GOOD - fast, doesn't block
    send_email_task.delay([acc.pk for acc in new_records])
```

#### 2. Queries in Hooks

```python
# ⚠️ Additional queries extend transaction
@hook(AFTER_UPDATE, model=Account)
def update_related(self, new_records, old_records):
    for account in new_records:
        # Each iteration hits DB - N+1 problem
        Transaction.objects.filter(account=account).update(...)

# ✓ Better - bulk query
@hook(AFTER_UPDATE, model=Account)
def update_related_bulk(self, new_records, old_records):
    # Single query
    account_ids = [acc.pk for acc in new_records]
    Transaction.objects.filter(account_id__in=account_ids).update(...)
```

#### 3. Transaction Isolation

```python
"""
Read Your Own Writes:
- AFTER hooks see uncommitted changes within the transaction
- Other processes DON'T see changes until COMMIT
- Isolation level matters (READ COMMITTED, REPEATABLE READ, etc.)

Example:
@hook(AFTER_UPDATE, model=Account)
def verify_balance(self, new_records, old_records):
    # This query sees the updated balance (uncommitted)
    account = Account.objects.get(pk=new_records[0].pk)
    assert account.balance == new_records[0].balance  # ✓ True
    
    # But concurrent transaction won't see it yet
    # (depends on isolation level)
"""
```

### Django Admin Integration

Django Admin uses transactions for `save()` calls automatically:

```python
"""
Django Admin behavior:
- Admin change forms wrap save() in transaction.atomic()
- Hooks fire within admin transaction
- Validation errors shown in form (no DB changes)
- Admin bulk actions also fire hooks

Example:
class AccountAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        # Admin already wraps this in transaction
        obj.save()  # Hooks are atomic here
    
    actions = ['bulk_activate']
    
    def bulk_activate(self, request, queryset):
        # This fires hooks atomically
        queryset.update(status='active')
"""
```

### Testing Transaction Behavior

```python
from django.test import TransactionTestCase

class HookTransactionTests(TransactionTestCase):
    """Use TransactionTestCase for testing transaction behavior."""
    
    def test_hook_failure_rolls_back(self):
        """Verify that hook failures roll back DB changes."""
        
        @hook(AFTER_UPDATE, model=Account)
        def failing_hook(self, new_records, old_records):
            raise ValueError("Test failure")
        
        account = Account.objects.create(balance=100)
        account.balance = 200
        
        with self.assertRaises(ValueError):
            Account.objects.bulk_update([account], fields=['balance'])
        
        # Verify rollback
        account.refresh_from_db()
        self.assertEqual(account.balance, 100)  # Unchanged
```

### Summary

**Transaction safety in django-bulk-lifecycle**:

✅ **Bulk operations**: Always atomic (`@transaction.atomic`)

✅ **Single instances**: User controls (Django convention)

✅ **MTI operations**: Fully atomic across all tables

✅ **Hook failures**: Automatic rollback

✅ **Nested transactions**: Handled via savepoints

✅ **Locking**: Optional, configurable (`lock_records=False` default)

✅ **Performance**: Consider hook latency when using locks

✅ **Admin integration**: Works seamlessly

**Remember**: Keep hooks fast, use background tasks for slow operations, and always order records consistently when using locks.

## 🎯 Key Features

### 1. **Auto Field Detection**

- Automatically detect changed fields in bulk_update
- Proper field comparison with `field.get_prep_value()`
- Handle auto_now fields automatically

### 2. **Bypass Mechanisms**

- `bypass_hooks=False` parameter for all operations
- Context managers for temporary bypassing
- Clean separation of concerns

### 3. **MTI Support**

- Automatic hook cascading through inheritance chain
- Parent → child execution order
- Polymorphic instance handling
- Field mapping per table

### 4. **Subquery Support**

- Handle Django Subquery objects in updates
- Automatic instance refresh after Subquery updates
- Complex expression support (Case, When, etc.)

### 5. **Performance Optimizations**

- Query optimization with select_related
- Batch processing with configurable batch_size
- N+1 query prevention
- Single-query record fetching

## 🎯 Success Criteria

### Performance Targets:

- **Non-MTI**: 2-3 queries for any size bulk operation
- **MTI**: 2-3 queries × inheritance depth (optimal given table structure)
- **Memory**: <20% overhead vs vanilla Django
- **Latency**: <10% overhead vs vanilla Django

### Code Quality:

- **Test Coverage**: >95%
- **Cyclomatic Complexity**: <10 per method
- **Clear Separation**: Core signals + optional hook layer
- **Production Grade**: No hacks, all edge cases handled

## 🚀 Implementation Phases

### Phase 1: Core Signals (Week 1)

- [ ] Implement Django signals (bulk_pre_create, bulk_post_update, etc.)
- [ ] Create BulkLifecycleModelMixin with basic save/delete hooks
- [ ] Build RecordFetcher for single-query old record loading
- [ ] Add FieldTracker for change detection
- [ ] Set up test framework

### Phase 2: MTI Support (Week 2)

- [ ] Implement MTIHandler with inheritance chain detection
- [ ] Add hook cascading logic (parent → child)
- [ ] Handle field splitting by table
- [ ] Test MTI hook execution order
- [ ] Optimize MTI bulk operations

### Phase 3: Hook Decorator Layer (Week 3)

- [ ] Implement @hook decorator
- [ ] Create LifecycleHook base class
- [ ] Add HookCondition system (WhenFieldHasChanged, etc.)
- [ ] Build hook registry
- [ ] Test hook + signal integration

### Phase 4: QuerySet & Manager (Week 4)

- [ ] Implement BulkLifecycleQuerySet
- [ ] Add BulkLifecycleManager
- [ ] Integrate MTI detection and routing
- [ ] Add bypass_hooks support
- [ ] Optimize query patterns

### Phase 5: Polish & Documentation (Week 5)

- [ ] Comprehensive test suite
- [ ] Performance benchmarking
- [ ] Documentation and examples
- [ ] API reference
- [ ] Migration guide from django-bulk-triggers

## 🔧 Production Refinements

### 1. Hook Priority System

All hooks support a `priority` parameter (default 50) to control execution order:

```python
@hook(AFTER_UPDATE, model=Account, priority=10)  # Runs first
def critical_audit(self, new_records, old_records):
    pass

@hook(AFTER_UPDATE, model=Account, priority=50)  # Runs second (default)
def normal_processing(self, new_records, old_records):
    pass

@hook(AFTER_UPDATE, model=Account, priority=90)  # Runs last
def notifications(self, new_records, old_records):
    pass
```

**Priority Guidelines:**

- 0-25: High priority (critical operations, validation)
- 25-50: Normal priority (default)
- 50-75: Low priority (notifications, logging)
- 75-100: Lowest priority (cleanup, non-critical tasks)

### 2. Hook Registry for Introspection

The `HookRegistry` enables debugging and introspection:

```python
from django_bulk_lifecycle.registry import HookRegistry

# List all hooks for a model
hooks = HookRegistry.get_hooks(Account)
# Returns: {
#     'after_update': [(10, wrapper_func1), (50, wrapper_func2)],
#     'before_create': [(50, wrapper_func3)]
# }

# Get hooks for specific event
after_update_hooks = HookRegistry.get_hooks(Account, 'after_update')
# Returns: [(10, wrapper_func1), (50, wrapper_func2)]

# List all hooks across all models
all_hooks = HookRegistry.list_all_hooks()
```

**CLI Integration** (future):

```bash
python manage.py list_hooks Account
python manage.py list_hooks --all
```

### 3. Standardized Signal Payload

All signals include consistent `operation_meta`:

```python
# In querysets.py
from datetime import timezone
from uuid import uuid4

def _create_operation_meta(self):
    """Create standardized operation metadata."""
    return {
        "timestamp": timezone.now(),
        "database": self.db,
        "transaction_id": str(uuid4()),
        # Future: user context, request ID, etc.
    }

# In bulk_update
self._fire_hooks_for_chain(
    AFTER_UPDATE,
    new_records=objs,
    old_records=old_records,
    update_fields=fields,
    operation_meta=self._create_operation_meta()  # ← Standardized
)
```

**Hook Usage:**

```python
@hook(AFTER_UPDATE, model=Account)
def audit_with_metadata(self, new_records, old_records, operation_meta=None, **kwargs):
    # Access standardized metadata
    timestamp = operation_meta.get('timestamp')
    tx_id = operation_meta.get('transaction_id')
    
    AuditLog.objects.create(
        timestamp=timestamp,
        transaction_id=tx_id,
        ...
    )
```

### 4. Consistent FieldTracker API

Fixed signature for bulk detection:

```python
# data_access/field_tracker.py
class FieldTracker:
    @staticmethod
    def detect_changed_fields(objs, old_records_map):
        """
        Auto-detect changed fields across multiple objects.
        
        Args:
            objs: List of new instances
            old_records_map: Dict[pk, old_instance] - already fetched
        
        Returns:
            List of field names that changed across all objects
        """
        if not objs or not old_records_map:
            return []
        
        all_changed = set()
        for obj in objs:
            old_obj = old_records_map.get(obj.pk)
            if not old_obj:
                continue
            
            tracker = FieldTracker(obj, old_obj)
            all_changed.update(tracker.get_changed_fields())
        
        return list(all_changed)
```

### 5. Edge Case Documentation

#### bulk_create with update_conflicts

```python
"""
IMPORTANT: bulk_create with update_conflicts=True fires ONLY CREATE hooks,
NOT UPDATE hooks, even though some records may be updated.

This matches Django's semantic: bulk_create is a create operation,
regardless of conflict resolution strategy.

Example:
Account.objects.bulk_create(
    [Account(id=1, balance=100)],  # ID 1 already exists
    update_conflicts=True,
    unique_fields=['id'],
    update_fields=['balance']
)

# Fires: BEFORE_CREATE, AFTER_CREATE
# Does NOT fire: BEFORE_UPDATE, AFTER_UPDATE
"""
```

#### MTI with Overridden Fields

```python
"""
When child model overrides parent field:

class Account(BulkLifecycleModelMixin):
    owner = models.ForeignKey(User)  # Parent field

class LoanAccount(Account):
    owner = models.ForeignKey(User)  # Overridden in child

Behavior:
- Child field shadows parent field
- Hooks see child's version of the field
- Parent table still has original field (separate column)
- Use parent_ptr to access parent's version if needed
"""
```

#### Proxy Models

```python
"""
Proxy models do NOT trigger separate hooks:

class Account(BulkLifecycleModelMixin):
    pass

class SpecialAccount(Account):
    class Meta:
        proxy = True

# Hooks registered on Account fire for SpecialAccount
# Hooks registered on SpecialAccount fire only for SpecialAccount
# Inheritance chain skips proxy models (handled by _meta.proxy check)
"""
```

### 6. Comprehensive Test Strategy

#### Test Fixtures

```python
# conftest.py
import pytest

@pytest.fixture
def single_table_model():
    """Model without inheritance."""
    class SimpleAccount(BulkLifecycleModelMixin):
        balance = models.DecimalField(max_digits=10, decimal_places=2)
    return SimpleAccount

@pytest.fixture
def two_level_mti():
    """Parent → Child MTI."""
    class Account(BulkLifecycleModelMixin):
        balance = models.DecimalField()
    
    class LoanAccount(Account):
        interest_rate = models.DecimalField()
    
    return Account, LoanAccount

@pytest.fixture
def three_level_mti():
    """Grandparent → Parent → Child MTI."""
    class BaseAccount(BulkLifecycleModelMixin):
        owner = models.CharField(max_length=100)
    
    class Account(BaseAccount):
        balance = models.DecimalField()
    
    class LoanAccount(Account):
        interest_rate = models.DecimalField()
    
    return BaseAccount, Account, LoanAccount
```

#### Hook Execution Order Tests

```python
# test_hook_order.py
def test_mti_hook_execution_order(two_level_mti):
    """Verify parent → child hook execution order."""
    Account, LoanAccount = two_level_mti
    
    execution_order = []
    
    @hook(AFTER_UPDATE, model=Account, priority=50)
    def parent_hook(self, new_records, old_records):
        execution_order.append(('Account', 50))
    
    @hook(AFTER_UPDATE, model=LoanAccount, priority=50)
    def child_hook(self, new_records, old_records):
        execution_order.append(('LoanAccount', 50))
    
    loan = LoanAccount.objects.create(balance=100, interest_rate=5.0)
    loan.balance = 200
    LoanAccount.objects.bulk_update([loan], fields=['balance'])
    
    # Assert order: parent before child
    assert execution_order == [('Account', 50), ('LoanAccount', 50)]

def test_priority_ordering():
    """Verify hook priority ordering."""
    execution_order = []
    
    @hook(AFTER_UPDATE, model=Account, priority=90)
    def low_priority(self, new_records, old_records):
        execution_order.append(90)
    
    @hook(AFTER_UPDATE, model=Account, priority=10)
    def high_priority(self, new_records, old_records):
        execution_order.append(10)
    
    @hook(AFTER_UPDATE, model=Account, priority=50)
    def normal_priority(self, new_records, old_records):
        execution_order.append(50)
    
    account = Account.objects.create(balance=100)
    account.balance = 200
    Account.objects.bulk_update([account], fields=['balance'])
    
    # Assert priority order: 10, 50, 90
    assert execution_order == [10, 50, 90]
```

#### Rollback Verification Tests

```python
# test_transactions.py
from django.test import TransactionTestCase

class TransactionRollbackTests(TransactionTestCase):
    """Test transaction rollback on hook failures."""
    
    def test_before_hook_failure_prevents_update(self):
        """BEFORE hook failure should prevent DB update."""
        @hook(BEFORE_UPDATE, model=Account)
        def failing_before_hook(self, new_records, old_records):
            raise ValueError("Validation failed")
        
        account = Account.objects.create(balance=100)
        account.balance = 200
        
        with self.assertRaises(ValueError):
            Account.objects.bulk_update([account], fields=['balance'])
        
        # Verify no update occurred
        account.refresh_from_db()
        assert account.balance == 100
    
    def test_after_hook_failure_rolls_back_update(self):
        """AFTER hook failure should roll back successful DB update."""
        @hook(AFTER_UPDATE, model=Account)
        def failing_after_hook(self, new_records, old_records):
            raise ValueError("Post-processing failed")
        
        account = Account.objects.create(balance=100)
        account.balance = 200
        
        with self.assertRaises(ValueError):
            Account.objects.bulk_update([account], fields=['balance'])
        
        # Verify rollback
        account.refresh_from_db()
        assert account.balance == 100  # Rolled back!
    
    def test_mti_rollback_across_tables(self):
        """MTI failure should roll back both parent and child tables."""
        @hook(AFTER_UPDATE, model=LoanAccount)
        def failing_child_hook(self, new_records, old_records):
            raise ValueError("Child hook failed")
        
        loan = LoanAccount.objects.create(balance=100, interest_rate=5.0)
        loan.balance = 200
        loan.interest_rate = 6.0
        
        with self.assertRaises(ValueError):
            LoanAccount.objects.bulk_update([loan], fields=['balance', 'interest_rate'])
        
        # Verify both tables rolled back
        loan.refresh_from_db()
        assert loan.balance == 100  # Parent table rolled back
        assert loan.interest_rate == 5.0  # Child table rolled back
```

#### Performance Regression Tests

```python
# test_performance.py
import pytest
from django.test.utils import override_settings

@pytest.mark.benchmark
def test_bulk_update_query_count(benchmark, django_assert_num_queries):
    """Verify bulk_update uses optimal query count."""
    accounts = [Account.objects.create(balance=i) for i in range(100)]
    
    for acc in accounts:
        acc.balance += 10
    
    # Should be exactly 3 queries:
    # 1. Fetch old records
    # 2. Update operation
    # 3. No query for AFTER hooks (instances already in memory)
    with django_assert_num_queries(2):  # Fetch + Update
        Account.objects.bulk_update(accounts, fields=['balance'])

@pytest.mark.benchmark
def test_mti_query_count_per_level(benchmark):
    """Verify MTI adds constant queries per inheritance level."""
    # Create 3-level MTI: BaseAccount → Account → LoanAccount
    loans = [
        LoanAccount.objects.create(owner='User', balance=100, interest_rate=5.0)
        for i in range(100)
    ]
    
    for loan in loans:
        loan.balance += 10
    
    # Expected queries for 3-level MTI:
    # 1. Fetch old records
    # 2. Update BaseAccount table
    # 3. Update Account table
    # 4. Update LoanAccount table
    # Total: 4 queries (1 fetch + 3 updates)
    with django_assert_num_queries(4):
        LoanAccount.objects.bulk_update(loans, fields=['balance'])
```

### 7. Management Commands (Future Enhancement)

```python
# management/commands/list_hooks.py
from django.core.management.base import BaseCommand
from django_bulk_lifecycle.registry import HookRegistry

class Command(BaseCommand):
    help = 'List all registered lifecycle hooks'
    
    def add_arguments(self, parser):
        parser.add_argument('model', nargs='?', help='Model name (optional)')
        parser.add_argument('--event', help='Filter by event')
    
    def handle(self, *args, **options):
        if options['model']:
            # Show hooks for specific model
            self.show_model_hooks(options['model'], options.get('event'))
        else:
            # Show all hooks
            self.show_all_hooks()
    
    def show_model_hooks(self, model_name, event=None):
        hooks = HookRegistry.get_hooks(model_name, event)
        # Format and display...
```

## 🚨 Critical Fixes & Design Corrections (PRODUCTION REVIEW v2)

### Architectural Decisions & Launch Blockers

The following critical issues **MUST** be addressed before implementation. These are grouped by severity:

### 🔴 LAUNCH BLOCKERS (Must Fix)

#### 1. **Single Dispatcher - No Dual Execution Models** ❌

**Issue**: Plan proposes custom `HookDispatcher` AND Django signals, creating two different execution models with different ordering/exception semantics.

**Fix**: Make dispatcher the ONLY execution path:

```python
# dispatcher.py
import threading
from collections import defaultdict
from typing import Dict, List, Tuple, Callable, Any

class ReentrancyGuard:
    """Prevent infinite loops from hooks calling operations that trigger hooks."""
    
    def __init__(self):
        self._local = threading.local()
    
    def _get_context(self):
        if not hasattr(self._local, 'dispatch_stack'):
            self._local.dispatch_stack = []
        return self._local.dispatch_stack
    
    def is_dispatching(self, transaction_id, model_class, event, pk_set):
        """Check if we're already dispatching this exact operation."""
        stack = self._get_context()
        for ctx in stack:
            if (ctx['transaction_id'] == transaction_id and
                ctx['model'] is model_class and
                ctx['event'] == event and
                ctx['pk_set'] & pk_set):  # Overlapping PKs
                return True
        return False
    
    def enter(self, transaction_id, model_class, event, pk_set):
        """Enter dispatch context."""
        self._get_context().append({
            'transaction_id': transaction_id,
            'model': model_class,
            'event': event,
            'pk_set': pk_set,
            'depth': len(self._get_context())
        })
    
    def exit(self):
        """Exit dispatch context."""
        stack = self._get_context()
        if stack:
            stack.pop()

class HookDispatcher:
    """
    Single, authoritative dispatcher with priority support and reentrancy protection.
    
    This is the ONLY execution path for hooks. Django signals are optional thin wrappers.
    """
    
    def __init__(self):
        self.registry = HookRegistry()
        self.reentrancy_guard = ReentrancyGuard()
        self._lock = threading.RLock()
    
    def dispatch(self, model_class, lifecycle_event, new_records, old_records, 
                operation_meta, changeset=None, allow_reentrant=False):
        """
        Dispatch hooks with:
        - Priority ordering (lower number = earlier)
        - Fail-fast (first exception stops execution and propagates)
        - Reentrancy protection (prevents infinite loops)
        - Thread-safe
        
        Args:
            model_class: Model class
            lifecycle_event: Event constant (BEFORE_CREATE, etc.)
            new_records: List of new instances
            old_records: List of old instances
            operation_meta: Operation metadata dict
            changeset: ChangeSet object (required for UPDATE events)
            allow_reentrant: If False, prevent reentrant dispatch
        """
        transaction_id = operation_meta.get('transaction_id')
        pk_set = {getattr(r, 'pk', None) for r in new_records if hasattr(r, 'pk')}
        pk_set.discard(None)
        
        # Check for reentrancy
        if not allow_reentrant and self.reentrancy_guard.is_dispatching(
            transaction_id, model_class, lifecycle_event, pk_set
        ):
            logger.warning(
                f"Reentrancy detected: {model_class.__name__}.{lifecycle_event} "
                f"with PKs {pk_set}. Skipping to prevent infinite loop."
            )
            return
        
        # Get hooks sorted by priority
        with self._lock:
            prioritized_hooks = self.registry.get_hooks(model_class, lifecycle_event)
        
        if not prioritized_hooks:
            return
        
        # Enter dispatch context
        self.reentrancy_guard.enter(transaction_id, model_class, lifecycle_event, pk_set)
        
        try:
            for priority, hook_callable in sorted(prioritized_hooks, key=lambda t: t[0]):
                try:
                    # Call hook with full signature
                    hook_callable(
                        new_records=new_records,
                        old_records=old_records,
                        update_fields=operation_meta.get('update_fields'),
                        operation_meta=operation_meta,
                        changeset=changeset
                    )
                except Exception as e:
                    logger.error(
                        f"Hook {hook_callable.__name__} failed at priority {priority}: {e}",
                        exc_info=True
                    )
                    raise  # Fail-fast: stop immediately and propagate
        finally:
            self.reentrancy_guard.exit()

# Django signals are THIN WRAPPERS only (optional compatibility)
# Users should NOT register direct @receiver - use @hook instead

@receiver(bulk_pre_update, weak=False)
def _bulk_pre_update_dispatcher(sender, **kwargs):
    """
    Single Django signal receiver that delegates to custom dispatcher.
    This is the ONLY signal receiver - do NOT register additional receivers.
    """
    from django_bulk_lifecycle.dispatcher import get_dispatcher
    dispatcher = get_dispatcher()
    dispatcher.dispatch(sender, BEFORE_UPDATE, **kwargs)

# Runtime warning if someone tries to bypass dispatcher
def _check_for_rogue_receivers():
    """Warn if additional receivers are attached to lifecycle signals."""
    from django_bulk_lifecycle.signals import bulk_pre_update
    
    receivers = bulk_pre_update._live_receivers(None)
    if len(receivers) > 1:  # More than our dispatcher
        logger.warning(
            "Multiple receivers detected on bulk_pre_update. "
            "Only @hook decorator is supported. "
            "Direct @receiver usage may cause undefined behavior."
        )
```

**Impact**: Single execution model, deterministic behavior, no confusion.

#### 2. **MTI Bulk Update with Batching** ⚡

```python
# dispatcher.py
class HookDispatcher:
    """Custom dispatcher with priority support and deterministic ordering."""
    
    def __init__(self):
        self.registry = HookRegistry()
    
    def dispatch(self, model_class, lifecycle_event, new_records, old_records, **operation_meta):
        """
        Dispatch hooks with priority ordering and robust error handling.
        
        Strategy: Fail-fast (stop on first exception)
        - Hooks execute in priority order (lower number = earlier)
        - First exception stops execution and propagates
        - Transaction rolls back on any failure
        """
        prioritized_hooks = self.registry.get_hooks(model_class, lifecycle_event)
        
        for priority, hook_callable in sorted(prioritized_hooks, key=lambda t: t[0]):
            try:
                hook_callable(new_records, old_records, **operation_meta)
            except Exception as e:
                logger.error(f"Hook {hook_callable} failed at priority {priority}: {e}")
                raise  # Fail-fast: stop immediately and propagate

# Integration with Django signals (optional compatibility layer)
@receiver(bulk_pre_update)
def _bulk_pre_update_dispatcher(sender, new_records, old_records, **kwargs):
    """Single Django signal receiver that calls custom dispatcher."""
    dispatcher = HookDispatcher()
    dispatcher.dispatch(sender, BEFORE_UPDATE, new_records, old_records, **kwargs)
```

**Impact**: Priority now works correctly, execution is deterministic, and we control error handling.

### 2. **QuerySet.update() Uses Wrong Queryset** 🔴

**Issue**: `update()` method calls `super().update()` on `self` instead of the optimized/locked queryset, silently ignoring optimization and locking.

**Fix**:

```python
@transaction.atomic
def update(self, lock_records=False, **kwargs):
    """Override update with hook support."""
    try:
        # Step 1: Optimize and optionally lock
        queryset_for_update = self._optimize_queryset()
        if lock_records:
            queryset_for_update = queryset_for_update.select_for_update()
            # CRITICAL: Sort by PK to prevent deadlocks
            queryset_for_update = queryset_for_update.order_by('pk')
        
        instances = list(queryset_for_update)
        if not instances:
            return 0
        
        # Step 2: Fetch old records
        old_records_map = self._fetch_old_records_map(instances, lock_records=False)
        old_records = [old_records_map.get(obj.pk) for obj in instances]
        
        # Step 3: Fire BEFORE hooks with ChangeSet
        changeset = self._build_changeset(instances, old_records_map, list(kwargs.keys()))
        
        self._fire_hooks_for_chain(
            BEFORE_UPDATE,
            new_records=instances,
            old_records=old_records,
            update_fields=list(kwargs.keys()),
            operation_meta=self._create_operation_meta(),
            changeset=changeset
        )
        
        # Step 4: Execute update ON THE OPTIMIZED QUERYSET
        result = queryset_for_update.update(**kwargs)  # ← FIXED: Use optimized queryset
        
        # Step 5: Refresh instances
        refreshed = list(self.model.objects.filter(pk__in=[obj.pk for obj in instances]))
        
        # Step 6: Fire AFTER hooks
        self._fire_hooks_for_chain(
            AFTER_UPDATE,
            new_records=refreshed,
            old_records=old_records,
            update_fields=list(kwargs.keys()),
            operation_meta=self._create_operation_meta(),
            changeset=changeset
        )
        
        return result
    except Exception as e:
        logger.error(f"Hook or update failed: {e}")
        raise
```

**Impact**: Locking and optimization now work correctly.

### 3. **ChangeSet Structure for Performance** ⚡

**Issue**: Hooks repeatedly compute field deltas, conditions re-diff data.

**Fix**: Compute once, pass to all hooks:

```python
# changeset.py
@dataclass
class RecordChange:
    """Change information for a single record."""
    pk: Any
    changed_fields: List[str]
    old_values: Dict[str, Any]
    new_values: Dict[str, Any]

@dataclass
class ChangeSet:
    """Efficient change tracking structure."""
    changes_by_pk: Dict[Any, RecordChange]
    updated_fields: List[str]
    
    def has_field_changed(self, pk, field_name):
        """Check if field changed for specific record."""
        change = self.changes_by_pk.get(pk)
        return change and field_name in change.changed_fields
    
    def get_old_value(self, pk, field_name):
        """Get old value for specific field."""
        change = self.changes_by_pk.get(pk)
        return change.old_values.get(field_name) if change else None
    
    def get_new_value(self, pk, field_name):
        """Get new value for specific field."""
        change = self.changes_by_pk.get(pk)
        return change.new_values.get(field_name) if change else None

# In queryset
def _build_changeset(self, new_records, old_records_map, updated_fields):
    """Build ChangeSet once for all hooks to use."""
    changes_by_pk = {}
    
    for new_record in new_records:
        old_record = old_records_map.get(new_record.pk)
        if not old_record:
            continue
        
        changed_fields = []
        old_values = {}
        new_values = {}
        
        for field_name in updated_fields:
            field = self.model._meta.get_field(field_name)
            old_val = self._get_field_value(old_record, field)
            new_val = self._get_field_value(new_record, field)
            
            if old_val != new_val:
                changed_fields.append(field_name)
                old_values[field_name] = old_val
                new_values[field_name] = new_val
        
        changes_by_pk[new_record.pk] = RecordChange(
            pk=new_record.pk,
            changed_fields=changed_fields,
            old_values=old_values,
            new_values=new_values
        )
    
    return ChangeSet(
        changes_by_pk=changes_by_pk,
        updated_fields=updated_fields
    )

# Usage in hooks
@hook(AFTER_UPDATE, model=Account)
def audit_changes(self, new_records, old_records, changeset=None, **kwargs):
    if not changeset:
        return
    
    for record in new_records:
        if changeset.has_field_changed(record.pk, 'balance'):
            old_balance = changeset.get_old_value(record.pk, 'balance')
            new_balance = changeset.get_new_value(record.pk, 'balance')
            AuditLog.create(pk=record.pk, old=old_balance, new=new_balance)
```

**Impact**: Massive performance improvement, no re-diffing in hooks/conditions.

### 4. **MTI Field Ownership Detection** 🔧

**Issue**: Field identity comparison may fail in complex inheritance.

**Fix**:

```python
def _split_fields_by_table(self, fields):
    """Split update fields by table using field.model comparison."""
    chain = self._get_inheritance_chain()
    field_map = {}
    
    for field_name in fields:
        # Get field from child model
        field = self.model._meta.get_field(field_name)
        
        # Find which model owns this field by checking field.model
        for model in chain:
            # Compare by model identity, not field identity
            if field.model is model:
                if model not in field_map:
                    field_map[model] = []
                field_map[model].append(field_name)
                break
    
    return field_map
```

### 5. **bulk_create with update_conflicts Semantics** 📝

**Issue**: Fires only CREATE hooks, but users expect UPDATE hooks for updated records.

**Fix Option A** (Simple - Document Loudly):

```python
"""
⚠️ IMPORTANT: bulk_create(..., update_conflicts=True) fires ONLY CREATE hooks.

This is Django's semantic: bulk_create is a CREATE operation regardless of 
conflict resolution. If you need separate hooks for created vs updated:

Use separate operations:
- bulk_create(new_records, ignore_conflicts=True)  # CREATE hooks
- bulk_update(existing_records, fields=...)         # UPDATE hooks
"""
```

**Fix Option B** (Complex - Split Batches):

```python
def bulk_create_with_upsert_semantics(self, objs, unique_fields, update_fields, ...):
    """
    Smart upsert that fires correct hooks for created vs updated records.
    More queries but semantically correct.
    """
    # 1. Identify existing vs new
    pks_to_check = {getattr(obj, field) for obj in objs for field in unique_fields if hasattr(obj, field)}
    existing_map = {
        getattr(obj, unique_fields[0]): obj
        for obj in self.model.objects.filter(**{f"{unique_fields[0]}__in": pks_to_check})
    }
    
    # 2. Split into created vs updated
    to_create = [obj for obj in objs if getattr(obj, unique_fields[0]) not in existing_map]
    to_update = [obj for obj in objs if getattr(obj, unique_fields[0]) in existing_map]
    
    # 3. Fire correct hooks
    if to_create:
        self.bulk_create(to_create)  # CREATE hooks
    if to_update:
        self.bulk_update(to_update, fields=update_fields)  # UPDATE hooks
```

**Recommendation**: Use Option A (document) for simplicity. Offer Option B as `bulk_upsert()` method.

### 6. **on_commit Hook Support** 🎯

**Issue**: AFTER hooks run in-transaction, users need post-commit for external effects.

**Fix**:

```python
# hooks.py
def hook(event, model=None, condition=None, priority=50, on_commit=False):
    """
    Decorator with on_commit support for post-transaction work.
    
    Args:
        on_commit: If True, defer execution until after transaction commits.
                   Perfect for emails, webhooks, cache invalidation.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(new_records, old_records, **kwargs):
            if condition and not condition.evaluate(new_records, old_records):
                return
            
            if on_commit:
                # Queue for post-commit execution
                from django.db import transaction
                transaction.on_commit(
                    lambda: func(new_records, old_records, **kwargs)
                )
            else:
                # Execute immediately (in-transaction)
                return func(new_records, old_records, **kwargs)
        
        # Register with HookRegistry
        HookRegistry.register(model, event, wrapper, priority, on_commit=on_commit)
        return wrapper
    
    return decorator

# Usage
@hook(AFTER_CREATE, model=Account, on_commit=True)
def send_welcome_email(self, new_records, old_records):
    """Sends email AFTER transaction commits."""
    for account in new_records:
        send_email(account.email, "Welcome!")
```

### 7. **Chunked Hook Dispatch** 📊

**Issue**: Passing thousands of objects to hooks causes memory issues.

**Fix**:

```python
# In queryset
def _fire_hooks_for_chain_chunked(self, event, new_records, old_records, chunk_size=100, **kwargs):
    """
    Fire hooks in chunks to limit memory usage.
    
    Args:
        chunk_size: Number of records per hook invocation (default 100)
    """
    for i in range(0, len(new_records), chunk_size):
        new_chunk = new_records[i:i+chunk_size]
        old_chunk = old_records[i:i+chunk_size] if old_records else []
        
        # Fire for this chunk
        self._fire_hooks_for_chain(event, new_chunk, old_chunk, **kwargs)

# Usage with configuration
BulkLifecycleQuerySet.hook_chunk_size = 100  # Configurable

def bulk_update(self, objs, ...):
    # Use chunked dispatch for large batches
    if len(objs) > self.hook_chunk_size:
        self._fire_hooks_for_chain_chunked(BEFORE_UPDATE, objs, old_records, chunk_size=self.hook_chunk_size)
    else:
        self._fire_hooks_for_chain(BEFORE_UPDATE, objs, old_records)
```

### 8. **Dry Run Mode** 🧪

**Issue**: Hard to debug what hooks will fire and what changes will occur.

**Fix**:

```python
# In queryset
def bulk_update(self, objs, fields=None, dry_run=False, **kwargs):
    """
    Bulk update with optional dry-run mode.
    
    Args:
        dry_run: If True, compute everything but don't execute DB update.
                 Returns detailed execution plan.
    """
    if dry_run:
        # Build execution plan
        old_records_map = self._fetch_old_records_map(objs, lock_records=False)
        changeset = self._build_changeset(objs, old_records_map, fields)
        hooks_to_fire = self._get_hooks_execution_plan(BEFORE_UPDATE, AFTER_UPDATE)
        
        return {
            'would_update': len(objs),
            'affected_pks': [obj.pk for obj in objs],
            'changeset': changeset,
            'hooks_before': hooks_to_fire[BEFORE_UPDATE],
            'hooks_after': hooks_to_fire[AFTER_UPDATE],
            'fields': fields,
            'query_count_estimate': 2 + (len(self._get_inheritance_chain()) if self._is_mti_model() else 0)
        }
    
    # Normal execution
    return self._bulk_update_impl(objs, fields, **kwargs)
```

### 9. **Expression vs bulk_update Clarification** 📚

**Issue**: Plan claims Subquery support in bulk_update, but Django's bulk_update doesn't accept expressions.

**Fix - Document Clearly**:

```python
"""
IMPORTANT: Expression Handling in Updates

1. For per-object values (Python objects):
   Use bulk_update():
   ✓ Account.objects.bulk_update(accounts, fields=['balance'])

2. For set-wise expressions (F(), Case(), Subquery()):
   Use queryset.update():
   ✓ Account.objects.update(balance=F('balance') + 100)
   ✓ Account.objects.update(balance=Subquery(...))

3. After expression updates, refresh instances:
   refreshed = list(Account.objects.filter(pk__in=pks))
   # Use refreshed in AFTER hooks

Example:
# BAD - This won't work
Account.objects.bulk_update(accounts, fields=[F('balance') + 100])

# GOOD - Use queryset.update for expressions
Account.objects.filter(pk__in=[a.pk for a in accounts]).update(
    balance=F('balance') + 100
)
"""
```

### 10. **Database Routing** 🗄️

**Issue**: Doesn't respect `using=` and `self._state.db` consistently.

**Fix**:

```python
# In mixins.py
def save(self, using=None, *args, **kwargs):
    """Respect database routing consistently."""
    db = using or self._state.db
    
    # Use correct database for fetching old instance
    if self.pk:
        old_instance = self.__class__._base_manager.using(db).get(pk=self.pk)
    
    # Include database in operation_meta
    operation_meta = {
        'database': db,
        'timestamp': timezone.now(),
        ...
    }
    
    self._fire_hooks_for_inheritance_chain(
        BEFORE_UPDATE if self.pk else BEFORE_CREATE,
        new_records=[self],
        old_records=[old_instance] if self.pk else [],
        operation_meta=operation_meta
    )
    
    result = super().save(using=db, *args, **kwargs)
    ...
```

## 🏭 Factory & Dependency Injection System

### Overview

Professional applications require dependency injection for services, repositories, and other dependencies. The factory system enables seamless integration with DI containers while maintaining clean separation of concerns.

### Factory Interface

```python
# factory.py
import threading
from typing import Any, Callable, Optional, Type

# Thread-safe storage
_hook_factories: dict[Type, Callable[[], Any]] = {}
_default_factory: Optional[Callable[[Type], Any]] = None
_container_resolver: Optional[Callable[[Type], Any]] = None
_factory_lock = threading.RLock()


def set_hook_factory(hook_cls: Type, factory: Callable[[], Any]) -> None:
    """
    Register a factory function for a specific hook class.
    
    Args:
        hook_cls: The hook class to register a factory for
        factory: A callable that returns an instance of hook_cls
    
    Example:
        >>> def create_account_hooks():
        ...     return container.account_hooks()
        >>> 
        >>> set_hook_factory(AccountHooks, create_account_hooks)
    """
    with _factory_lock:
        _hook_factories[hook_cls] = factory


def set_default_hook_factory(factory: Callable[[Type], Any]) -> None:
    """
    Set a default factory for all hooks without a specific factory.
    
    Args:
        factory: A callable that takes a class and returns an instance
    
    Example:
        >>> def resolve_hook(hook_cls):
        ...     provider_name = hook_cls.__name__.lower()
        ...     return getattr(container, provider_name)()
        >>> 
        >>> set_default_hook_factory(resolve_hook)
    """
    global _default_factory
    with _factory_lock:
        _default_factory = factory


def configure_hook_container(container) -> None:
    """
    Configure hooks to use a dependency-injector container.
    
    Args:
        container: dependency-injector container instance
    
    Example:
        >>> from dependency_injector import containers, providers
        >>> 
        >>> class ApplicationContainer(containers.DeclarativeContainer):
        ...     # Services
        ...     account_repository = providers.Singleton(AccountRepository)
        ...     account_service = providers.Singleton(AccountService)
        ...     
        ...     # Hooks with DI
        ...     account_hooks = providers.Singleton(
        ...         AccountHooks,
        ...         service=account_service,
        ...         repository=account_repository
        ...     )
        >>> 
        >>> container = ApplicationContainer()
        >>> configure_hook_container(container)
    """
    def resolver(hook_cls):
        # Convert class name to provider name (AccountHooks → account_hooks)
        provider_name = _class_to_provider_name(hook_cls)
        try:
            provider = getattr(container, provider_name)
            return provider()
        except AttributeError:
            # Fallback to direct instantiation
            return hook_cls()
    
    set_default_hook_factory(resolver)


def create_hook_instance(hook_cls: Type) -> Any:
    """
    Create a hook instance using registered factories.
    
    Args:
        hook_cls: Hook class to instantiate
    
    Returns:
        Hook instance with dependencies injected
    """
    with _factory_lock:
        # Check for specific factory
        if hook_cls in _hook_factories:
            return _hook_factories[hook_cls]()
        
        # Check for default factory
        if _default_factory:
            return _default_factory(hook_cls)
        
        # Fallback to direct instantiation
        return hook_cls()


def _class_to_provider_name(cls: Type) -> str:
    """Convert class name to provider name (CamelCase → snake_case)."""
    import re
    name = cls.__name__
    # Convert CamelCase to snake_case
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def clear_hook_factories() -> None:
    """Clear all registered factories (useful for testing)."""
    global _default_factory, _container_resolver
    with _factory_lock:
        _hook_factories.clear()
        _default_factory = None
        _container_resolver = None
```

### Usage Patterns

#### Pattern 1: Container Integration (Recommended)

```python
from dependency_injector import containers, providers
from django_bulk_lifecycle import configure_hook_container, LifecycleHook, hook, AFTER_UPDATE

class LoanAccountService:
    def recalculate_schedule(self, loan_account):
        # Business logic
        pass

class ApplicationContainer(containers.DeclarativeContainer):
    # Services
    loan_service = providers.Singleton(LoanAccountService)
    
    # Hooks with DI
    loan_account_hooks = providers.Singleton(
        'myapp.hooks.LoanAccountHooks',
        loan_service=loan_service
    )

# In your Django app config
class MyAppConfig(AppConfig):
    def ready(self):
        container = ApplicationContainer()
        configure_hook_container(container)
```

#### Pattern 2: Explicit Factory Registration

```python
from django_bulk_lifecycle import set_hook_factory

def create_loan_hooks():
    return LoanAccountHooks(
        loan_service=container.loan_service(),
        validator=container.loan_validator()
    )

set_hook_factory(LoanAccountHooks, create_loan_hooks)
```

#### Pattern 3: Hook with Dependencies

```python
class LoanAccountHooks(LifecycleHook):
    """Hook handler with injected dependencies."""
    
    def __init__(self, loan_service, validator):
        self.loan_service = loan_service
        self.validator = validator
    
    @hook(AFTER_UPDATE, model=LoanAccount)
    def recalculate_on_balance_change(self, new_records, old_records, changeset=None):
        """Uses injected service."""
        for loan in new_records:
            if changeset and changeset.has_field_changed(loan.pk, 'balance'):
                self.loan_service.recalculate_schedule(loan)
```

### Integration with Hook Decorator

The `@hook` decorator automatically uses the factory system:

```python
# hooks.py (updated)
def hook(event, model=None, condition=None, priority=50, on_commit=False):
    def decorator(func):
        # When hook is called, create instance using factory
        def get_hook_handler():
            if hasattr(func, '__self__'):
                # Method on a class
                hook_class = func.__self__.__class__
                return create_hook_instance(hook_class)
            return None
        
        @wraps(func)
        def wrapper(new_records, old_records, **kwargs):
            # Get hook handler instance (with DI)
            handler = get_hook_handler()
            
            if condition and not condition.evaluate(new_records, old_records):
                return
            
            if on_commit:
                from django.db import transaction
                transaction.on_commit(
                    lambda: func(handler, new_records, old_records, **kwargs) if handler else func(new_records, old_records, **kwargs)
                )
            else:
                return func(handler, new_records, old_records, **kwargs) if handler else func(new_records, old_records, **kwargs)
        
        HookRegistry.register(model, event, wrapper, priority, on_commit=on_commit)
        return wrapper
    
    return decorator
```

## 🐛 Debug Utilities

### Overview

Production debugging requires query tracking, performance monitoring, and N+1 query detection. Debug utilities provide comprehensive observability without performance overhead in production.

### Debug Utilities Interface

```python
# debug_utils.py
import logging
import time
from functools import wraps
from django.db import connection
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def track_queries(func):
    """
    Decorator to track database queries during function execution.
    
    Usage:
        @track_queries
        def my_bulk_operation():
            Account.objects.bulk_update(accounts)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        initial_queries = len(connection.queries)
        initial_time = time.time()
        
        logger.debug(f"Starting {func.__name__} - query count: {initial_queries}")
        
        try:
            result = func(*args, **kwargs)
            
            final_queries = len(connection.queries)
            duration = time.time() - initial_time
            query_count = final_queries - initial_queries
            
            logger.debug(
                f"Completed {func.__name__} - "
                f"queries: {query_count}, duration: {duration:.4f}s"
            )
            
            # Log all queries if in debug mode
            if logger.isEnabledFor(logging.DEBUG) and query_count > 0:
                for i, query in enumerate(connection.queries[initial_queries:], 1):
                    logger.debug(f"  {i}. {query['sql'][:200]}... ({query['time']}s)")
            
            return result
        except Exception as e:
            query_count = len(connection.queries) - initial_queries
            logger.error(f"Exception in {func.__name__} after {query_count} queries: {e}")
            raise
    
    return wrapper


@contextmanager
def QueryTracker(context_name="QueryTracker"):
    """
    Context manager for tracking database queries.
    
    Usage:
        with QueryTracker("Bulk Update Operation"):
            Account.objects.bulk_update(accounts)
    """
    initial_queries = len(connection.queries)
    start_time = time.time()
    
    logger.debug(f"Starting {context_name} - initial query count: {initial_queries}")
    
    try:
        yield
    finally:
        final_queries = len(connection.queries)
        duration = time.time() - start_time
        query_count = final_queries - initial_queries
        
        logger.debug(
            f"Completed {context_name} - "
            f"queries: {query_count}, duration: {duration:.4f}s"
        )
        
        if logger.isEnabledFor(logging.DEBUG) and query_count > 0:
            for i, query in enumerate(connection.queries[initial_queries:], 1):
                logger.debug(f"  {i}. {query['sql'][:200]}... ({query['time']}s)")


def log_query_count(context=""):
    """Log current query count with context."""
    query_count = len(connection.queries)
    logger.debug(f"Query count at {context}: {query_count}")


def assert_query_count(expected_count, tolerance=0):
    """
    Assert query count for testing.
    
    Usage:
        with assert_query_count(2):  # Expect exactly 2 queries
            Account.objects.bulk_update(accounts)
    """
    @contextmanager
    def _assert():
        initial_queries = len(connection.queries)
        yield
        actual_count = len(connection.queries) - initial_queries
        
        if abs(actual_count - expected_count) > tolerance:
            queries_executed = connection.queries[initial_queries:]
            logger.error(
                f"Query count mismatch: expected {expected_count}, got {actual_count}"
            )
            for i, query in enumerate(queries_executed, 1):
                logger.error(f"  {i}. {query['sql'][:200]}")
            
            raise AssertionError(
                f"Expected {expected_count} queries (±{tolerance}), "
                f"but executed {actual_count}"
            )
    
    return _assert()


class PerformanceMonitor:
    """Monitor performance metrics for lifecycle operations."""
    
    def __init__(self):
        self.metrics = {}
    
    def record(self, operation_name, query_count, duration, record_count):
        """Record performance metrics."""
        if operation_name not in self.metrics:
            self.metrics[operation_name] = []
        
        self.metrics[operation_name].append({
            'query_count': query_count,
            'duration': duration,
            'record_count': record_count,
            'queries_per_record': query_count / record_count if record_count > 0 else 0,
            'duration_per_record': duration / record_count if record_count > 0 else 0
        })
    
    def get_summary(self, operation_name=None):
        """Get performance summary."""
        if operation_name:
            data = self.metrics.get(operation_name, [])
        else:
            data = [item for items in self.metrics.values() for item in items]
        
        if not data:
            return {}
        
        return {
            'total_operations': len(data),
            'avg_queries': sum(d['query_count'] for d in data) / len(data),
            'avg_duration': sum(d['duration'] for d in data) / len(data),
            'avg_records': sum(d['record_count'] for d in data) / len(data)
        }


# Global performance monitor
performance_monitor = PerformanceMonitor()
```

### Usage Examples

```python
# Example 1: Decorator usage
@track_queries
def update_account_balances(accounts):
    Account.objects.bulk_update(accounts, fields=['balance'])

# Example 2: Context manager
with QueryTracker("Monthly Balance Update"):
    for batch in batches:
        Account.objects.bulk_update(batch, fields=['balance'])

# Example 3: Test assertions
def test_bulk_update_query_count():
    accounts = [Account.objects.create(balance=100) for _ in range(100)]
    
    for acc in accounts:
        acc.balance += 10
    
    with assert_query_count(2):  # Expect: fetch + update
        Account.objects.bulk_update(accounts, fields=['balance'])
```

## 🚀 MTI Bulk Parent Optimization

### Overview

The current MTI implementation (lines 356-487 in mti_operations.py) has a **critical optimization** that uses bulk insert for parent tables instead of looping. This must be explicitly included in the new plan.

### Two-Path Strategy

```python
# In BulkLifecycleQuerySet._mti_bulk_create

def _can_use_bulk_parent_insert(self):
    """
    Check if database supports bulk insert with RETURNING (getting PKs back).
    
    Available on:
    - PostgreSQL (all versions)
    - Oracle 12+
    - SQLite 3.35+
    - MySQL 8.0.19+
    - MariaDB 10.5+
    """
    from django.db import connection
    features = connection.features
    return getattr(features, 'can_return_rows_from_bulk_insert', False)


def _mti_bulk_create(self, objs, **kwargs):
    """
    MTI bulk create with optimization.
    
    Strategy:
    - Try bulk insert for parents first (O(k) queries where k = depth)
    - Fall back to loop if bulk not supported (O(n*k) queries)
    """
    inheritance_chain = self._get_inheritance_chain()
    
    with transaction.atomic(using=self.db, savepoint=False):
        # Try bulk optimization first
        if self._can_use_bulk_parent_insert():
            try:
                parent_pk_map = self._bulk_create_parents(objs, inheritance_chain, **kwargs)
                logger.info(
                    f"✓ BULK optimization: Inserted {len(objs)} parents "
                    f"in {len(inheritance_chain)-1} queries "
                    f"(vs {len(objs) * (len(inheritance_chain)-1)} in loop)"
                )
            except Exception as e:
                logger.warning(f"Bulk parent insert failed, falling back to loop: {e}")
                parent_pk_map = self._loop_create_parents(objs, inheritance_chain, **kwargs)
        else:
            # Database doesn't support RETURNING
            logger.debug("Using loop approach (DB doesn't support RETURNING)")
            parent_pk_map = self._loop_create_parents(objs, inheritance_chain, **kwargs)
        
        # Create children (same for both paths)
        self._create_children_bulk(objs, inheritance_chain, parent_pk_map, **kwargs)
        
        return objs


def _bulk_create_parents(self, objs, inheritance_chain, **kwargs):
    """
    OPTIMIZED: Bulk insert parent objects (O(k) queries).
    
    For 1000 objects with 3-level inheritance:
    - Bulk: 3 queries (one per level)
    - Loop: 3000 queries (1000 * 3 levels)
    
    Returns: parent_pk_map Dict[obj_id, Dict[ParentModel, pk]]
    """
    parent_pk_map = {}
    bypass_hooks = kwargs.get('bypass_hooks', False)
    
    # Process each parent level
    for level_idx, parent_model in enumerate(inheritance_chain[:-1]):
        # Step 1: Create parent instances for ALL objects at this level
        parent_objs = []
        obj_to_parent = {}
        
        for obj in objs:
            parent_obj = self._create_parent_instance(obj, parent_model, parent_pk_map)
            parent_objs.append(parent_obj)
            obj_to_parent[id(parent_obj)] = obj
        
        # Step 2: Fire BEFORE hooks in bulk
        if not bypass_hooks:
            self._fire_hooks_for_chain(BEFORE_CREATE, parent_objs)
        
        # Step 3: BULK INSERT with RETURNING - KEY OPTIMIZATION!
        created_parents = parent_model._base_manager.using(self.db).bulk_create(
            parent_objs,
            batch_size=kwargs.get('batch_size')
        )
        
        # Step 4: Map PKs back to child objects
        for obj, created_parent in zip(objs, created_parents):
            obj_id = id(obj)
            if obj_id not in parent_pk_map:
                parent_pk_map[obj_id] = {}
            parent_pk_map[obj_id][parent_model] = created_parent.pk
            
            # Copy auto-generated fields back
            for field in parent_model._meta.local_fields:
                if hasattr(field, 'auto_now_add') and field.auto_now_add:
                    setattr(obj, field.name, getattr(created_parent, field.name))
        
        # Step 5: Fire AFTER hooks in bulk
        if not bypass_hooks:
            self._fire_hooks_for_chain(AFTER_CREATE, parent_objs)
    
    return parent_pk_map


def _loop_create_parents(self, objs, inheritance_chain, **kwargs):
    """
    FALLBACK: Create parent objects one-by-one (O(n*k) queries).
    
    Used when database doesn't support RETURNING or bulk insert fails.
    
    Returns: parent_pk_map Dict[obj_id, Dict[ParentModel, pk]]
    """
    parent_pk_map = {}
    bypass_hooks = kwargs.get('bypass_hooks', False)
    
    for obj in objs:
        parent_instances = {}
        current_parent = None
        
        for parent_model in inheritance_chain[:-1]:
            parent_obj = self._create_parent_instance(obj, parent_model, current_parent)
            
            # Fire hooks per object
            if not bypass_hooks:
                self._fire_hooks_for_chain(BEFORE_CREATE, [parent_obj])
            
            # Individual insert (gets PK back)
            field_values = {
                f.name: getattr(parent_obj, f.name)
                for f in parent_model._meta.local_fields
                if hasattr(parent_obj, f.name) and getattr(parent_obj, f.name) is not None
            }
            created_obj = parent_model._base_manager.using(self.db).create(**field_values)
            
            # Copy all fields back
            for field in parent_model._meta.local_fields:
                setattr(parent_obj, field.name, getattr(created_obj, field.name))
            
            if not bypass_hooks:
                self._fire_hooks_for_chain(AFTER_CREATE, [parent_obj])
            
            parent_instances[parent_model] = parent_obj
            current_parent = parent_obj
        
        parent_pk_map[id(obj)] = parent_instances
    
    return parent_pk_map
```

### Performance Comparison

```python
"""
Performance for 1000 objects with 3-level MTI (Grandparent → Parent → Child):

BULK PATH (with RETURNING support):
- Query 1: Bulk insert 1000 grandparents → get PKs
- Query 2: Bulk insert 1000 parents → get PKs  
- Query 3: Bulk insert 1000 children
Total: 3 queries

LOOP PATH (without RETURNING):
- Queries 1-1000: Insert each grandparent individually
- Queries 1001-2000: Insert each parent individually
- Queries 2001-3000: Insert each child individually
Total: 3000 queries

Speedup: 1000x fewer queries!
"""
```

### Feature Detection

```python
# In AppConfig.ready()
from django.db import connection

def check_bulk_parent_support():
    """Check and log bulk parent insert support."""
    features = connection.features
    has_returning = getattr(features, 'can_return_rows_from_bulk_insert', False)
    
    if has_returning:
        logger.info(
            f"✓ Database supports RETURNING - MTI bulk creates will use "
            f"optimized path (O(k) queries instead of O(n*k))"
        )
    else:
        logger.warning(
            f"⚠ Database doesn't support RETURNING - MTI bulk creates will use "
            f"loop path (O(n*k) queries). Consider upgrading database for better performance."
        )
```

## 📚 API Summary

```python
# Package: django-bulk-lifecycle

# Core imports
from django_bulk_lifecycle import (
    BulkLifecycleModelMixin,    # Model mixin
    BulkLifecycleManager,        # Manager with hook support
    LifecycleHook,               # Base class for hook handlers
    hook,                        # @hook decorator (with on_commit support)
    
    # Constants
    BEFORE_CREATE, AFTER_CREATE,
    BEFORE_UPDATE, AFTER_UPDATE,
    BEFORE_DELETE, AFTER_DELETE,
    
    # Conditions (now use ChangeSet)
    WhenFieldHasChanged,
    WhenFieldValueIs,
    WhenFieldValueWas,
    
    # Data structures
    ChangeSet,                   # Efficient change tracking
    RecordChange,                # Per-record change info
    
    # Dispatcher (custom, not Django signals)
    HookDispatcher,              # Priority-based dispatcher
    HookRegistry,                # Hook registration
    
    # Factory & DI
    set_hook_factory,            # Register hook factory
    configure_hook_container,    # Wire to DI container
    create_hook_instance,        # Create with DI
    
    # Debug utilities
    track_queries,               # Query tracking decorator
    QueryTracker,                # Query tracking context manager
    assert_query_count,          # Test query assertions
    performance_monitor,         # Performance monitoring
    
    # Signals (optional compatibility)
    bulk_pre_create,
    bulk_post_create,
    bulk_pre_update,
    bulk_post_update,
    bulk_pre_delete,
    bulk_post_delete,
)
```

---

This plan provides a comprehensive roadmap for building `django-bulk-lifecycle` with **production-grade fixes** addressing all critical issues identified in review, plus the essential Factory/DI system, Debug utilities, and MTI bulk parent optimization from the current working implementation.

### To-dos

- [ ] Implement core Django signals (bulk_pre_create, bulk_post_update, etc.) and constants
- [ ] Create BulkLifecycleModelMixin with save/delete override and MTI hook cascading
- [ ] Build data access layer (RecordFetcher, FieldTracker, QueryOptimizer)
- [ ] Implement MTIHandler with inheritance chain detection and hook cascading logic
- [ ] Create @hook decorator and LifecycleHook base class with condition system
- [ ] Implement BulkLifecycleQuerySet and BulkLifecycleManager with MTI routing
- [ ] Build comprehensive test suite including MTI cascading tests
- [ ] Write documentation, API reference, and migration guide