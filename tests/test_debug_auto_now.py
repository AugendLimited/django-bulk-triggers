#!/usr/bin/env python3
"""
Test script with debug logging to understand auto_now field behavior during upsert operations.
"""

import os
import sys
import django
import logging
from django.conf import settings
import pytest

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings for testing
if not settings.configured:
    settings.configure(
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=[
            'django_bulk_hooks',
        ],
        USE_TZ=False,
        LOGGING={
            'version': 1,
            'disable_existing_loggers': False,
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                },
            },
            'loggers': {
                'django_bulk_hooks.queryset': {
                    'handlers': ['console'],
                    'level': 'DEBUG',
                },
            },
        },
    )
    django.setup()

from django.db import models
from django_bulk_hooks.constants import BEFORE_CREATE, BEFORE_UPDATE, AFTER_CREATE, AFTER_UPDATE
from django_bulk_hooks.decorators import hook

# Create a test model with auto_now fields
class TestModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    value = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'test_debug'

# Create a simple hook to track what's happening
class TestHook:
    def __init__(self):
        self.before_create_called = False
        self.before_update_called = False
        self.after_create_called = False
        self.after_update_called = False
        self.records_processed = []
    
    @hook(BEFORE_CREATE, model=TestModel)
    def before_create(self, old_records, new_records, **kwargs):
        self.before_create_called = True
        self.records_processed.extend(new_records)
        print(f"BEFORE_CREATE called with {len(new_records)} records")
    
    @hook(BEFORE_UPDATE, model=TestModel)
    def before_update(self, old_records, new_records, **kwargs):
        self.before_update_called = True
        self.records_processed.extend(new_records)
        print(f"BEFORE_UPDATE called with {len(new_records)} records")
    
    @hook(AFTER_CREATE, model=TestModel)
    def after_create(self, old_records, new_records, **kwargs):
        self.after_create_called = True
        print(f"AFTER_CREATE called with {len(new_records)} records")
    
    @hook(AFTER_UPDATE, model=TestModel)
    def after_update(self, old_records, new_records, **kwargs):
        self.after_update_called = True
        print(f"AFTER_UPDATE called with {len(new_records)} records")

@pytest.mark.skip(reason="This test creates dynamic models which interfere with pytest-django")
@pytest.mark.django_db
def test_auto_now_debug():
    """Test with debug logging to see what's happening with auto_now fields"""
    print("Testing auto_now field behavior with debug logging...")
    
    # Create the test hook
    test_hook = TestHook()
    
    # Create tables
    from django.db import connection
    with connection.cursor() as cursor:
        # Disable foreign key checks for SQLite
        cursor.execute('PRAGMA foreign_keys = OFF')
        try:
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(TestModel)
        finally:
            cursor.execute('PRAGMA foreign_keys = ON')
    
    # Create initial record
    initial_record = TestModel(name="test-1", value=100)
    initial_record.save()
    
    print(f"Initial record created with updated_at: {initial_record.updated_at}")
    original_updated_at = initial_record.updated_at
    
    # Wait a bit to ensure timestamp difference
    import time
    time.sleep(0.1)
    
    # Now do an upsert operation
    upsert_record = TestModel(name="test-1", value=200)  # Same name, different value
    
    print(f"Upsert record prepared with updated_at: {upsert_record.updated_at}")
    
    print("\n" + "="*50)
    print("PERFORMING UPSERT OPERATION")
    print("="*50)
    
    # Perform upsert
    result = TestModel.objects.bulk_create(
        [upsert_record], 
        unique_fields=["name"], 
        update_conflicts=True, 
        update_fields=["value"]
    )
    
    print(f"\nUpsert operation completed. Result: {result}")
    
    # Refresh the record from database
    updated_record = TestModel.objects.get(name="test-1")
    print(f"Updated record value: {updated_record.value}")
    print(f"Updated record updated_at: {updated_record.updated_at}")
    
    # Check if updated_at was preserved
    if updated_record.updated_at == original_updated_at:
        print("✅ SUCCESS: updated_at timestamp was preserved during upsert!")
    else:
        print("❌ FAILURE: updated_at timestamp was changed during upsert!")
        print(f"  Original: {original_updated_at}")
        print(f"  Current:  {updated_record.updated_at}")
    
    # Check hook execution
    print(f"\nHook execution summary:")
    print(f"  BEFORE_CREATE called: {test_hook.before_create_called}")
    print(f"  BEFORE_UPDATE called: {test_hook.before_update_called}")
    print(f"  AFTER_CREATE called: {test_hook.after_create_called}")
    print(f"  AFTER_UPDATE called: {test_hook.after_update_called}")
    print(f"  Total records processed: {len(test_hook.records_processed)}")
    
    return updated_record.updated_at == original_updated_at

if __name__ == "__main__":
    try:
        success = test_auto_now_debug()
        if success:
            print("\n🎉 All tests passed!")
        else:
            print("\n💥 Some tests failed!")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
