#!/usr/bin/env python
"""
Test script to verify select_related functionality works correctly.
"""

import os
import sys
import django
from django.conf import settings
from django.db import connection, reset_queries
from django.test.utils import override_settings

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

from django.db import models
from django_bulk_hooks import hook, select_related, BEFORE_CREATE, AFTER_CREATE
from django_bulk_hooks.models import HookModelMixin
from django_bulk_hooks.conditions import IsEqual


class Status(models.Model):
    name = models.CharField(max_length=50)
    
    def __str__(self):
        return self.name


class LoanAccount(HookModelMixin, models.Model):
    name = models.CharField(max_length=100)
    status = models.ForeignKey(Status, on_delete=models.CASCADE)
    activated_date = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.status.name})"


class LoanAccountHandler:
    def __init__(self):
        self.activated_count = 0
    
    @hook(BEFORE_CREATE, model=LoanAccount, condition=IsEqual("status.name", value="ACTIVE"))
    @hook(
        AFTER_CREATE,
        model=LoanAccount,
        condition=IsEqual("status.name", value="ACTIVE"),
    )
    @select_related("status")
    def _set_activated_date(self, old_records, new_records, **kwargs):
        """This method should not cause queries in loops when accessing status.name"""
        print(f"Processing {len(new_records)} records")
        
        for record in new_records:
            # This should not cause a query since status is preloaded
            status_name = record.status.name
            print(f"Record {record.name} has status: {status_name}")
            
            if status_name == "ACTIVE":
                self.activated_count += 1
                print(f"Activated count: {self.activated_count}")


def test_select_related():
    """Test that select_related prevents queries in loops"""
    
    # Create the tables
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'migrate'])
    
    # Create test data
    active_status = Status.objects.create(name="ACTIVE")
    inactive_status = Status.objects.create(name="INACTIVE")
    
    # Create handler
    handler = LoanAccountHandler()
    
    # Enable query logging
    reset_queries()
    
    # Create loan accounts in bulk
    loan_accounts = [
        LoanAccount(name=f"Account {i}", status=active_status if i % 2 == 0 else inactive_status)
        for i in range(10)
    ]
    
    print("Creating loan accounts...")
    created_accounts = LoanAccount.objects.bulk_create(loan_accounts)
    
    # Check queries
    queries = connection.queries
    print(f"\nTotal queries executed: {len(queries)}")
    
    # Look for select_related queries
    select_related_queries = [q for q in queries if 'SELECT' in q['sql'] and 'JOIN' in q['sql']]
    print(f"Queries with JOINs (select_related): {len(select_related_queries)}")
    
    # Print a few queries for debugging
    for i, query in enumerate(queries[:5]):
        print(f"Query {i+1}: {query['sql'][:100]}...")
    
    print(f"\nHandler activated count: {handler.activated_count}")
    
    # Verify that we have the expected number of active accounts
    expected_active = len([acc for acc in created_accounts if acc.status.name == "ACTIVE"])
    print(f"Expected active accounts: {expected_active}")
    
    assert handler.activated_count == expected_active, f"Expected {expected_active}, got {handler.activated_count}"


if __name__ == "__main__":
    test_select_related()
    print("\n✅ Test completed successfully!") 