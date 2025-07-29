#!/usr/bin/env python
"""
Test to verify that BEFORE_CREATE hooks properly persist field modifications.
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

from django.db import models

from django_bulk_hooks import BEFORE_CREATE, HookHandler, hook
from django_bulk_hooks.conditions import IsBlank
from django_bulk_hooks.models import HookModelMixin


class TestModel(HookModelMixin, models.Model):
    name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50, blank=True, default="")

    def __str__(self):
        return f"{self.name} ({self.account_number})"


class TestHandler(HookHandler):
    @hook(BEFORE_CREATE, model=TestModel, condition=IsBlank("account_number"))
    def set_account_number(self, new_records, old_records=None):
        """Set account number if it's blank."""
        for record in new_records:
            if not record.account_number:
                record.account_number = f"ACC-{record.id or 'NEW'}-{len(new_records)}"
                print(f"Set account_number to: {record.account_number}")


def test_hook_persistence():
    """Test that BEFORE_CREATE hooks persist field modifications."""
    print("Testing hook persistence...")

    # Create a model instance with blank account_number
    test_instance = TestModel(name="Test Account")
    print(f"Before save - account_number: '{test_instance.account_number}'")

    # Save the instance (this should trigger the hook)
    test_instance.save()

    # Refresh from database to verify persistence
    test_instance.refresh_from_db()
    print(f"After save and refresh - account_number: '{test_instance.account_number}'")

    # Verify the account_number was set
    assert test_instance.account_number != "", (
        f"Expected account_number to be set, got: '{test_instance.account_number}'"
    )
    print(f"✅ Test passed! account_number is: '{test_instance.account_number}'")

    return test_instance


if __name__ == "__main__":
    # Create tables
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "migrate"])

    # Run test
    test_hook_persistence()
