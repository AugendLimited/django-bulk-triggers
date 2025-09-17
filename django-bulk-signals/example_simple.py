"""
Example: Zero-Coupling Bulk Signals Implementation

This example demonstrates how the simplified architecture eliminates coupling issues.
Each component has a single responsibility and zero dependencies on other components.
"""

from django.db import models
from django_bulk_signals import BulkSignalManager
from django_bulk_signals.conditions import ChangesTo, HasChanged, IsEqual
from django_bulk_signals.decorators import (
    after_create,
    after_update,
    before_create,
    before_delete,
    before_update,
)


class Account(models.Model):
    """Account model with bulk signal support."""

    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="active")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BulkSignalManager()  # This is the ONLY integration point

    def __str__(self):
        return self.name


class Opportunity(models.Model):
    """Opportunity model."""

    name = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stage = models.CharField(max_length=20, default="prospecting")

    def __str__(self):
        return self.name


# =============================================================================
# TRIGGER HANDLERS - Each has ZERO dependencies on services or configuration
# =============================================================================


@before_create(Account)
def validate_account_creation(sender, instances, **kwargs):
    """
    Validate accounts before creation.

    This handler has ZERO dependencies on services, executors, or configuration.
    It only knows about the instances and validation logic.
    """
    for account in instances:
        if not account.name:
            raise ValueError("Account name is required")
        if account.balance < 0:
            raise ValueError("Account balance cannot be negative")


@after_create(Account)
def create_default_opportunity(sender, instances, **kwargs):
    """
    Create default opportunity for new accounts.

    This handler has ZERO dependencies on services or configuration.
    It only knows about creating related records.
    """
    for account in instances:
        Opportunity.objects.create(
            name=f"Default Opportunity for {account.name}",
            account=account,
            amount=0,
            stage="prospecting",
        )


@before_update(Account, condition=ChangesTo("status", "inactive"))
def handle_account_deactivation(sender, instances, originals, **kwargs):
    """
    Handle account deactivation.

    This handler has ZERO dependencies on services or configuration.
    It only knows about the condition and the business logic.
    """
    for account in instances:
        # Close all opportunities when account becomes inactive
        opportunities = Opportunity.objects.filter(account=account)
        for opp in opportunities:
            opp.stage = "closed_lost"
            opp.save()


@after_update(Account, condition=HasChanged("balance"))
def update_opportunity_amounts(sender, instances, originals, **kwargs):
    """
    Update opportunity amounts when account balance changes.

    This handler has ZERO dependencies on services or configuration.
    It only knows about the condition and the business logic.
    """
    for account, original in zip(instances, originals):
        if account.balance != original.balance:
            # Update opportunity amounts based on new balance
            opportunities = Opportunity.objects.filter(account=account)
            for opp in opportunities:
                opp.amount = account.balance * 0.1
                opp.save()


@before_delete(Account)
def validate_account_deletion(sender, instances, **kwargs):
    """
    Validate account deletion.

    This handler has ZERO dependencies on services or configuration.
    It only knows about validation logic.
    """
    for account in instances:
        # Prevent deletion of accounts with open opportunities
        open_opportunities = Opportunity.objects.filter(
            account=account, stage__in=["prospecting", "qualification", "proposal"]
        )
        if open_opportunities.exists():
            raise ValueError(
                f"Cannot delete account {account.name} with open opportunities"
            )


# =============================================================================
# USAGE EXAMPLES - Clean, simple, predictable
# =============================================================================


def example_usage():
    """Example of using the zero-coupling bulk signals."""

    # Create accounts - triggers fire automatically
    accounts = [
        Account(name="Account 1", status="active", balance=1000),
        Account(name="Account 2", status="active", balance=2000),
        Account(name="Account 3", status="active", balance=3000),
    ]

    # This fires:
    # 1. validate_account_creation (before_create)
    # 2. Django's bulk_create
    # 3. create_default_opportunity (after_create)
    created_accounts = Account.objects.bulk_create(accounts)
    print(f"Created {len(created_accounts)} accounts")

    # Update accounts - triggers fire automatically
    accounts[0].status = "inactive"
    accounts[1].balance = 2500

    # This fires:
    # 1. handle_account_deactivation (before_update, condition=ChangesTo('status', 'inactive'))
    # 2. Django's bulk_update
    # 3. update_opportunity_amounts (after_update, condition=HasChanged('balance'))
    Account.objects.bulk_update(accounts, ["status", "balance"])
    print("Updated accounts")

    # Delete accounts - triggers fire automatically
    # This fires:
    # 1. validate_account_deletion (before_delete)
    # 2. Django's bulk_delete
    Account.objects.bulk_delete(accounts)
    print("Deleted accounts")


# =============================================================================
# TESTING EXAMPLES - Easy to test, no mocking required
# =============================================================================


def test_example():
    """Example of testing the zero-coupling implementation."""

    # Test before_create trigger
    accounts = [Account(name="Test Account", balance=1000)]

    # This should work
    try:
        Account.objects.bulk_create(accounts)
        print("✅ Account creation test passed")
    except ValueError as e:
        print(f"❌ Account creation test failed: {e}")

    # Test validation
    invalid_accounts = [Account(name="", balance=1000)]  # Empty name

    # This should fail
    try:
        Account.objects.bulk_create(invalid_accounts)
        print("❌ Validation test failed - should have raised ValueError")
    except ValueError as e:
        print(f"✅ Validation test passed: {e}")


if __name__ == "__main__":
    print("Django Bulk Signals - Zero Coupling Example")
    print("=" * 50)

    # Run examples
    try:
        example_usage()
        test_example()
    except Exception as e:
        print(f"Example failed: {e}")
        import traceback

        traceback.print_exc()
