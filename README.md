
# django-bulk-triggers

⚡ Bulk triggers for Django bulk operations and individual model lifecycle events.

`django-bulk-triggers` brings a declarative, trigger-like experience to Django's `bulk_create`, `bulk_update`, and `bulk_delete` — including support for `BEFORE_` and `AFTER_` triggers, conditions, batching, and transactional safety. It also provides comprehensive lifecycle triggers for individual model operations.

## ✨ Features

- Declarative trigger system: `@trigger(AFTER_UPDATE, condition=...)`
- BEFORE/AFTER triggers for create, update, delete
- Trigger-aware manager that wraps Django's `bulk_` operations
- **NEW**: `TriggerModelMixin` for individual model lifecycle events
- Trigger chaining, trigger deduplication, and atomicity
- Class-based trigger handlers with DI support
- Support for both bulk and individual model operations

## 🚀 Quickstart

```bash
pip install django-bulk-triggers
```

### Define Your Model

```python
from django.db import models
from django_bulk_triggers.models import TriggerModelMixin

class Account(TriggerModelMixin):
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    # The TriggerModelMixin automatically provides BulkTriggerManager
```

### Create a Trigger Handler

```python
from django_bulk_triggers import trigger, AFTER_UPDATE, Trigger
from django_bulk_triggers.conditions import WhenFieldHasChanged
from .models import Account

class AccountTriggers(Trigger):
    @trigger(AFTER_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    def log_balance_change(self, new_records, old_records):
        print("Accounts updated:", [a.pk for a in new_records])
    
    @trigger(BEFORE_CREATE, model=Account)
    def before_create(self, new_records, old_records):
        for account in new_records:
            if account.balance < 0:
                raise ValueError("Account cannot have negative balance")
    
    @trigger(AFTER_DELETE, model=Account)
    def after_delete(self, new_records, old_records):
        print("Accounts deleted:", [a.pk for a in old_records])
```

## 🛠 Supported Trigger Events

- `BEFORE_CREATE`, `AFTER_CREATE`
- `BEFORE_UPDATE`, `AFTER_UPDATE`
- `BEFORE_DELETE`, `AFTER_DELETE`

## 🔄 Lifecycle Events

### Individual Model Operations

The `TriggerModelMixin` automatically triggers triggers for individual model operations:

```python
# These will trigger BEFORE_CREATE and AFTER_CREATE triggers
account = Account.objects.create(balance=100.00)
account.save()  # for new instances

# These will trigger BEFORE_UPDATE and AFTER_UPDATE triggers
account.balance = 200.00
account.save()  # for existing instances

# This will trigger BEFORE_DELETE and AFTER_DELETE triggers
account.delete()
```

### Bulk Operations

Bulk operations also trigger the same triggers:

```python
# Bulk create - triggers BEFORE_CREATE and AFTER_CREATE triggers
accounts = [
    Account(balance=100.00),
    Account(balance=200.00),
]
Account.objects.bulk_create(accounts)

# Bulk update - triggers BEFORE_UPDATE and AFTER_UPDATE triggers
for account in accounts:
    account.balance *= 1.1
Account.objects.bulk_update(accounts)  # fields are auto-detected

# Bulk delete - triggers BEFORE_DELETE and AFTER_DELETE triggers
Account.objects.bulk_delete(accounts)
```

### Queryset Operations

Queryset operations are also supported:

```python
# Queryset update - triggers BEFORE_UPDATE and AFTER_UPDATE triggers
Account.objects.update(balance=0.00)

# Queryset delete - triggers BEFORE_DELETE and AFTER_DELETE triggers
Account.objects.delete()
```

### Subquery Support in Updates

When using `Subquery` objects in update operations, the computed values are automatically available in triggers. The system efficiently refreshes all instances in bulk for optimal performance:

