
# django-bulk-hooks

⚡ Bulk hooks for Django bulk operations.

`django-bulk-hooks` brings a declarative, hook-like experience to Django's `bulk_create`, `bulk_update`, and `bulk_delete` — including support for `BEFORE_` and `AFTER_` hooks, conditions, batching, and transactional safety.

## ✨ Features

- Declarative hook system: `@hook(AFTER_UPDATE, condition=...)`
- BEFORE/AFTER hooks for create, update, delete
- Hook-aware manager that wraps Django's `bulk_` operations
- Hook chaining, hook deduplication, and atomicity
- Class-based hook handlers with DI support

## 🚀 Quickstart

```bash
pip install django-bulk-hooks
```

### Define Your Model

```python
from django.db import models
from django_bulk_hooks.manager import BulkHookManager

class Account(models.Model):
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    objects = BulkHookManager()
```

### Create a Hook Handler

```python
from django_bulk_hooks import hook, AFTER_UPDATE, HookHandler
from django_bulk_hooks.conditions import WhenFieldHasChanged
from .models import Account

class AccountHookHandler(HookHandler):
    @hook(AFTER_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    def log_balance_change(self, new_objs):
        print("Accounts updated:", [a.pk for a in new_objs])
```

## 🛠 Supported Hook Events

- `BEFORE_CREATE`, `AFTER_CREATE`
- `BEFORE_UPDATE`, `AFTER_UPDATE`
- `BEFORE_DELETE`, `AFTER_DELETE`

## 🧠 Why?

Django's `bulk_` methods bypass signals and `save()`. This package fills that gap with:

- Hooks that behave consistently across creates/updates/deletes
- Scalable performance via chunking (default 200)
- Support for `@hook` decorators and centralized hook classes

## 📦 Usage in Views / Commands

```python
# Calls AFTER_UPDATE hooks automatically
Account.objects.bulk_update(accounts, ['balance'])

# Triggers BEFORE_CREATE and AFTER_CREATE hooks
Account.objects.bulk_create(accounts)
```

## 🧩 Integration with Queryable Properties

You can extend from `BulkHookManager` to support formula fields or property querying.

```python
class MyManager(BulkHookManager, QueryablePropertiesManager):
    pass
```

## 📝 License

MIT © 2024 Augend / Konrad Beck
