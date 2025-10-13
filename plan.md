# 🚀 `django-bulk-signals` V2.1 - Implementation Plan

## 📋 Project Overview

**Goal**: Create a clean, performant, and maintainable framework that provides reliable signals for all Django ORM operations, including bulk methods and Multi-Table Inheritance (MTI).

**Core Principle**: Single Responsibility - The framework provides signals, business logic stays in signal receivers.

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Signal Layer (Clean API)                 │
├─────────────────────────────────────────────────────────────┤
│  BulkSignalModelMixin  │  BulkSignalManager  │  Signals     │
├─────────────────────────────────────────────────────────────┤
│                Operation Interceptors                       │
├─────────────────────────────────────────────────────────────┤
│  CreateInterceptor │ UpdateInterceptor │ DeleteInterceptor  │
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
django_bulk_signals/
├── __init__.py                 # Public API exports
├── signals.py                  # Signal definitions
├── mixins.py                   # BulkSignalModelMixin
├── managers.py                 # BulkSignalManager
├── querysets.py                # BulkSignalQuerySet
├── interceptors/               # Operation interceptors
│   ├── __init__.py
│   ├── base.py                 # BaseInterceptor
│   ├── create.py               # CreateInterceptor
│   ├── update.py               # UpdateInterceptor
│   └── delete.py               # DeleteInterceptor
├── data_access/                # Data access layer
│   ├── __init__.py
│   ├── record_fetcher.py       # RecordFetcher
│   ├── field_tracker.py        # FieldTracker
│   ├── mti_handler.py          # MTIHandler
│   └── query_optimizer.py      # QueryOptimizer
├── utils/                      # Utility functions
│   ├── __init__.py
│   ├── warnings.py             # Salesforce-style warnings
│   └── helpers.py              # Helper functions
└── exceptions.py               # Custom exceptions
```

## 🎯 Core Interfaces

### 1. Signal Interface
```python
# signals.py
from django.dispatch import Signal

# Clean, consistent signal API
bulk_pre_create = Signal()
bulk_post_create = Signal()
bulk_pre_update = Signal()
bulk_post_update = Signal()
bulk_pre_delete = Signal()
bulk_post_delete = Signal()

# Signal payload structure (consistent across all)
# sender: Model class
# new_records: List[Model instances]
# old_records: List[Model instances] (empty for creates)
# update_fields: List[str] | None
# operation_meta: Dict with additional context
```

### 2. Constants Interface
```python
# constants.py
# Event constants
BEFORE_CREATE = "before_create"
AFTER_CREATE = "after_create"
BEFORE_UPDATE = "before_update"
AFTER_UPDATE = "after_update"
BEFORE_DELETE = "before_delete"
AFTER_DELETE = "after_delete"

# Validation constants
VALIDATE_CREATE = "validate_create"
VALIDATE_UPDATE = "validate_update"
VALIDATE_DELETE = "validate_delete"
```

### 3. Priority Interface
```python
# enums.py
from enum import IntEnum

class Priority(IntEnum):
    """Named priorities for signal receivers."""
    HIGHEST = 0    # runs first
    HIGH = 25      # runs early
    NORMAL = 50    # default ordering
    LOW = 75       # runs late
    LOWEST = 100   # runs last

