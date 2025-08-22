#!/usr/bin/env python
"""
Test script to verify that HasChanged conditions work correctly with Subquery updates.
"""

import os
import sys

import django
from django.conf import settings

# Add the django_bulk_hooks directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "tests",  # Our test models
        ],
        USE_TZ=True,
        LOGGING={
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                },
            },
            "loggers": {
                "django_bulk_hooks": {
                    "handlers": ["console"],
                    "level": "DEBUG",
                    "propagate": False,
                },
            },
        },
    )

django.setup()

from django.db import models
from django.db.models import Max, OuterRef, Subquery

from django_bulk_hooks.conditions import HasChanged
from django_bulk_hooks.constants import BEFORE_UPDATE
from django_bulk_hooks.decorators import hook
from django_bulk_hooks.handler import Hook
from django_bulk_hooks.manager import BulkHookManager
from django_bulk_hooks.models import HookModelMixin


# Test Models
class TestParent(HookModelMixin, models.Model):
    name = models.CharField(max_length=100)
    computed_value = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="pending")

    objects = BulkHookManager()

    class Meta:
        app_label = "tests"


class TestChild(models.Model):
    parent = models.ForeignKey(
        TestParent, on_delete=models.CASCADE, related_name="children"
    )
    value = models.IntegerField()

    class Meta:
        app_label = "tests"


# Hook to test
class TestHook(Hook):
    executed_count = 0
    last_old_value = None
    last_new_value = None

    @hook(
        BEFORE_UPDATE,
        model=TestParent,
        condition=HasChanged("computed_value", has_changed=True),
    )
    def on_computed_value_change(self, old_records, new_records, **kwargs):
        TestHook.executed_count += 1
        if old_records and new_records:
            TestHook.last_old_value = old_records[0].computed_value
            TestHook.last_new_value = new_records[0].computed_value
            # Set status based on computed value to test hook field modifications
            if new_records[0].computed_value > 5:
                new_records[0].status = "high"
            else:
                new_records[0].status = "low"
        print(f"✅ Hook executed! Count: {TestHook.executed_count}")
        print(f"   Old value: {TestHook.last_old_value}")
        print(f"   New value: {TestHook.last_new_value}")
        print(f"   Set status to: {new_records[0].status}")


def run_test():
    """Test that HasChanged works with Subquery updates."""
    from django.core.management import execute_from_command_line

    print("Creating database tables...")
    execute_from_command_line(["manage.py", "migrate", "--run-syncdb", "--verbosity=0"])

    print("\n🧪 Testing HasChanged with Subquery updates...")

    # Reset hook state
    TestHook.executed_count = 0
    TestHook.last_old_value = None
    TestHook.last_new_value = None

    # Create test data
    parent = TestParent.objects.create(name="Test Parent", computed_value=0)
    TestChild.objects.create(parent=parent, value=10)
    TestChild.objects.create(parent=parent, value=20)
    TestChild.objects.create(parent=parent, value=30)

    print(f"Created parent with computed_value: {parent.computed_value}")
    print(f"Created 3 children with values: 10, 20, 30")

    # Update using Subquery (this should trigger the hook)
    print("\n📊 Updating computed_value using Subquery...")
    updated_count = TestParent.objects.filter(id=parent.id).update(
        computed_value=Subquery(
            TestChild.objects.filter(parent_id=OuterRef("pk"))
            .annotate(max_value=Max("value"))
            .values("max_value")[:1]
        )
    )

    print(f"Updated {updated_count} records")

    # Check results
    parent.refresh_from_db()
    print(f"Parent computed_value after update: {parent.computed_value}")
    print(f"Parent status after update: {parent.status}")

    # Verify hook execution
    if TestHook.executed_count > 0:
        print(f"\n✅ SUCCESS! Hook was executed {TestHook.executed_count} time(s)")
        print(
            f"   HasChanged detected: {TestHook.last_old_value} → {TestHook.last_new_value}"
        )
        # Verify that hook modifications were persisted
        expected_status = "high" if TestHook.last_new_value > 5 else "low"
        if parent.status == expected_status:
            print(f"   ✅ Hook field modification persisted: status = {parent.status}")
        else:
            print(
                f"   ❌ Hook field modification NOT persisted: expected {expected_status}, got {parent.status}"
            )
            return False
        return True
    else:
        print(f"\n❌ FAILURE! Hook was not executed")
        print(f"   Expected: computed_value to change from 0 to 30")
        print(f"   Hook execution count: {TestHook.executed_count}")
        return False


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
