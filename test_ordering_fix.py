#!/usr/bin/env python
"""
Test to verify that the ordering fix for bulk operations works correctly.
This test ensures that old and new records are properly paired in hooks.
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

from django.db import models

from django_bulk_hooks import HookHandler, hook
from django_bulk_hooks.constants import AFTER_UPDATE, BEFORE_UPDATE
from django_bulk_hooks.models import HookModelMixin

# Configure logging
logging.basicConfig(level=logging.DEBUG)


class LoanAccount(HookModelMixin):
    account_number = models.CharField(max_length=50, unique=True)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        app_label = "test"


class LoanAccountHooks(HookHandler):
    @hook(BEFORE_UPDATE, model=LoanAccount)
    def validate_account_number(self, new_records, old_records):
        print("\n=== BEFORE_UPDATE Hook ===")
        for i, (new_account, old_account) in enumerate(zip(new_records, old_records)):
            print(
                f"Record {i}: ID {new_account.id} - Old: '{old_account.account_number}' -> New: '{new_account.account_number}'"
            )

            if old_account.account_number != new_account.account_number:
                raise ValueError(
                    f"Account number cannot be changed from '{old_account.account_number}' to '{new_account.account_number}'"
                )

    @hook(AFTER_UPDATE, model=LoanAccount)
    def after_update(self, new_records, old_records):
        print("\n=== AFTER_UPDATE Hook ===")
        for i, (new_account, old_account) in enumerate(zip(new_records, old_records)):
            print(
                f"Record {i}: ID {new_account.id} - Updated from '{old_account.account_number}' to '{new_account.account_number}'"
            )


def main():
    print("=== Testing Ordering Fix for Bulk Operations ===\n")

    # Create database tables
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "migrate"])

    # Create test accounts with specific IDs
    accounts = [
        LoanAccount(account_number="loan-1234", balance=100.00),
        LoanAccount(account_number="loan-5678", balance=200.00),
        LoanAccount(account_number="loan-9999", balance=300.00),
    ]

    # Bulk create accounts
    created_accounts = LoanAccount.objects.bulk_create(accounts)
    print(f"Created {len(created_accounts)} accounts")

    # Verify the accounts were created with the expected IDs
    for account in created_accounts:
        print(f"Account ID {account.id}: {account.account_number}")

    # Now test bulk update with reordered accounts
    # This should trigger the validation error if ordering is wrong
    print("\n=== Testing Bulk Update with Reordered Accounts ===")

    # Reorder the accounts and modify them
    reordered_accounts = [
        created_accounts[2],  # ID 3 (loan-9999)
        created_accounts[0],  # ID 1 (loan-1234)
        created_accounts[1],  # ID 2 (loan-5678)
    ]

    # Try to change account numbers (this should fail validation)
    reordered_accounts[0].account_number = "loan-9999-changed"
    reordered_accounts[1].account_number = "loan-1234-changed"
    reordered_accounts[2].account_number = "loan-5678-changed"

    try:
        LoanAccount.objects.bulk_update(reordered_accounts, ["account_number"])
        print("❌ ERROR: Bulk update succeeded when it should have failed!")
    except ValueError as e:
        print(f"✅ SUCCESS: Bulk update correctly failed with validation error: {e}")

    # Test with valid changes (no account number changes)
    print("\n=== Testing Bulk Update with Valid Changes ===")
    reordered_accounts[0].balance = 350.00
    reordered_accounts[1].balance = 150.00
    reordered_accounts[2].balance = 250.00

    try:
        LoanAccount.objects.bulk_update(reordered_accounts, ["balance"])
        print("✅ SUCCESS: Bulk update with valid changes succeeded")
    except Exception as e:
        print(f"❌ ERROR: Bulk update failed unexpectedly: {e}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()