DEFAULT_PRIORITY = Priority.NORMAL
```

### 4. Model Mixin Interface
```python
# mixins.py
class BulkSignalModelMixin(models.Model):
    """Clean, simple mixin that adds signal support to models."""
    
    objects = BulkSignalManager()
    
    class Meta:
        abstract = True
    
    def clean(self, bypass_signals=False):
        """Override clean() to trigger validation signals."""
        super().clean()
        
        if bypass_signals:
            return
        
        # Determine if this is a create or update operation
        is_create = self.pk is None
        
        if is_create:
            # Fire validation signal for create
            bulk_validate_create.send(sender=self.__class__, new_records=[self])
        else:
            # Fire validation signal for update
            bulk_validate_update.send(sender=self.__class__, new_records=[self])
    
    def save(self, update_fields=None, bypass_signals=False, *args, **kwargs):
        """Override save to fire signals with proper field tracking."""
        if self.pk is None:
            # Create operation
            bulk_pre_create.send(sender=self.__class__, new_records=[self])
            result = super().save(update_fields, *args, **kwargs)
            bulk_post_create.send(sender=self.__class__, new_records=[self])
        else:
            # Update operation
            # Auto-detect changed fields if not provided
            if update_fields is None:
                update_fields = self._get_changed_fields()
            
            bulk_pre_update.send(
                sender=self.__class__, 
                new_records=[self], 
                old_records=[self._get_original_instance()],
                update_fields=update_fields
            )
            result = super().save(update_fields, *args, **kwargs)
            bulk_post_update.send(
                sender=self.__class__, 
                new_records=[self], 
                old_records=[self._get_original_instance()],
                update_fields=update_fields
            )
        return result
    
    def delete(self, bypass_signals=False, *args, **kwargs):
        """Override delete to fire signals."""
        if not bypass_signals:
            bulk_pre_delete.send(
                sender=self.__class__, 
                new_records=[], 
                old_records=[self]
            )
        
        result = super().delete(*args, **kwargs)
        
        if not bypass_signals:
            bulk_post_delete.send(
                sender=self.__class__, 
                new_records=[], 
                old_records=[self]
            )
        
        return result
    
    def _get_changed_fields(self):
        """Get list of changed fields using proper field comparison."""
        # Implementation in FieldTracker
        pass
    
    def _get_original_instance(self):
        """Get original instance for comparison."""
        # Implementation in FieldTracker
        pass
```

### 5. Manager Interface
```python
# managers.py
class BulkSignalManager(models.Manager):
    """Manager that provides signal-aware bulk operations."""
    
    def get_queryset(self):
        """Return optimized queryset with signal support."""
        return BulkSignalQuerySet(self.model, using=self._db)
    
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, 
                   update_conflicts=False, update_fields=None, unique_fields=None,
                   bypass_signals=False, bypass_validation=False, **kwargs):
        """Delegate to queryset with proper signal handling."""
        return self.get_queryset().bulk_create(
            objs, 
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            bypass_signals=bypass_signals,
            bypass_validation=bypass_validation,
            **kwargs
        )
    
    def bulk_update(self, objs, fields=None, bypass_signals=False, 
                   bypass_validation=False, **kwargs):
        """Delegate to queryset with proper signal handling."""
        return self.get_queryset().bulk_update(
            objs, 
            fields=fields,
            bypass_signals=bypass_signals,
            bypass_validation=bypass_validation,
            **kwargs
        )
    
    def bulk_delete(self, objs, batch_size=None, bypass_signals=False,
                   bypass_validation=False, **kwargs):
        """Delegate to queryset with proper signal handling."""
        return self.get_queryset().bulk_delete(
            objs,
            batch_size=batch_size,
            bypass_signals=bypass_signals,
            bypass_validation=bypass_validation,
            **kwargs
        )
