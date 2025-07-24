
# django-bulk-hooks

⚡ Bulk hooks for Django bulk operations and individual model lifecycle events.

`django-bulk-hooks` brings a declarative, hook-like experience to Django's `bulk_create`, `bulk_update`, and `bulk_delete` — including support for `BEFORE_` and `AFTER_` hooks, conditions, batching, and transactional safety. It also provides comprehensive lifecycle hooks for individual model operations.

## ✨ Features

- Declarative hook system: `@hook(AFTER_UPDATE, condition=...)`
- BEFORE/AFTER hooks for create, update, delete
- Hook-aware manager that wraps Django's `bulk_` operations
- **NEW**: `HookModelMixin` for individual model lifecycle events
- Hook chaining, hook deduplication, and atomicity
- Class-based hook handlers with DI support
- Support for both bulk and individual model operations
- **NEW**: Safe handling of related objects to prevent `RelatedObjectDoesNotExist` errors
- **NEW**: `@select_related` decorator to prevent queries in loops

## 🚀 Quickstart

```bash
pip install django-bulk-hooks
```

### Define Your Model

```python
from django.db import models
from django_bulk_hooks.models import HookModelMixin

class Account(HookModelMixin):
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    # The HookModelMixin automatically provides BulkHookManager
```

### Create a Hook Handler

```python
from django_bulk_hooks import hook, AFTER_UPDATE, select_related
from django_bulk_hooks.conditions import WhenFieldHasChanged
from .models import Account

class AccountHandler:
    @hook(AFTER_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    @select_related("user")  # Preload user to prevent queries in loops
    def notify_balance_change(self, new_records, old_records):
        for account in new_records:
            # This won't cause a query since user is preloaded
            user_email = account.user.email
            self.send_notification(user_email, account.balance)
```

## 🔧 Using `@select_related` to Prevent Queries in Loops

The `@select_related` decorator is essential when your hook logic needs to access related objects. Without it, you might end up with N+1 query problems.

### ❌ Without `@select_related` (causes queries in loops)

```python
@hook(AFTER_CREATE, model=LoanAccount)
def process_accounts(self, new_records, old_records):
    for account in new_records:
        # ❌ This causes a query for each account!
        status_name = account.status.name
        if status_name == "ACTIVE":
            self.activate_account(account)
```

### ✅ With `@select_related` (bulk loads related objects)

```python
@hook(AFTER_CREATE, model=LoanAccount)
@select_related("status")  # Bulk load status objects
def process_accounts(self, new_records, old_records):
    for account in new_records:
        # ✅ No query here - status is preloaded
        status_name = account.status.name
        if status_name == "ACTIVE":
            self.activate_account(account)
```

### Multiple Related Fields

```python
@hook(AFTER_UPDATE, model=Transaction)
@select_related("account", "category", "status")
def process_transactions(self, new_records, old_records):
    for transaction in new_records:
        # All related objects are preloaded - no queries in loops
        account_name = transaction.account.name
        category_type = transaction.category.type
        status_name = transaction.status.name
        
        if status_name == "COMPLETE":
            self.process_complete_transaction(transaction)
```

### Your Original Example (Fixed)

```python
@hook(BEFORE_CREATE, model=LoanAccount, condition=IsEqual("status.name", value=Status.ACTIVE.value))
@hook(
    BEFORE_UPDATE,
    model=LoanAccount,
    condition=HasChanged("status", has_changed=True) & IsEqual("status.name", value=Status.ACTIVE.value),
    priority=Priority.HIGH,
)
@select_related("status")  # This ensures status is preloaded
def _set_activated_date(self, old_records: list[LoanAccount], new_records: list[LoanAccount], **kwargs) -> None:
    logger.info(f"Setting activated date for {new_records}")
    # No queries in loops - status objects are preloaded
    self._loan_account_service.set_activated_date(new_records)
```

## 🛡️ Safe Handling of Related Objects

Use the `safe_get_related_attr` utility function to safely access related object attributes:

```python
from django_bulk_hooks.conditions import safe_get_related_attr

# ✅ SAFE: Use safe_get_related_attr to handle None values
@hook(AFTER_CREATE, model=Transaction)
def process_transaction(self, new_records, old_records):
    for transaction in new_records:
        # Safely get the status name, returns None if status doesn't exist
        status_name = safe_get_related_attr(transaction, 'status', 'name')
        
        if status_name == "COMPLETE":
            # Process the transaction
            pass
        elif status_name is None:
            # Handle case where status is not set
            print(f"Transaction {transaction.id} has no status")
```

