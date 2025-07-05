#!/usr/bin/env python
"""
Comprehensive example demonstrating Django Bulk Hooks lifecycle events.

This example shows how to use the HookModelMixin to handle all model lifecycle events:
- BEFORE_CREATE / AFTER_CREATE
- BEFORE_UPDATE / AFTER_UPDATE
- BEFORE_DELETE / AFTER_DELETE

It also demonstrates both individual model operations and bulk operations.
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
from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.models import HookModelMixin

# Configure logging to see all messages
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# Define a test model using the HookModelMixin
class User(HookModelMixin):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "example"


# Define comprehensive hook handlers
class UserLifecycleHandler(HookHandler):
    @hook(BEFORE_CREATE, model=User)
    def before_create(self, new_records, old_records):
        print(f"🟢 BEFORE_CREATE: Creating {len(new_records)} user(s)")
        for user in new_records:
            print(f"  - Will create: {user.name} ({user.email})")
            # You can modify the instance before it's saved
            if not user.name:
                user.name = "Anonymous User"

    @hook(AFTER_CREATE, model=User)
    def after_create(self, new_records, old_records):
        print(f"✅ AFTER_CREATE: Created {len(new_records)} user(s)")
        for user in new_records:
            print(f"  - Created: {user.name} (ID: {user.pk})")

    @hook(BEFORE_UPDATE, model=User)
    def before_update(self, new_records, old_records):
        print(f"🟡 BEFORE_UPDATE: Updating {len(new_records)} user(s)")
        for new_user, old_user in zip(new_records, old_records):
            print(f"  - Will update: {old_user.name} -> {new_user.name}")
            print(f"    Email: {old_user.email} -> {new_user.email}")
            print(f"    Active: {old_user.is_active} -> {new_user.is_active}")

    @hook(AFTER_UPDATE, model=User)
    def after_update(self, new_records, old_records):
        print(f"✅ AFTER_UPDATE: Updated {len(new_records)} user(s)")
        for new_user, old_user in zip(new_records, old_records):
            print(f"  - Updated: {new_user.name} (ID: {new_user.pk})")

    @hook(BEFORE_DELETE, model=User)
    def before_delete(self, new_records, old_records):
        print(f"🔴 BEFORE_DELETE: Deleting {len(old_records)} user(s)")
        for user in old_records:
            print(f"  - Will delete: {user.name} (ID: {user.pk})")
            # You can perform cleanup operations here
            # For example, archive the user instead of deleting

    @hook(AFTER_DELETE, model=User)
    def after_delete(self, new_records, old_records):
        print(f"✅ AFTER_DELETE: Deleted {len(old_records)} user(s)")
        for user in old_records:
            print(f"  - Deleted: {user.name} (ID: {user.pk})")


def main():
    print("=== Django Bulk Hooks Lifecycle Example ===\n")

    # Create the database tables
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "migrate"])

    print("=== Individual Model Operations ===\n")

    # Test individual create
    print("1. Creating individual user...")
    user1 = User.objects.create(name="John Doe", email="john@example.com")
    print(f"   Result: {user1.name} (ID: {user1.pk})\n")

    # Test individual update
    print("2. Updating individual user...")
    user1.name = "John Smith"
    user1.email = "john.smith@example.com"
    user1.save()
    print(f"   Result: {user1.name} (ID: {user1.pk})\n")

    # Test individual delete
    print("3. Deleting individual user...")
    user1.delete()
    print(f"   Result: User deleted\n")

    print("=== Bulk Operations ===\n")

    # Test bulk create
    print("4. Creating multiple users with bulk_create...")
    users_to_create = [
        User(name="Alice Johnson", email="alice@example.com"),
        User(name="Bob Wilson", email="bob@example.com"),
        User(name="Carol Brown", email="carol@example.com"),
    ]
    created_users = User.objects.bulk_create(users_to_create)
    print(f"   Result: Created {len(created_users)} users\n")

    # Test bulk update
    print("5. Updating multiple users with bulk_update...")
    for user in created_users:
        user.name = f"{user.name} (Updated)"
        user.is_active = False
    User.objects.bulk_update(created_users, fields=["name", "is_active"])
    print(f"   Result: Updated {len(created_users)} users\n")

    # Test queryset update
    print("6. Updating users with queryset.update()...")
    User.objects.update(is_active=True)
    print(f"   Result: Updated all users to active\n")

    # Test bulk delete
    print("7. Deleting multiple users with bulk_delete...")
    User.objects.bulk_delete(created_users)
    print(f"   Result: Deleted {len(created_users)} users\n")

    # Test queryset delete
    print("8. Creating users for queryset delete test...")
    users_for_delete = [
        User(name="Temp User 1", email="temp1@example.com"),
        User(name="Temp User 2", email="temp2@example.com"),
    ]
    User.objects.bulk_create(users_for_delete)

    print("9. Deleting users with queryset.delete()...")
    deleted_count = User.objects.delete()
    print(f"   Result: Deleted {deleted_count} users\n")

    print("=== Final State ===")
    print(f"Total users in database: {User.objects.count()}")


if __name__ == "__main__":
    main()