```

### 6. QuerySet Interface
```python
# querysets.py
class BulkSignalQuerySet(models.QuerySet):
    """QuerySet with signal support for bulk operations."""
    
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                   update_conflicts=False, update_fields=None, unique_fields=None,
                   bypass_signals=False, bypass_validation=False, **kwargs):
        """Override bulk_create with signal support."""
        if not bypass_signals:
            # Fire pre-signal
            bulk_pre_create.send(sender=self.model, new_records=objs)
        
        # Execute operation
        result = super().bulk_create(
            objs, 
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            **kwargs
        )
        
        if not bypass_signals:
            # Fire post-signal
            bulk_post_create.send(sender=self.model, new_records=objs)
        
        return result
    
    def bulk_update(self, objs, fields=None, bypass_signals=False,
                   bypass_validation=False, **kwargs):
        """Override bulk_update with signal support."""
        # Auto-detect fields if not provided
        if fields is None:
            fields = self._detect_changed_fields(objs)
        
        # Get old records for comparison
        old_records = self._get_old_records(objs)
        
        if not bypass_signals:
            # Fire pre-signal
            bulk_pre_update.send(
                sender=self.model, 
                new_records=objs, 
                old_records=old_records,
                update_fields=fields
            )
        
        # Execute operation
        result = super().bulk_update(objs, fields=fields, **kwargs)
        
        if not bypass_signals:
            # Fire post-signal
            bulk_post_update.send(
                sender=self.model, 
                new_records=objs, 
                old_records=old_records,
                update_fields=fields
            )
        
        return result
    
    def bulk_delete(self, objs, batch_size=None, bypass_signals=False,
                   bypass_validation=False, **kwargs):
        """Override bulk_delete with signal support."""
        if not bypass_signals:
            # Fire pre-signal
            bulk_pre_delete.send(sender=self.model, new_records=[], old_records=objs)
        
        # Execute operation
        result = super().bulk_delete(objs, batch_size=batch_size, **kwargs)
        
        if not bypass_signals:
            # Fire post-signal
            bulk_post_delete.send(sender=self.model, new_records=[], old_records=objs)
        
        return result
    
    def update(self, **kwargs):
        """Override update with signal support."""
        # Get instances before update
        instances = list(self)
        if not instances:
            return 0
        
        # Get old records for comparison
        old_records = self._get_old_records(instances)
        
        # Fire pre-signal
        bulk_pre_update.send(
            sender=self.model, 
            new_records=instances, 
            old_records=old_records,
            update_fields=list(kwargs.keys())
        )
        
        # Execute operation
        result = super().update(**kwargs)
        
        # Get updated instances
        updated_instances = list(self.model.objects.filter(pk__in=[obj.pk for obj in instances]))
        
        # Fire post-signal
        bulk_post_update.send(
            sender=self.model, 
            new_records=updated_instances, 
            old_records=old_records,
            update_fields=list(kwargs.keys())
        )
        
        return result
    
    def delete(self):
        """Override delete with signal support."""
        # Get instances before delete
        instances = list(self)
        if not instances:
            return 0
        
        # Fire pre-signal
        bulk_pre_delete.send(sender=self.model, new_records=[], old_records=instances)
        
        # Execute operation
        result = super().delete()
        
        # Fire post-signal
        bulk_post_delete.send(sender=self.model, new_records=[], old_records=instances)
        
        return result
    
    def _detect_changed_fields(self, objs):
        """Auto-detect which fields have changed."""
        # Implementation in FieldTracker
        pass
    
    def _get_old_records(self, objs):
        """Get old records for comparison."""
        # Implementation in RecordFetcher
        pass
```

## 🔧 Interceptor Interfaces

### 1. Base Interceptor
```python
# interceptors/base.py
from abc import ABC, abstractmethod

class BaseInterceptor(ABC):
    """Base class for all operation interceptors."""
    
    def __init__(self, model_cls, signal_manager, record_fetcher):
        self.model_cls = model_cls
        self.signal_manager = signal_manager
        self.record_fetcher = record_fetcher
    
    @abstractmethod
    def intercept(self, operation, instances, **kwargs):
        """Intercept and handle the operation."""
        pass
```

### 2. Create Interceptor
```python
# interceptors/create.py
class CreateInterceptor(BaseInterceptor):
    """Handles all create operations (save, bulk_create)."""
    
    def intercept(self, operation, instances, **kwargs):
        """Intercept create operation."""
        if operation == 'save':
            return self._intercept_save(instances, **kwargs)
        elif operation == 'bulk_create':
            return self._intercept_bulk_create(instances, **kwargs)
    
    def _intercept_save(self, instance, **kwargs):
        """Intercept single instance save."""
        pass
    
    def _intercept_bulk_create(self, instances, **kwargs):
        """Intercept bulk_create operation."""
        pass
