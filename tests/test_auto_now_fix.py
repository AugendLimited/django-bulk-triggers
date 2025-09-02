#!/usr/bin/env python3
"""
Test script to verify auto_now field handling in bulk_update
"""

import os
import sys
import django
from django.conf import settings
from django.db import models

# Setup Django
if not settings.configured:
    settings.configure(
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=[],
        LOGGING={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "verbose": {
                    "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "level": "DEBUG",
                    "class": "logging.StreamHandler",
                    "formatter": "verbose",
                },
            },
            "root": {"level": "DEBUG", "handlers": ["console"]},
            "loggers": {
                "django_bulk_hooks": {
                    "level": "DEBUG",
                    "handlers": ["console"],
                    "propagate": False,
                },
            },
        }
    )
    django.setup()

# Create a test model
class TestModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    value = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'test'

# Test the bulk_update functionality
def test_auto_now_bulk_update():
    print("Testing auto_now field handling in bulk_update...")
    
    # Create tables
    from django.db import connection
    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(TestModel)
    
    # Create initial record
    initial_record = TestModel(name="test-1", value=100)
    initial_record.save()
    
    print(f"Initial record created with updated_at: {initial_record.updated_at}")
    original_updated_at = initial_record.updated_at
    
    # Wait a bit to ensure timestamp difference
    import time
    time.sleep(0.1)
    
    # Now do a bulk_update operation
    from django_bulk_hooks.queryset import HookQuerySetMixin
    
    # Create a mock queryset with the mixin
    class MockQuerySet:
        def __init__(self, model):
            self.model = model
            self._meta = model._meta
    
    # Mix in the HookQuerySetMixin
    queryset = MockQuerySet(TestModel)
    HookQuerySetMixin.__init__(queryset)
    
    # Create an object to update
    update_obj = TestModel(name="test-1", value=200)
    update_obj.pk = initial_record.pk  # Set the same PK for update
    
    print(f"Update object prepared with updated_at: {update_obj.updated_at}")
    
    # Perform bulk_update
    result = queryset.bulk_update([update_obj], ["value", "updated_at"])
    
    print(f"Bulk update operation completed. Result: {result}")
    
    # Refresh the record from database
    updated_record = TestModel.objects.get(name="test-1")
    print(f"Updated record value: {updated_record.value}")
    print(f"Updated record updated_at: {updated_record.updated_at}")
    
    # Check if updated_at was updated
    if updated_record.updated_at != original_updated_at:
        print("✅ SUCCESS: updated_at timestamp was updated during bulk_update!")
    else:
        print("❌ FAILURE: updated_at timestamp was not updated during bulk_update!")
        print(f"  Original: {original_updated_at}")
        print(f"  Current:  {updated_record.updated_at}")

if __name__ == "__main__":
    test_auto_now_bulk_update()
