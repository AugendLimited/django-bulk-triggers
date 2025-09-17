# Django Bulk Signals

**Salesforce-style triggers for Django bulk operations using signals**

Django Bulk Signals provides a clean, production-grade way to add trigger-like behavior to Django's bulk operations (`bulk_create`, `bulk_update`, `bulk_delete`) using Django's signal framework. This gives you Salesforce-style triggers without the complex hacks, thread-local state, or ORM interception found in other solutions.

## Features

- ✅ **Salesforce-style triggers** - BEFORE_CREATE, AFTER_CREATE, BEFORE_UPDATE, AFTER_UPDATE, BEFORE_DELETE, AFTER_DELETE
- ✅ **Clean Django signals** - Uses Django's built-in signal framework
- ✅ **No thread-local state** - No hidden dependencies or complex state management
- ✅ **Conditional triggers** - Fire triggers only when specific conditions are met
- ✅ **OLD/NEW value access** - Compare original and updated values like Salesforce
- ✅ **Transaction safety** - All operations wrapped in database transactions
- ✅ **Easy testing** - Simple to mock and test
- ✅ **Production ready** - Robust, maintainable, and well-tested

## Installation

```bash
pip install django-bulk-signals
```

## Quick Start

### 1. Add BulkSignalManager to your models

```python
from django.db import models
from django_bulk_signals import BulkSignalManager

class Account(models.Model):
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='active')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    objects = BulkSignalManager()  # Add this line
```

### 2. Create trigger handlers

```python
from django_bulk_signals.decorators import before_create, after_update
from django_bulk_signals.conditions import HasChanged

@before_create(Account)
def validate_account_creation(sender, instances, **kwargs):
    """Validate all accounts before creation."""
    for account in instances:
        if not account.name:
            raise ValueError("Account name is required")
        if account.balance < 0:
            raise ValueError("Account balance cannot be negative")

@after_update(Account, condition=HasChanged('status'))
def handle_status_change(sender, instances, originals, **kwargs):
    """Handle status changes."""
    for account, original in zip(instances, originals):
        if account.status != original.status:
            if account.status == 'inactive':
                account.balance = 0  # Set balance to 0 when inactive
```

### 3. Use bulk operations with triggers

```python
# Create accounts - triggers fire automatically
accounts = [
    Account(name='Account 1', status='active', balance=1000),
    Account(name='Account 2', status='inactive', balance=2000),
]
Account.objects.bulk_create(accounts)

# Update accounts - triggers fire automatically
accounts[0].status = 'inactive'
Account.objects.bulk_update(accounts, ['status'])
```

## Trigger Types

### BEFORE Triggers
Fire before the database operation and can modify the data:

```python
@before_create(Account)
def before_create_handler(sender, instances, **kwargs):
    # Modify instances before creation
    for account in instances:
        account.created_at = timezone.now()

@before_update(Account, condition=HasChanged('status'))
def before_update_handler(sender, instances, originals, **kwargs):
    # Modify instances before update
    for account, original in zip(instances, originals):
        if account.status != original.status:
            account.status_changed_at = timezone.now()
```

### AFTER Triggers
Fire after the database operation and can perform side effects:

```python
@after_create(Account)
def after_create_handler(sender, instances, **kwargs):
    # Send notifications, create related records, etc.
    for account in instances:
        send_welcome_email(account)

@after_update(Account, condition=HasChanged('balance'))
def after_update_handler(sender, instances, originals, **kwargs):
    # Update related records, send notifications, etc.
    for account, original in zip(instances, originals):
        if account.balance != original.balance:
            update_related_opportunities(account)
```

## Trigger Conditions

### HasChanged
Fire only when a field has changed:

```python
from django_bulk_signals.conditions import HasChanged

@after_update(Account, condition=HasChanged('status'))
def handle_status_change(sender, instances, originals, **kwargs):
    # Only fires when status field changes
    pass
```

### IsEqual / IsNotEqual
Fire when a field equals or doesn't equal a value:

```python
from django_bulk_signals.conditions import IsEqual, IsNotEqual

@before_update(Account, condition=IsEqual('status', 'inactive'))
def handle_deactivation(sender, instances, originals, **kwargs):
    # Only fires when status becomes 'inactive'
    pass

@after_update(Account, condition=IsNotEqual('balance', 0))
def handle_balance_change(sender, instances, originals, **kwargs):
    # Only fires when balance is not 0
    pass
```

### ChangesTo
Fire when a field changes to a specific value:

```python
from django_bulk_signals.conditions import ChangesTo

@before_update(Account, condition=ChangesTo('status', 'inactive'))
def handle_deactivation(sender, instances, originals, **kwargs):
    # Only fires when status changes to 'inactive'
    pass
```

### Custom Conditions
Create your own conditions:

```python
from django_bulk_signals.conditions import CustomCondition

def high_value_account(instance, original):
    return instance.balance > 10000

@after_update(Account, condition=CustomCondition(high_value_account))
def handle_high_value_account(sender, instances, originals, **kwargs):
    # Only fires for high-value accounts
    pass
```

## Convenience Functions