```

### 3. Update Interceptor
```python
# interceptors/update.py
class UpdateInterceptor(BaseInterceptor):
    """Handles all update operations (save, bulk_update, queryset.update)."""
    
    def intercept(self, operation, instances, **kwargs):
        """Intercept update operation."""
        if operation == 'save':
            return self._intercept_save(instances, **kwargs)
        elif operation == 'bulk_update':
            return self._intercept_bulk_update(instances, **kwargs)
        elif operation == 'queryset_update':
            return self._intercept_queryset_update(instances, **kwargs)
    
    def _intercept_save(self, instance, **kwargs):
        """Intercept single instance save for updates."""
        pass
    
    def _intercept_bulk_update(self, instances, **kwargs):
        """Intercept bulk_update operation."""
        pass
    
    def _intercept_queryset_update(self, queryset, **kwargs):
        """Intercept queryset.update() operation."""
        pass
```

### 4. Delete Interceptor
```python
# interceptors/delete.py
class DeleteInterceptor(BaseInterceptor):
    """Handles all delete operations (delete, bulk_delete, queryset.delete)."""
    
    def intercept(self, operation, instances, **kwargs):
        """Intercept delete operation."""
        if operation == 'delete':
            return self._intercept_delete(instances, **kwargs)
        elif operation == 'bulk_delete':
            return self._intercept_bulk_delete(instances, **kwargs)
        elif operation == 'queryset_delete':
            return self._intercept_queryset_delete(instances, **kwargs)
    
    def _intercept_delete(self, instance, **kwargs):
        """Intercept single instance delete."""
        pass
    
    def _intercept_bulk_delete(self, instances, **kwargs):
        """Intercept bulk_delete operation."""
        pass
    
    def _intercept_queryset_delete(self, queryset, **kwargs):
        """Intercept queryset.delete() operation."""
        pass
```

## 🗄️ Data Access Interfaces

### 1. Record Fetcher
```python
# data_access/record_fetcher.py
class RecordFetcher:
    """Efficiently fetches records with proper optimization."""
    
    def __init__(self, model_cls):
        self.model_cls = model_cls
    
    def fetch_old_records(self, pks):
        """Fetch old records for comparison - single query."""
        pass
    
    def fetch_new_records(self, pks):
        """Fetch new records after operation - single query."""
        pass
    
    def fetch_with_relationships(self, pks, relationships):
        """Fetch records with specific relationships preloaded."""
        pass
```

### 2. Field Tracker
```python
# data_access/field_tracker.py
class FieldTracker:
    """Handles field change detection without N+1 queries."""
    
    def __init__(self, instance):
        self.instance = instance
        self._original_values = self._snapshot_fields()
    
    def _snapshot_fields(self):
        """Snapshot field values on initialization."""
        pass
    
    def get_changed_fields(self):
        """Get list of changed fields using proper field comparison."""
        pass
    
    def has_field_changed(self, field_name):
        """Check if specific field has changed."""
        pass
```

### 3. MTI Handler
```python
# data_access/mti_handler.py
class MTIHandler:
    """Handles Multi-Table Inheritance properly."""
    
    def __init__(self, model_cls):
        self.model_cls = model_cls
        self.parent_models = self._get_parent_models()
    
    def get_inheritance_chain(self):
        """Get the complete inheritance chain."""
        pass
    
    def split_update_fields(self, update_fields):
        """Split update fields by model table."""
        pass
    
    def cascade_triggers(self, instances, event_type):
        """Handle trigger cascading for MTI."""
        pass
```

### 4. Query Optimizer
```python
# data_access/query_optimizer.py
class QueryOptimizer:
    """Optimizes queries to prevent N+1 problems."""
    
    def __init__(self, model_cls):
        self.model_cls = model_cls
    
    def optimize_queryset(self, queryset, operation_type):
        """Add appropriate select_related/prefetch_related."""
        pass
    
    def get_required_relationships(self, operation_type):
        """Determine which relationships need to be preloaded."""
        pass
    
    def batch_queries(self, queries):
        """Batch multiple queries efficiently."""
        pass
```

## 🚨 Warning System Interface

### 1. Salesforce-Style Warnings
```python
# utils/warnings.py
import warnings
from django.dispatch import Signal

