#!/usr/bin/env python
import os
import sys
import django
from django.conf import settings

# Setup Django
if not settings.configured:
    settings.configure(
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
        ],
        USE_TZ=False,
    )
    django.setup()

import logging
from django.db import models
from django_bulk_hooks.manager import BulkHookManager
from django_bulk_hooks import hook, BEFORE_DELETE, AFTER_DELETE, HookHandler
from django_bulk_hooks.registry import list_all_hooks

# Configure logging to see all messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Define a test model
class TestModel(models.Model):
    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)
    
    objects = BulkHookManager()
    
    class Meta:
        app_label = 'test'

# Define a hook handler
class TestHookHandler(HookHandler):
    @hook(BEFORE_DELETE, model=TestModel)
    def before_delete(self, new_records, old_records):
        print(f"BEFORE_DELETE called with {len(new_records)} records")
        for record in new_records:
            print(f"  Will delete: {record.name} (id={record.pk})")
    
    @hook(AFTER_DELETE, model=TestModel)
    def after_delete(self, new_records, old_records):
        print(f"AFTER_DELETE called with {len(new_records)} records")
        for record in new_records:
            print(f"  Deleted: {record.name} (id={record.pk})")

def main():
    print("=== Django Bulk Hooks Debug Test ===")
    
    # Create the database tables
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'migrate'])
    
    # List all registered hooks
    print("\n=== Registered Hooks ===")
    all_hooks = list_all_hooks()
    for (model, event), hooks in all_hooks.items():
        print(f"{model.__name__}.{event}: {len(hooks)} hooks")
        for handler_cls, method_name, condition, priority in hooks:
            print(f"  - {handler_cls.__name__}.{method_name} (priority={priority})")
    
    # Create some test objects
    print("\n=== Creating Test Objects ===")
    obj1 = TestModel.objects.create(name="Test1", value=100)
    obj2 = TestModel.objects.create(name="Test2", value=200)
    obj3 = TestModel.objects.create(name="Test3", value=300)
    
    print(f"Created objects: {obj1.pk}, {obj2.pk}, {obj3.pk}")
    
    # Test bulk delete
    print("\n=== Testing Bulk Delete ===")
    objects_to_delete = [obj1, obj2, obj3]
    TestModel.objects.bulk_delete(objects_to_delete)
    
    print("\n=== Final Object Count ===")
    print(f"Remaining objects: {TestModel.objects.count()}")

if __name__ == "__main__":
    main() 