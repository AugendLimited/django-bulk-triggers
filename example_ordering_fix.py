#!/usr/bin/env python
"""
Example demonstrating the Salesforce-like ordering fix for bulk operations.

This example shows how the system now properly pairs old and new records
in hooks, regardless of the order in which objects are passed to bulk operations.
"""

import os
import sys

import django
from django.conf import settings

# Setup Django
if not settings.configured:
    settings.configure(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
        ],
        USE_TZ=False,
    )
    django.setup()

import logging

from django.core.exceptions import ValidationError
from django.db import models

from django_bulk_hooks import HookHandler, hook
from django_bulk_hooks.constants import BEFORE_UPDATE
from django_bulk_hooks.models import HookModelMixin

# Configure logging
logging.basicConfig(level=logging.INFO)


class LoanAccount(HookModelMixin):
    account_number = models.CharField(max_length=50, unique=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        app_label = "example"


class LoanAccountHooks(HookHandler):
    @hook(BEFORE_UPDATE, model=LoanAccount)
    def validate_account_number(self, new_records, old_records):
        print("\n🔍 Validating account numbers...")
        for new_account, old_account in zip(new_records, old_records):
            print(
                f"  ID {new_account.id}: '{old_account.account_number}' -> '{new_account.account_number}'"
            )

            if old_account.account_number != new_account.account_number:
                raise ValidationError(
                    {
                        "account_number": f"Cannot change account number from '{old_account.account_number}' to '{new_account.account_number}'"
                    }
                )
        print("✅ All account numbers are valid!")


def main():
    print("=== Salesforce-like Ordering Fix Example ===\n")

    # Create database tables
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "migrate"])

    # Create test accounts
    accounts = [
        LoanAccount(account_number="loan-1234", balance=100.00),
        LoanAccount(account_number="loan-5678", balance=200.00),
        LoanAccount(account_number="loan-9999", balance=300.00),
    ]

    # Bulk create accounts
    created_accounts = LoanAccount.objects.bulk_create(accounts)
    print(f"Created {len(created_accounts)} accounts:")
    for account in created_accounts:
        print(f"  ID {account.id}: {account.account_number}")

    print("\n=== Testing with Reordered Objects ===")

    # Reorder the accounts (this would cause issues before the fix)
    reordered_accounts = [
        created_accounts[2],  # ID 3 (loan-9999)
        created_accounts[0],  # ID 1 (loan-1234)
        created_accounts[1],  # ID 2 (loan-5678)
    ]

    print("Reordered accounts for bulk update:")
    for account in reordered_accounts:
        print(f"  ID {account.id}: {account.account_number}")

    # Test 1: Valid update (no account number changes)
    print("\n--- Test 1: Valid balance updates ---")
    reordered_accounts[0].balance = 350.00
    reordered_accounts[1].balance = 150.00
    reordered_accounts[2].balance = 250.00

    try:
        LoanAccount.objects.bulk_update(reordered_accounts, ["balance"])
        print("✅ SUCCESS: Balance updates completed")
    except Exception as e:
        print(f"❌ ERROR: {e}")

    # Test 2: Invalid update (trying to change account numbers)
    print("\n--- Test 2: Invalid account number changes ---")
    reordered_accounts[0].account_number = "loan-9999-changed"
    reordered_accounts[1].account_number = "loan-1234-changed"
    reordered_accounts[2].account_number = "loan-5678-changed"

    try:
        LoanAccount.objects.bulk_update(reordered_accounts, ["account_number"])
        print("❌ ERROR: Should have failed validation!")
    except ValidationError as e:
        print("✅ SUCCESS: Correctly caught validation error")
        print(f"   Error: {e}")

    print("\n=== Summary ===")
    print("The ordering fix ensures that:")
    print("1. old_records[i] always corresponds to new_records[i]")
    print("2. Validation works correctly regardless of object order")
    print("3. The system behaves like Salesforce's trigger system")


if __name__ == "__main__":
    main()