class BulkSignal(Signal):
    """Custom signal that warns about multiple receivers."""
    
    def send(self, sender=None, **named):
        """Send signal with multiple receiver warning."""
        if sender and hasattr(sender, '_meta'):
            # Count receivers for this model
            receiver_count = len([r for r in self._live_receivers if r[1] == sender])
            
            if receiver_count > 1:
                warnings.warn(
                    f"Multiple bulk signal receivers ({receiver_count}) registered for {sender.__name__}. "
                    f"This is not recommended for performance reasons. "
                    f"Consider consolidating into a single receiver.",
                    UserWarning,
                    stacklevel=2
                )
        
        return super().send(sender, **named)
```

## 📝 Usage Examples

### 1. Basic Model Setup
```python
# models.py
from django.db import models
from django_bulk_signals import BulkSignalModelMixin

class Account(BulkSignalModelMixin):
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    name = models.CharField(max_length=100)
```

### 2. Signal Receivers
```python
# signals.py
from django.dispatch import receiver
from django_bulk_signals.signals import bulk_pre_create, bulk_post_update
from django_bulk_signals.models import Account

@receiver(bulk_pre_create, sender=Account)
def validate_account_creation(sender, new_records, old_records, **kwargs):
    """Validate account creation."""
    for account in new_records:
        if account.balance < 0:
            raise ValidationError("Account cannot have negative balance")

@receiver(bulk_post_update, sender=Account)
def audit_balance_changes(sender, new_records, old_records, **kwargs):
    """Audit balance changes."""
    for new_account, old_account in zip(new_records, old_records):
        if old_account.balance != new_account.balance:
            AuditLog.objects.create(
                model='Account',
                instance_id=new_account.pk,
                field='balance',
                old_value=old_account.balance,
                new_value=new_account.balance
            )
```

### 3. Operations
```python
# All of these will fire signals
account = Account.objects.create(balance=100.00)
account.balance = 200.00
account.save()

Account.objects.bulk_create([Account(balance=100), Account(balance=200)])
Account.objects.bulk_update(accounts, fields=['balance'])
Account.objects.update(balance=0.00)
account.delete()
Account.objects.delete()
```

## 🎯 Key Features from Current Codebase

### 1. **Auto Update Fields Detection**
- Automatically detect which fields have changed in bulk_update
- Use proper field comparison with `field.get_prep_value()`
- Handle auto_now fields automatically
- Support for custom pre_save fields

### 2. **Bypass Mechanisms**
- `bypass_signals=False` parameter for all operations
- `bypass_validation=False` parameter for validation triggers
- Context managers for temporary bypassing
- Clean separation between signal and validation bypassing

### 3. **Validation Triggers**
- Separate validation signals (VALIDATE_CREATE, VALIDATE_UPDATE, VALIDATE_DELETE)
- Integration with Django's `clean()` method
- Admin form validation support
- N+1 query prevention in validation

### 4. **Multi-Table Inheritance (MTI) Support**
- Proper handling of MTI models
- Cascade trigger firing (parent → child, child → parent)
- Field mapping per model table
- Instance hydration with select_related

### 5. **Subquery Support**
- Handle Django Subquery objects in updates
- Automatic instance refresh after Subquery updates
- Proper output_field handling
- Complex expression support (Case, When, etc.)

### 6. **Salesforce-like Ordering Guarantees**
- Proper pairing of old_records and new_records
- Order-independent bulk operations
- Consistent record ordering across operations

### 7. **Performance Optimizations**
- Query optimization with select_related
- Batch processing with configurable batch_size
- N+1 query prevention
- Efficient field change detection

## 🎯 Success Criteria

### Performance Targets:
- **Bulk Update**: <5 queries for 1000 records (vs current 214 for 100)
- **Bulk Delete**: <3 queries for 1000 records (vs current 105 for 100)
- **Memory Usage**: <20% overhead over vanilla Django
- **Latency**: <10% overhead over vanilla Django

### Code Quality:
- **Test Coverage**: >95%
- **Cyclomatic Complexity**: <10 per method
- **Coupling**: Loose coupling between components
- **Cohesion**: High cohesion within components

### Maintainability:
- **Single Responsibility**: Each class has one clear purpose
- **Dependency Injection**: All dependencies injected, not hardcoded
- **Interface Segregation**: Clean, focused interfaces
- **Open/Closed**: Easy to extend, hard to break

## 🚀 Implementation Phases

### Phase 1: Core Foundation (Week 1-2)
- [ ] Implement signal definitions and constants
- [ ] Create BulkSignalModelMixin with bypass support
- [ ] Build field tracking system with auto-detection
- [ ] Set up basic testing framework
- [ ] Implement validation signal integration

### Phase 2: Data Access Layer (Week 2-3)
- [ ] Implement RecordFetcher with query optimization
- [ ] Build FieldTracker with proper field comparison
- [ ] Create MTIHandler for inheritance support
- [ ] Add QueryOptimizer for N+1 prevention
- [ ] Implement Subquery support

### Phase 3: Manager & QuerySet (Week 3-4)
- [ ] Implement BulkSignalManager with all parameters
- [ ] Create BulkSignalQuerySet with signal support
- [ ] Add auto update_fields detection
- [ ] Implement bypass mechanisms
- [ ] Add Salesforce-style ordering guarantees

### Phase 4: Advanced Features (Week 4-5)
- [ ] Implement context managers for bypassing
- [ ] Add performance optimizations
- [ ] Create warning system for multiple receivers
- [ ] Add comprehensive error handling
- [ ] Implement transaction safety

### Phase 5: Testing & Polish (Week 5-6)
- [ ] Comprehensive test suite
- [ ] Performance benchmarking
- [ ] Documentation and examples
- [ ] Migration tools
- [ ] Final optimization

## 🔧 Key Architectural Decisions

### 1. **Dependency Injection Pattern**
```python
# Instead of tight coupling
class TriggerQuerySetMixin(BulkOperationsMixin, FieldOperationsMixin, ...):
    pass