```python
from django.db.models import Subquery, OuterRef, Sum

def aggregate_revenue_by_ids(self, ids: Iterable[int]) -> int:
    return self.find_by_ids(ids).update(
        revenue=Subquery(
            FinancialTransaction.objects.filter(daily_financial_aggregate_id=OuterRef("pk"))
            .filter(is_revenue=True)
            .values("daily_financial_aggregate_id")
            .annotate(revenue_sum=Sum("amount"))
            .values("revenue_sum")[:1],
        ),
    )

# In your triggers, you can now access the computed revenue value:
class FinancialAggregateTriggers(Trigger):
    @trigger(AFTER_UPDATE, model=DailyFinancialAggregate)
    def log_revenue_update(self, new_records, old_records):
        for new_record in new_records:
            # This will now contain the computed value, not the Subquery object
            print(f"Updated revenue: {new_record.revenue}")

# Bulk operations are optimized for performance:
def bulk_aggregate_revenue(self, ids: Iterable[int]) -> int:
    # This will efficiently refresh all instances in a single query
    return self.filter(id__in=ids).update(
        revenue=Subquery(
            FinancialTransaction.objects.filter(daily_financial_aggregate_id=OuterRef("pk"))
            .filter(is_revenue=True)
            .values("daily_financial_aggregate_id")
            .annotate(revenue_sum=Sum("amount"))
            .values("revenue_sum")[:1],
        ),
    )
```

## 🧠 Why?

Django's `bulk_` methods bypass signals and `save()`. This package fills that gap with:

- Triggers that behave consistently across creates/updates/deletes
- **NEW**: Individual model lifecycle triggers that work with `save()` and `delete()`
- Scalable performance via chunking (default 200)
- Support for `@trigger` decorators and centralized trigger classes
- **NEW**: Automatic trigger triggering for admin operations and other Django features
- **NEW**: Proper ordering guarantees for old/new record pairing in triggers (Salesforce-like behavior)

## 📦 Usage Examples

### Individual Model Operations

```python
# These automatically trigger triggers
account = Account.objects.create(balance=100.00)
account.balance = 200.00
account.save()
account.delete()
```

### Bulk Operations

```python
# These also trigger triggers
Account.objects.bulk_create(accounts)
Account.objects.bulk_update(accounts)  # fields are auto-detected
Account.objects.bulk_delete(accounts)
```

### Advanced Trigger Usage

```python
class AdvancedAccountTriggers(Trigger):
    @trigger(BEFORE_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    def validate_balance_change(self, new_records, old_records):
        for new_account, old_account in zip(new_records, old_records):
            if new_account.balance < 0 and old_account.balance >= 0:
                raise ValueError("Cannot set negative balance")
    
    @trigger(AFTER_CREATE, model=Account)
    def send_welcome_email(self, new_records, old_records):
        for account in new_records:
            # Send welcome email logic here
            pass
```

### Salesforce-like Ordering Guarantees

The system ensures that `old_records` and `new_records` are always properly paired, regardless of the order in which you pass objects to bulk operations:

```python
class LoanAccountTriggers(Trigger):
    @trigger(BEFORE_UPDATE, model=LoanAccount)
    def validate_account_number(self, new_records, old_records):
        # old_records[i] always corresponds to new_records[i]
        for new_account, old_account in zip(new_records, old_records):
            if old_account.account_number != new_account.account_number:
                raise ValidationError("Account number cannot be changed")

# This works correctly even with reordered objects:
accounts = [account1, account2, account3]  # IDs: 1, 2, 3
reordered = [account3, account1, account2]  # IDs: 3, 1, 2

# The trigger will still receive properly paired old/new records
LoanAccount.objects.bulk_update(reordered)  # fields are auto-detected
```

## 🧩 Integration with Other Managers

You can extend from `BulkTriggerManager` to work with other manager classes. The manager uses a cooperative approach that dynamically injects bulk trigger functionality into any queryset, ensuring compatibility with other managers.

```python
from django_bulk_triggers.manager import BulkTriggerManager
from queryable_properties.managers import QueryablePropertiesManager

class MyManager(BulkTriggerManager, QueryablePropertiesManager):
    pass
```

This approach uses the industry-standard injection pattern, similar to how `QueryablePropertiesManager` works, ensuring both functionalities work seamlessly together without any framework-specific knowledge.

Framework needs to:
Register these methods
Know when to execute them (BEFORE_UPDATE, AFTER_UPDATE)
Execute them in priority order
Pass ChangeSet to them
Handle errors (rollback on failure)

## 📝 License

MIT © 2024 Augend / Konrad Beck
