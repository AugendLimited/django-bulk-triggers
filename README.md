
# django-bulk-lifecycle

⚡ Salesforce-style lifecycle hooks for Django bulk operations.

`django-bulk-lifecycle` brings a declarative, trigger-like experience to Django's `bulk_create`, `bulk_update`, and `bulk_delete` — including support for `BEFORE_` and `AFTER_` hooks, conditions, batching, and transactional safety.

## ✨ Features

- Declarative hook system: `@hook(AFTER_UPDATE, condition=...)`
- BEFORE/AFTER hooks for create, update, delete
- Salesforce-style semantics with full batch support
- Lifecycle-aware manager that wraps Django’s `bulk_` operations
- Hook chaining, trigger deduplication, and atomicity
- Class-based hook handlers with DI support

## 🚀 Quickstart

```bash
pip install django-bulk-lifecycle
```

### Define Your Model

```python
from django.db import models
from django_bulk_lifecycle.manager import BulkLifecycleManager

class Account(models.Model):
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    objects = BulkLifecycleManager()
```

### Create a Trigger Handler

```python
from django_bulk_lifecycle import hook, AFTER_UPDATE, TriggerHandler
from django_bulk_lifecycle.conditions import WhenFieldHasChanged
from .models import Account

class AccountTriggerHandler(TriggerHandler):
    @hook(AFTER_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    def log_balance_change(self, new_objs):
        print("Accounts updated:", [a.pk for a in new_objs])
```

## 🛠 Supported Lifecycle Events

- `BEFORE_INSERT`, `AFTER_INSERT`
- `BEFORE_UPDATE`, `AFTER_UPDATE`
- `BEFORE_DELETE`, `AFTER_DELETE`

## 🧠 Why?

Django’s `bulk_` methods bypass signals and `save()`. This package fills that gap with:

- Triggers that behave consistently across inserts/updates/deletes
- Scalable performance via chunking (default 200)
- Support for `@hook` decorators and centralized trigger classes

## 📦 Usage in Views / Commands

```python
# Calls AFTER_UPDATE hooks automatically
Account.objects.bulk_update(accounts, ['balance'])

# Triggers BEFORE_INSERT and AFTER_INSERT
Account.objects.bulk_create(accounts)
```

## 🧩 Integration with Queryable Properties

You can extend from `BulkLifecycleManager` to support formula fields or property querying.

```python
class MyManager(BulkLifecycleManager, QueryablePropertiesManager):
    pass
```

## 📝 License

MIT © 2024 Augend / Konrad Beck
