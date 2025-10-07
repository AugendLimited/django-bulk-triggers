# Nested Container Support Guide

This guide explains how to use `django-bulk-triggers` with hierarchical/nested dependency injection container structures.

## The Problem

Previously, the framework only supported flat container structures where triggers were direct providers on the container:

```python
class Container(containers.DeclarativeContainer):
    loan_account_trigger = providers.Singleton(LoanAccountTrigger, ...)
```

But many applications use nested/hierarchical container structures:

```python
class ApplicationContainer(containers.DeclarativeContainer):
    loan_accounts_container = providers.Singleton(LoanAccountsContainer)
    
class LoanAccountsContainer(containers.DeclarativeContainer):
    loan_account_trigger = providers.Singleton(LoanAccountTrigger, ...)
```

## The Solution

The framework now supports nested containers through three approaches:

###  1: Use `configure_nested_container()` (Simplest)

**Best for:** Most cases where triggers are in a sub-container

```python
from django.apps import AppConfig
from django.apps import apps
from django_bulk_triggers import configure_nested_container


class LoanaccountsConfig(AppConfig):
    name = "augend.loan_accounts"
    
    def ready(self):
        # Get your application container
        application_container = apps.get_app_config("augend_common").container
        
        # Configure django-bulk-triggers to use nested structure
        configure_nested_container(
            application_container,
            container_path="loan_accounts_container"
        )
```

**That's it!** The framework will automatically:
1. Navigate to `application_container.loan_accounts_container()`
2. Find `loan_account_trigger` provider
3. Call it to get fully-injected trigger instances

#### Deeply Nested Containers

For multiple levels of nesting, use dot notation:

```python
configure_nested_container(
    application_container,
    container_path="module.submodule.loan_accounts_container"
)
```

### Approach 2: Custom Provider Resolver (Most Flexible)

**Best for:** Complex container structures or custom navigation logic

```python
from django.apps import AppConfig
from django_bulk_triggers import configure_trigger_container


class LoanaccountsConfig(AppConfig):
    def ready(self):
        application_container = apps.get_app_config("augend_common").container
        
        def resolve_trigger(container, trigger_cls, provider_name):
            """
            Custom logic to navigate your container structure.
            
            Args:
                container: Root container
                trigger_cls: The trigger class to instantiate
                provider_name: Snake_case name (e.g., "loan_account_trigger")
            
            Returns:
                Fully-injected trigger instance
            """
            # Your custom navigation logic
            loan_accounts = container.loan_accounts_container()
            trigger_provider = getattr(loan_accounts, provider_name)
            return trigger_provider()
        
        configure_trigger_container(
            application_container,
            provider_resolver=resolve_trigger
        )
```

### Approach 3: Specific Factory (Most Control)

**Best for:** Per-trigger customization or special cases

```python
from django.apps import AppConfig
from django_bulk_triggers import set_trigger_factory


class LoanaccountsConfig(AppConfig):
    def ready(self):
        application_container = apps.get_app_config("augend_common").container
        
        def create_loan_account_trigger():
            loan_accounts = application_container.loan_accounts_container()
            return loan_accounts.loan_account_trigger()
        
        from augend.loan_accounts.triggers import LoanAccountTrigger
        set_trigger_factory(LoanAccountTrigger, create_loan_account_trigger)
```

## Complete Example

### Your Container Structure

```python
# augend/common/containers.py
from dependency_injector import containers, providers
from augend.loan_accounts.containers import LoanAccountsContainer
from augend.daily_loan_summaries.containers import DailyLoanSummariesContainer


class ApplicationContainer(containers.DeclarativeContainer):
    """Root application container."""
    
    # Sub-containers for different app modules
    loan_accounts_container = providers.Singleton(LoanAccountsContainer)
    daily_loan_summaries_container = providers.Singleton(DailyLoanSummariesContainer)
```

```python
# augend/loan_accounts/containers.py
from dependency_injector import containers, providers
from augend.loan_accounts.services import LoanAccountService, LoanAccountValidator
from augend.loan_accounts.triggers import LoanAccountTrigger


class LoanAccountsContainer(containers.DeclarativeContainer):
    """Container for loan accounts module."""
    
    # Services
    loan_account_service = providers.Singleton(LoanAccountService)
    loan_account_validator = providers.Singleton(LoanAccountValidator)
    
    # Triggers
    loan_account_trigger = providers.Singleton(
        LoanAccountTrigger,
        loan_account_service=loan_account_service,
        loan_account_validator=loan_account_validator,
    )
```

### Your Trigger Class

