
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
from django_bulk_hooks import hook, AFTER_UPDATE, Hook
from django_bulk_hooks.conditions import WhenFieldHasChanged
from .models import Account

class AccountHooks(HookHandler):
    @hook(AFTER_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    def log_balance_change(self, new_records, old_records):
        print("Accounts updated:", [a.pk for a in new_records])
    
    @hook(BEFORE_CREATE, model=Account)
    def before_create(self, new_records, old_records):
        for account in new_records:
            if account.balance < 0:
                raise ValueError("Account cannot have negative balance")
    
    @hook(AFTER_DELETE, model=Account)
    def after_delete(self, new_records, old_records):
        print("Accounts deleted:", [a.pk for a in old_records])
```

### Advanced Hook Usage

```python
class AdvancedAccountHooks(HookHandler):
    @hook(BEFORE_UPDATE, model=Account, condition=WhenFieldHasChanged("balance"))
    def validate_balance_change(self, new_records, old_records):
        for new_account, old_account in zip(new_records, old_records):
            if new_account.balance < 0 and old_account.balance >= 0:
                raise ValueError("Cannot set negative balance")
    
    @hook(AFTER_CREATE, model=Account)
    def send_welcome_email(self, new_records, old_records):
        for account in new_records:
            # Send welcome email logic here
            pass
```

## 🔒 Safely Handling Related Objects

One of the most common issues when working with hooks is the `RelatedObjectDoesNotExist` exception. This occurs when you try to access a related object that doesn't exist or hasn't been saved yet.

### The Problem

```python
# ❌ DANGEROUS: This can raise RelatedObjectDoesNotExist
@hook(AFTER_CREATE, model=Transaction)
def process_transaction(self, new_records, old_records):
    for transaction in new_records:
        # This will fail if transaction.status is None or doesn't exist
        if transaction.status.name == "COMPLETE":
            # Process the transaction
            pass
```

### The Solution

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
from django_bulk_hooks import hook
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
    def process_transactions(self, new_records, old_records=None):
        """Process transactions based on their status."""
        for transaction in new_records:
            # ✅ SAFE: Get status name safely
            status_name = safe_get_related_attr(transaction, 'status', 'name')
            
            if status_name == "COMPLETE":
                self._process_complete_transaction(transaction)
            elif status_name == "FAILED":
                self._process_failed_transaction(transaction)
            elif status_name is None:
                print(f"Transaction {transaction.id} has no status")
            
            # ✅ SAFE: Check for related object existence
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

1. **Always use `safe_get_related_attr`** when accessing related object attributes in hooks
2. **Set default values in `BEFORE_CREATE` hooks** to ensure related objects exist
3. **Handle None cases explicitly** to avoid unexpected behavior
4. **Use bulk operations efficiently** by fetching related objects once and reusing them

```python
class EfficientTransactionHandler:
    @hook(Transaction, "before_create")
    def prepare_transactions(self, new_records, old_records=None):
        """Efficiently prepare transactions for bulk creation."""
        # Get default objects once to avoid multiple queries
        default_status = Status.objects.filter(name="PENDING").first()
        default_category = Category.objects.filter(name="GENERAL").first()
        
        for transaction in new_records:
            if transaction.status is None:
                transaction.status = default_status
            if transaction.category is None:
                transaction.category = default_category
    
    @hook(Transaction, "after_create")
    def post_creation_processing(self, new_records, old_records=None):
        """Process transactions after creation."""
        # Group by status for efficient processing
        transactions_by_status = {}
        
        for transaction in new_records:
            status_name = safe_get_related_attr(transaction, 'status', 'name')
            if status_name not in transactions_by_status:
                transactions_by_status[status_name] = []
            transactions_by_status[status_name].append(transaction)
        
        # Process each group
        for status_name, transactions in transactions_by_status.items():
            if status_name == "COMPLETE":
                self._batch_process_complete(transactions)
            elif status_name == "FAILED":
                self._batch_process_failed(transactions)
```

This approach ensures your hooks are robust and won't fail due to missing related objects, while also being efficient with database queries.