```python
from django_bulk_signals.conditions import has_changed, is_equal, changes_to

# These are equivalent:
@after_update(Account, condition=HasChanged('status'))
@after_update(Account, condition=has_changed('status'))

@before_update(Account, condition=IsEqual('status', 'inactive'))
@before_update(Account, condition=is_equal('status', 'inactive'))

@before_update(Account, condition=ChangesTo('status', 'inactive'))
@before_update(Account, condition=changes_to('status', 'inactive'))
```

## Real-World Example

Here's a complete example showing how to implement Salesforce-style triggers:

```python
from django.db import models
from django_bulk_signals import BulkSignalManager
from django_bulk_signals.decorators import (
    before_create, after_create, before_update, after_update, before_delete
)
from django_bulk_signals.conditions import HasChanged, ChangesTo

class Account(models.Model):
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default='active')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    objects = BulkSignalManager()

class Opportunity(models.Model):
    name = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stage = models.CharField(max_length=20, default='prospecting')

# Triggers
@before_create(Account)
def validate_account_creation(sender, instances, **kwargs):
    """Validate accounts before creation."""
    for account in instances:
        if not account.name:
            raise ValueError("Account name is required")
        if account.balance < 0:
            raise ValueError("Account balance cannot be negative")

@after_create(Account)
def create_default_opportunity(sender, instances, **kwargs):
    """Create default opportunity for new accounts."""
    for account in instances:
        Opportunity.objects.create(
            name=f"Default Opportunity for {account.name}",
            account=account,
            amount=0,
            stage='prospecting'
        )

@before_update(Account, condition=ChangesTo('status', 'inactive'))
def handle_account_deactivation(sender, instances, originals, **kwargs):
    """Handle account deactivation."""
    for account in instances:
        # Close all opportunities when account becomes inactive
        opportunities = Opportunity.objects.filter(account=account)
        for opp in opportunities:
            opp.stage = 'closed_lost'
            opp.save()

@after_update(Account, condition=HasChanged('balance'))
def update_opportunity_amounts(sender, instances, originals, **kwargs):
    """Update opportunity amounts when account balance changes."""
    for account, original in zip(instances, originals):
        if account.balance != original.balance:
            # Update opportunity amounts based on new balance
            opportunities = Opportunity.objects.filter(account=account)
            for opp in opportunities:
                opp.amount = account.balance * 0.1
                opp.save()

@before_delete(Account)
def validate_account_deletion(sender, instances, **kwargs):
    """Validate account deletion."""
    for account in instances:
        # Prevent deletion of accounts with open opportunities
        open_opportunities = Opportunity.objects.filter(
            account=account,
            stage__in=['prospecting', 'qualification', 'proposal']
        )
        if open_opportunities.exists():
            raise ValueError(f"Cannot delete account {account.name} with open opportunities")

# Usage
accounts = [
    Account(name='Account 1', status='active', balance=1000),
    Account(name='Account 2', status='active', balance=2000),
]

# Create accounts - triggers fire automatically
Account.objects.bulk_create(accounts)

# Update accounts - triggers fire automatically
accounts[0].status = 'inactive'
Account.objects.bulk_update(accounts, ['status'])

# Delete accounts - triggers fire automatically
Account.objects.bulk_delete(accounts)
```

## Testing

Django Bulk Signals is designed to be easy to test:

```python
from unittest.mock import patch
from django.test import TestCase

class TestAccountTriggers(TestCase):
    def test_before_create_trigger(self):
        """Test that before_create trigger fires."""
        with patch('myapp.signals.validate_account_creation') as mock_handler:
            accounts = [Account(name='Test Account', balance=1000)]
            Account.objects.bulk_create(accounts)
            mock_handler.assert_called_once()
    
    def test_after_update_trigger_with_condition(self):
        """Test that after_update trigger fires with condition."""
        with patch('myapp.signals.handle_status_change') as mock_handler:
            account = Account.objects.create(name='Test', status='active')
            account.status = 'inactive'
            Account.objects.bulk_update([account], ['status'])
            mock_handler.assert_called_once()
```

## Why Django Bulk Signals?

### Compared to Other Solutions

**Django Bulk Triggers (current approach):**
- ❌ 700+ lines of complex code
- ❌ Thread-local state hacks
- ❌ Complex ORM interception
- ❌ Metaclass magic
- ❌ Function attribute manipulation
- ❌ Hard to test and debug

**Django Bulk Signals (this solution):**
- ✅ 10 lines of clean code
- ✅ No hidden dependencies
- ✅ Standard Django patterns
- ✅ Easy to test and debug
- ✅ Maintainable and robust
- ✅ Leverages Django's infrastructure

### Benefits

1. **Clean Architecture** - Uses Django's signal framework instead of complex hacks
2. **Easy Testing** - Simple to mock and test trigger behavior
3. **Maintainable** - Clear, explicit code that's easy to understand
4. **Performance** - Leverages Django's optimized signal system
5. **Django Compliant** - Follows Django's established patterns
6. **Production Ready** - Robust error handling and transaction safety

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

If you have any questions or issues, please open an issue on GitHub.