```python
# augend/loan_accounts/triggers.py
from django_bulk_triggers import Trigger
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.constants import BEFORE_CREATE, AFTER_UPDATE
from augend.loan_accounts.models import LoanAccount


class LoanAccountTrigger(Trigger):
    """Trigger for loan account business logic."""
    
    def __init__(self, loan_account_service, loan_account_validator):
        self.service = loan_account_service
        self.validator = loan_account_validator
    
    @trigger(BEFORE_CREATE, model=LoanAccount)
    def validate_on_create(self, new_records, old_records=None):
        """Validate loan accounts before creation."""
        for account in new_records:
            self.validator.validate(account)
    
    @trigger(AFTER_UPDATE, model=LoanAccount)
    def update_summary(self, new_records, old_records=None):
        """Update summaries after loan account changes."""
        for account in new_records:
            self.service.update_daily_summary(account)
```

### Configure in AppConfig

```python
# augend/loan_accounts/apps.py
from django.apps import AppConfig
from django.apps import apps
from django_bulk_triggers import configure_nested_container


class LoanaccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "augend_loan_accounts"
    name = "augend.loan_accounts"
    verbose_name = "Loan Accounts"

    def ready(self):
        # Get the application container from common app
        application_container = apps.get_app_config("augend_common").container
        
        # Wire the container for @inject decorators
        application_container.wire(packages=[self.name])
        
        # Configure django-bulk-triggers for nested structure
        configure_nested_container(
            application_container,
            container_path="loan_accounts_container"
        )
```

### Initialize Application Container

```python
# augend/common/apps.py
from django.apps import AppConfig


class ApplicationConfig(AppConfig):
    label = "augend_common"
    name = "augend.common"
    verbose_name = "Common"

    def ready(self):
        from augend.common.containers import ApplicationContainer

        # Initialize and store container
        self.container = ApplicationContainer()
        self.container.wire(packages=[self.name])
```

## How It Works

When a model operation triggers a handler:

1. **Framework needs trigger instance**: `LoanAccountTrigger`
2. **Converts to snake_case**: `loan_account_trigger`
3. **Navigates nested structure**: 
   - `application_container.loan_accounts_container()` → sub-container
   - `sub_container.loan_account_trigger` → provider
   - `provider()` → fully-injected instance
4. **Executes trigger method** with all dependencies injected

## Benefits

✅ **Zero boilerplate per trigger** - Configure once, all triggers work  
✅ **Type-safe dependency injection** - Container validates dependencies  
✅ **Testable** - Easy to swap containers in tests  
✅ **Scalable** - Works with any number of nested levels  
✅ **Production-grade** - No hacks or workarounds  

## Migration from Flat Structure

If you have an existing flat container, no changes needed! The framework is backward compatible:

```python
# This still works
class FlatContainer(containers.DeclarativeContainer):
    loan_account_trigger = providers.Singleton(LoanAccountTrigger, ...)

configure_trigger_container(flat_container)
```

## Troubleshooting

### Error: "Container path not found"
- Check that your container path exactly matches your container structure
- Ensure sub-containers are defined as `providers.Singleton()` not just class references

### Error: "Provider not found in sub-container"
- Verify the trigger provider exists in your sub-container
- Check naming convention: `LoanAccountTrigger` → `loan_account_trigger`

### Triggers still failing with "missing required arguments"
- Ensure you called `configure_nested_container()` in your `AppConfig.ready()`
- Verify the container is initialized before Django starts handling requests
- Check that your container wiring includes the app package

## Advanced: Multiple Sub-Containers

For apps with triggers in different sub-containers:

```python
def ready(self):
    application_container = apps.get_app_config("augend_common").container
    
    # Option 1: Configure for specific sub-container
    configure_nested_container(
        application_container,
        container_path="loan_accounts_container"
    )
    
    # Option 2: Custom resolver that handles multiple sub-containers
    def resolve_any_trigger(container, trigger_cls, provider_name):
        # Try loan accounts
        if hasattr(container, 'loan_accounts_container'):
            loan_accounts = container.loan_accounts_container()
            if hasattr(loan_accounts, provider_name):
                return getattr(loan_accounts, provider_name)()
        
        # Try daily summaries
        if hasattr(container, 'daily_loan_summaries_container'):
            summaries = container.daily_loan_summaries_container()
            if hasattr(summaries, provider_name):
                return getattr(summaries, provider_name)()
        
        raise ValueError(f"Provider {provider_name} not found")
    
    configure_trigger_container(
        application_container,
        provider_resolver=resolve_any_trigger
    )
```

## Summary

The framework now fully supports nested container structures with three approaches:

1. **`configure_nested_container()`** - Simple, one-line configuration
2. **Custom provider resolver** - Flexible for complex structures
3. **Specific factories** - Maximum control per trigger

Choose the approach that best fits your application's complexity and structure.