# Use dependency injection
class BulkSignalQuerySet(models.QuerySet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._interceptors = self._create_interceptors()
        self._record_fetcher = RecordFetcher(self.model)
        self._query_optimizer = QueryOptimizer(self.model)
```

### 2. **Single Query Strategy**
```python
# Instead of multiple queries with select_related hacks
def update(self, **kwargs):
    instances = list(self.select_related(*fk_fields))  # Query 1
    originals = list(self.model._base_manager.filter(pk__in=pks))  # Query 2
    # ... more queries

# Use single optimized query
def update(self, **kwargs):
    instances = self._record_fetcher.fetch_instances(self)  # Single query
    originals = self._record_fetcher.fetch_old_records(instances)  # Single query
```

### 3. **Clean Signal API**
```python
# Instead of complex payloads
def run(model_cls, event, new_records, old_records=None, ctx=None):
    # Complex context handling

# Use simple, consistent API
def fire_signal(signal, sender, new_records, old_records, update_fields=None, **meta):
    signal.send(
        sender=sender,
        new_records=new_records,
        old_records=old_records,
        update_fields=update_fields,
        **meta
    )
```

## 📚 Documentation Plan

### 1. **API Reference**
- Signal definitions and payloads
- Model mixin usage
- Manager and QuerySet methods
- Interceptor interfaces

### 2. **Usage Guide**
- Basic setup and configuration
- Signal receiver examples
- Performance optimization tips
- Best practices

### 3. **Migration Guide**
- From current version
- From other frameworks
- Performance considerations

### 4. **Examples**
- Real-world usage scenarios
- Performance benchmarks
- Integration patterns

## 🧪 Testing Strategy

### 1. **Unit Tests**
- Signal firing and payloads
- Field change detection
- Query optimization
- MTI handling

### 2. **Integration Tests**
- End-to-end operations
- Performance benchmarks
- Error handling
- Transaction safety

### 3. **Performance Tests**
- Query count validation
- Memory usage monitoring
- Latency measurements
- Scalability testing

## 🎯 Next Steps

1. **Review and approve this plan**
2. **Start Phase 1 implementation**
3. **Set up development environment**
4. **Create initial test suite**
5. **Begin core signal implementation**

---

This plan provides a comprehensive roadmap for creating a clean, performant, and maintainable bulk signals framework that eliminates the N+1 query problems and architectural issues of the current implementation.