### Complete Example

```python
from django.db import models
from django_bulk_hooks import hook, select_related
from django_bulk_hooks.conditions import safe_get_related_attr

class Status(models.Model):
    name = models.CharField(max_length=50)

class Transaction(HookModelMixin, models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.ForeignKey(Status, on_delete=models.CASCADE, null=True, blank=True)
    category = models.ForeignKey('Category', on_delete=models.CASCADE, null=True, blank=True)

class TransactionHandler:
    @hook(Transaction, "before_create")
    def set_default_status(self, new_records, old_records=None):
        """Set default status for new transactions."""
        default_status = Status.objects.filter(name="PENDING").first()
        for transaction in new_records:
            if transaction.status is None:
                transaction.status = default_status
    
    @hook(Transaction, "after_create")
    @select_related("status", "category")  # Preload related objects
    def process_transactions(self, new_records, old_records=None):
        """Process transactions based on their status."""
        for transaction in new_records:
            # ✅ SAFE: Get status name safely (no queries in loops)
            status_name = safe_get_related_attr(transaction, 'status', 'name')
            
            if status_name == "COMPLETE":
                self._process_complete_transaction(transaction)
            elif status_name == "FAILED":
                self._process_failed_transaction(transaction)
            elif status_name is None:
                print(f"Transaction {transaction.id} has no status")
            
            # ✅ SAFE: Check for related object existence (no queries in loops)
            category = safe_get_related_attr(transaction, 'category')
            if category:
                print(f"Transaction {transaction.id} belongs to category: {category.name}")
    
    def _process_complete_transaction(self, transaction):
        # Process complete transaction logic
        pass
    
    def _process_failed_transaction(self, transaction):
        # Process failed transaction logic
        pass
```

### Best Practices for Related Objects

1. **Always use `@select_related`** when accessing related object attributes in hooks
2. **Use `safe_get_related_attr`** for safe access to related object attributes
3. **Set default values in `BEFORE_CREATE` hooks** to ensure related objects exist
4. **Handle None cases explicitly** to avoid unexpected behavior
5. **Use bulk operations efficiently** by fetching related objects once and reusing them

## 🔍 Performance Tips

### Monitor Query Count

```python
from django.db import connection, reset_queries

# Before your bulk operation
reset_queries()

# Your bulk operation
accounts = Account.objects.bulk_create(account_list)

# After your bulk operation
print(f"Total queries: {len(connection.queries)}")
```

### Use `@select_related` Strategically

```python
# Only select_related fields you actually use
@select_related("status")  # Good - only what you need
@select_related("status", "category", "user", "account")  # Only if you use all of them
```

### Avoid Nested Loops with Related Objects

```python
# ❌ Bad - nested loops with related objects
@hook(AFTER_CREATE, model=Order)
def process_orders(self, new_records, old_records):
    for order in new_records:
        for item in order.items.all():  # This causes queries!
            process_item(item)

# ✅ Good - use prefetch_related for many-to-many/one-to-many
@hook(AFTER_CREATE, model=Order)
@select_related("customer")
def process_orders(self, new_records, old_records):
    # Prefetch items for all orders at once
    from django.db.models import Prefetch
    orders_with_items = Order.objects.prefetch_related(
        Prefetch('items', queryset=Item.objects.select_related('product'))
    ).filter(id__in=[order.id for order in new_records])
    
    for order in orders_with_items:
        for item in order.items.all():  # No queries here
            process_item(item)
```

## 📚 API Reference

### Decorators

- `@hook(event, model, condition=None, priority=DEFAULT_PRIORITY)` - Register a hook
- `@select_related(*fields)` - Preload related fields to prevent queries in loops

### Conditions

- `IsEqual(field, value)` - Check if field equals value
- `HasChanged(field, has_changed=True)` - Check if field has changed
- `safe_get_related_attr(instance, field, attr=None)` - Safely get related object attributes

### Events

- `BEFORE_CREATE`, `AFTER_CREATE`
- `BEFORE_UPDATE`, `AFTER_UPDATE`
- `BEFORE_DELETE`, `AFTER_DELETE`
- `VALIDATE_CREATE`, `VALIDATE_UPDATE`, `VALIDATE_DELETE`

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
