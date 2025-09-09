#!/usr/bin/env python

from decimal import Decimal
from django.test import TestCase
from tests.models import SimpleModel
from django_bulk_triggers import TriggerClass
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.constants import AFTER_UPDATE
from django_bulk_triggers.conditions import HasChanged

class BalanceFixTest(TestCase):
    def setUp(self):
        # Test variables to track trigger execution
        self.balance_changes_detected = []
        self.trigger_executed = False

    def test_bulk_update_balance_trigger(self):
        # Use test case instance variables instead of globals
        balance_changes_detected = []
        trigger_executed = False
        
        test_case = self
        
        class BalanceTrigger(TriggerClass):            
            @trigger(AFTER_UPDATE, model=SimpleModel, condition=HasChanged("value"))
            def on_balance_changed(self, old_records, new_records, **kwargs):
                nonlocal balance_changes_detected, trigger_executed
                print(f"🎉 BALANCE TRIGGER FIRED!")
                trigger_executed = True
                
                print(f"  old_records count: {len(old_records) if old_records else 0}")
                print(f"  new_records count: {len(new_records)}")
                
                for i, (old, new) in enumerate(zip(old_records or [], new_records)):
                    change_info = {
                        'pk': new.pk,
                        'old_value': old.value if old else None,
                        'new_value': new.value,
                        'changed': old.value != new.value if old else True
                    }
                    balance_changes_detected.append(change_info)
                    print(f"  Balance change {i}: pk={new.pk}, {old.value if old else 'None'} -> {new.value}")
        
        # Create test trigger
        trigger_instance = BalanceTrigger()
        
        # Create test objects
        obj1 = SimpleModel.objects.create(name="test1", value=100)
        obj2 = SimpleModel.objects.create(name="test2", value=200)
        
        print(f"=== Initial state ===")
        print(f"obj1: name='{obj1.name}', value={obj1.value}")
        print(f"obj2: name='{obj2.name}', value={obj2.value}")
        
        # Fetch objects fresh from database and modify them (simulating accumulation service)
        objects_to_update = list(SimpleModel.objects.filter(pk__in=[obj1.pk, obj2.pk]).order_by('pk'))
        
        # Modify the values like your accumulation service would
        objects_to_update[0].value = 300  # Changed from 100 to 300
        objects_to_update[1].value = 400  # Changed from 200 to 400
        
        print(f"=== About to call bulk_update ===")
        print(f"obj1 will change: value {obj1.value} -> {objects_to_update[0].value}")
        print(f"obj2 will change: value {obj2.value} -> {objects_to_update[1].value}")
        
        # Call bulk_update - this should now trigger the balance change detection!
        result = SimpleModel.objects.bulk_update(objects_to_update, ['value'])
        
        print(f"=== Results ===")
        print(f"Trigger executed: {trigger_executed}")
        print(f"Balance changes detected: {balance_changes_detected}")
        
        # Verify the fix worked
        self.assertTrue(trigger_executed, "HasChanged('value') trigger should have fired")
        self.assertGreaterEqual(len(balance_changes_detected), 2, "Should have detected at least 2 balance changes")
        
        # Verify the specific changes detected
        change_1 = next(c for c in balance_changes_detected if c['pk'] == obj1.pk)
        change_2 = next(c for c in balance_changes_detected if c['pk'] == obj2.pk)
        
        self.assertEqual(change_1['old_value'], 100, f"Should have correct old value for obj1: {change_1}")
        self.assertEqual(change_1['new_value'], 300, f"Should have correct new value for obj1: {change_1}")
        self.assertTrue(change_1['changed'], f"Should detect change for obj1: {change_1}")
        
        self.assertEqual(change_2['old_value'], 200, f"Should have correct old value for obj2: {change_2}")
        self.assertEqual(change_2['new_value'], 400, f"Should have correct new value for obj2: {change_2}")
        self.assertTrue(change_2['changed'], f"Should detect change for obj2: {change_2}")
        
        print("✅ ALL TESTS PASSED! The balance trigger fix is working!")
