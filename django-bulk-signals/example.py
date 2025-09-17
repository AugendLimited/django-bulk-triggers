#!/usr/bin/env python
"""
Example usage of django-bulk-signals.

This script demonstrates how to use django-bulk-signals in a real-world scenario,
showing Salesforce-style trigger patterns.
"""

import os
import sys
from decimal import Decimal

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
django.setup()

from django.db import models
from django_bulk_signals import BulkSignalManager, BulkSignalModelMixin
from django_bulk_signals.conditions import ChangesTo, HasChanged
from django_bulk_signals.decorators import (
    after_create,
    after_update,
    before_create,
    before_delete,
    before_update,
)


class Account(BulkSignalModelMixin):
    """Account model - similar to Salesforce Account."""

    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="active")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        app_label = "example"

    def __str__(self):
        return f"{self.name} ({self.status}) - ${self.balance}"


class Opportunity(models.Model):
    """Opportunity model - similar to Salesforce Opportunity."""

    name = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stage = models.CharField(max_length=20, default="prospecting")

    objects = BulkSignalManager()

    class Meta:
        app_label = "example"

    def __str__(self):
        return f"{self.name} - ${self.amount} ({self.stage})"


# Trigger Handlers
@before_create(Account)
def validate_account_creation(sender, instances, **kwargs):
    """Validate all accounts before creation."""
    print("🔍 BEFORE_CREATE: Validating account creation...")

    for account in instances:
        if not account.name:
            raise ValueError("Account name is required")
        if account.balance < 0:
            raise ValueError("Account balance cannot be negative")

    print(f"✅ Validation passed for {len(instances)} accounts")


@after_create(Account)
def create_default_opportunity(sender, instances, **kwargs):
    """Create default opportunity for new accounts."""
    print("🎯 AFTER_CREATE: Creating default opportunities...")

    for account in instances:
        opportunity = Opportunity.objects.create(
            name=f"Default Opportunity for {account.name}",
            account=account,
            amount=Decimal("0.00"),
            stage="prospecting",
        )
        print(f"  Created opportunity: {opportunity}")


@before_update(Account, condition=ChangesTo("status", "inactive"))
def handle_account_deactivation(sender, instances, originals, **kwargs):
    """Handle account deactivation."""
    print("⚠️  BEFORE_UPDATE: Handling account deactivation...")

    for account, original in zip(instances, originals):
        if account.status == "inactive" and original.status != "inactive":
            print(f"  Account {account.name} is being deactivated")
            # Close all opportunities when account becomes inactive
            opportunities = Opportunity.objects.filter(account=account)
            for opp in opportunities:
                opp.stage = "closed_lost"
                opp.save()
                print(f"    Closed opportunity: {opp}")


@after_update(Account, condition=HasChanged("balance"))
def update_opportunity_amounts(sender, instances, originals, **kwargs):
    """Update opportunity amounts when account balance changes."""
    print("💰 AFTER_UPDATE: Updating opportunity amounts...")

    for account, original in zip(instances, originals):
        if account.balance != original.balance:
            print(
                f"  Account {account.name} balance changed: ${original.balance} → ${account.balance}"
            )
            # Update opportunity amounts based on new balance
            opportunities = Opportunity.objects.filter(account=account)
            for opp in opportunities:
                old_amount = opp.amount
                opp.amount = account.balance * Decimal("0.1")  # 10% of account balance
                opp.save()
                print(
                    f"    Updated opportunity {opp.name}: ${old_amount} → ${opp.amount}"
                )


@before_delete(Account)
def validate_account_deletion(sender, instances, **kwargs):
    """Validate account deletion."""
    print("🗑️  BEFORE_DELETE: Validating account deletion...")

    for account in instances:
        # Prevent deletion of accounts with open opportunities
        open_opportunities = Opportunity.objects.filter(
            account=account, stage__in=["prospecting", "qualification", "proposal"]
        )
        if open_opportunities.exists():
            raise ValueError(
                f"Cannot delete account {account.name} with open opportunities"
            )

    print(f"✅ Deletion validation passed for {len(instances)} accounts")


def main():
    """Main example function."""
    print("🚀 Django Bulk Signals Example")
    print("=" * 50)

    # Create test accounts
    print("\n1. Creating accounts with bulk_create...")
    accounts = [
        Account(name="Acme Corp", status="active", balance=Decimal("10000.00")),
        Account(name="TechStart Inc", status="active", balance=Decimal("5000.00")),
        Account(name="Global Solutions", status="active", balance=Decimal("15000.00")),
    ]

    Account.objects.bulk_create(accounts)
    print(f"Created {len(accounts)} accounts")

    # Display created accounts and opportunities
    print("\n📊 Current state:")
    for account in Account.objects.all():
        print(f"  {account}")
        opportunities = Opportunity.objects.filter(account=account)
        for opp in opportunities:
            print(f"    └─ {opp}")

    # Update accounts with bulk_update
    print("\n2. Updating accounts with bulk_update...")
    accounts = list(Account.objects.all())

    # Change status of first account to inactive
    accounts[0].status = "inactive"

    # Change balance of second account
    accounts[1].balance = Decimal("7500.00")

    Account.objects.bulk_update(accounts, ["status", "balance"])
    print("Updated accounts")

    # Display updated state
    print("\n📊 Updated state:")
    for account in Account.objects.all():
        print(f"  {account}")
        opportunities = Opportunity.objects.filter(account=account)
        for opp in opportunities:
            print(f"    └─ {opp}")

    # Try to delete accounts (this will fail for accounts with open opportunities)
    print("\n3. Attempting to delete accounts...")
    try:
        Account.objects.bulk_delete(accounts)
        print("✅ All accounts deleted successfully")
    except ValueError as e:
        print(f"❌ Deletion failed: {e}")
        print(
            "This is expected behavior - accounts with open opportunities cannot be deleted"
        )

    print("\n🎉 Example completed!")
    print("\nThis demonstrates:")
    print("- BEFORE_CREATE triggers for validation")
    print("- AFTER_CREATE triggers for creating related records")
    print("- BEFORE_UPDATE triggers with conditions")
    print("- AFTER_UPDATE triggers with field change detection")
    print("- BEFORE_DELETE triggers for validation")
    print("- All using Django's clean signal framework!")


if __name__ == "__main__":
    main()
