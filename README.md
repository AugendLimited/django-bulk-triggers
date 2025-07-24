
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

## 🎯 Lambda Conditions and Anonymous Functions

`django-bulk-hooks` supports using anonymous functions (lambda functions) and custom callables as conditions, giving you maximum flexibility for complex filtering logic.

### Using LambdaCondition

The `LambdaCondition` class allows you to use lambda functions or any callable as a condition:

```python
from django_bulk_hooks import LambdaCondition

class ProductHandler:
    # Simple lambda condition
    @hook(Product, "after_create", condition=LambdaCondition(
        lambda instance: instance.price > 100
    ))
    def handle_expensive_products(self, new_records, old_records):
        """Handle products with price > 100"""
        for product in new_records:
            print(f"Expensive product: {product.name}")
    
    # Lambda with multiple conditions
    @hook(Product, "after_update", condition=LambdaCondition(
        lambda instance: instance.price > 50 and instance.is_active and instance.stock_quantity > 0
    ))
    def handle_available_expensive_products(self, new_records, old_records):
        """Handle active products with price > 50 and stock > 0"""
        for product in new_records:
            print(f"Available expensive product: {product.name}")
    
    # Lambda comparing with original instance
    @hook(Product, "after_update", condition=LambdaCondition(
        lambda instance, original: original and instance.price > original.price * 1.5
    ))
    def handle_significant_price_increases(self, new_records, old_records):
        """Handle products with >50% price increase"""
        for new_product, old_product in zip(new_records, old_records):
            if old_product:
                increase = ((new_product.price - old_product.price) / old_product.price) * 100
                print(f"Significant price increase: {new_product.name} +{increase:.1f}%")
```

### Combining Lambda Conditions with Built-in Conditions

You can combine lambda conditions with built-in conditions using the `&` (AND) and `|` (OR) operators:

```python
from django_bulk_hooks.conditions import HasChanged, IsEqual

class AdvancedProductHandler:
    # Combine lambda with built-in conditions
    @hook(Product, "after_update", condition=(
        HasChanged("price") & 
        LambdaCondition(lambda instance: instance.price > 100)
    ))
    def handle_expensive_price_changes(self, new_records, old_records):
        """Handle when expensive products have price changes"""
        for new_product, old_product in zip(new_records, old_records):
            print(f"Expensive product price changed: {new_product.name}")
    
    # Complex combined conditions
    @hook(Order, "after_update", condition=(
        LambdaCondition(lambda instance: instance.status == 'completed') &
        LambdaCondition(lambda instance, original: original and instance.total_amount > original.total_amount)
    ))
    def handle_completed_orders_with_increased_amount(self, new_records, old_records):
        """Handle completed orders that had amount increases"""
        for new_order, old_order in zip(new_records, old_records):
            if old_order:
                increase = new_order.total_amount - old_order.total_amount
                print(f"Completed order with amount increase: {new_order.customer_name} +${increase}")
```

### Custom Condition Classes

For reusable logic, you can create custom condition classes:

```python
from django_bulk_hooks.conditions import HookCondition

class IsPremiumProduct(HookCondition):
    def check(self, instance, original_instance=None):
        return (
            instance.price > 200 and 
            instance.rating >= 4.0 and 
            instance.is_active
        )
    
    def get_required_fields(self):
        return {'price', 'rating', 'is_active'}

class ProductHandler:
    @hook(Product, "after_create", condition=IsPremiumProduct())
    def handle_premium_products(self, new_records, old_records):
        """Handle premium products"""
        for product in new_records:
            print(f"Premium product: {product.name}")
```

### Lambda Conditions with Required Fields

For optimization, you can specify which fields your lambda condition depends on:

```python
class OptimizedProductHandler:
    @hook(Product, "after_update", condition=LambdaCondition(
        lambda instance: instance.price > 100 and instance.category == 'electronics',
        required_fields={'price', 'category'}
    ))
    def handle_expensive_electronics(self, new_records, old_records):
        """Handle expensive electronics products"""
        for product in new_records:
            print(f"Expensive electronics: {product.name}")
```

### Best Practices for Lambda Conditions

1. **Keep lambdas simple** - Complex logic should be moved to custom condition classes
2. **Handle None values** - Always check for None before performing operations
3. **Specify required fields** - This helps with query optimization
4. **Use descriptive names** - Make your lambda conditions self-documenting
5. **Test thoroughly** - Lambda conditions can be harder to debug than named functions

```python
# ✅ GOOD: Simple, clear lambda
condition = LambdaCondition(lambda instance: instance.price > 100)

# ✅ GOOD: Handles None values
condition = LambdaCondition(
    lambda instance: instance.price is not None and instance.price > 100
)

# ❌ AVOID: Complex logic in lambda
condition = LambdaCondition(
    lambda instance: (
        instance.price > 100 and 
        instance.category in ['electronics', 'computers'] and
        instance.stock_quantity > 0 and
        instance.rating >= 4.0 and
        instance.is_active and
        instance.created_at > datetime.now() - timedelta(days=30)
    )
)

# ✅ BETTER: Use custom condition class for complex logic
class IsRecentExpensiveElectronics(HookCondition):
    def check(self, instance, original_instance=None):
        return (
            instance.price > 100 and 
            instance.category in ['electronics', 'computers'] and
            instance.stock_quantity > 0 and
            instance.rating >= 4.0 and
            instance.is_active and
            instance.created_at > datetime.now() - timedelta(days=30)
        )
    
    def get_required_fields(self):
        return {'price', 'category', 'stock_quantity', 'rating', 'is_active', 'created_at'}
```

## 🔧 Best Practices for Related Objects
