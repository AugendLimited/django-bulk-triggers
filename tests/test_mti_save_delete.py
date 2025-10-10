"""
Test that save() and delete() properly fire parent triggers for MTI models.
"""
from django.test import TestCase

from django_bulk_triggers.constants import AFTER_CREATE, AFTER_UPDATE, AFTER_DELETE
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.handler import Trigger
from django_bulk_triggers.registry import clear_triggers
from tests.models import TriggerModel, Category


class ChildTriggerModel(TriggerModel):
    """Child model that inherits from TriggerModel for MTI testing."""
    class Meta:
        app_label = 'tests'


class TestMTISaveDelete(TestCase):
    """Test that parent triggers fire when using save() and delete() on MTI child models."""
    
    def setUp(self):
        clear_triggers()
        self.trigger_calls = []
        Category.objects.all().delete()
        self.category = Category.objects.create(name="Test Category")
        
    def tearDown(self):
        clear_triggers()
    
    def test_save_create_fires_parent_after_create(self):
        """Verify that save() fires parent AFTER_CREATE triggers for MTI models."""
        
        class ParentTrigger(Trigger):
            def __init__(trigger_self):
                trigger_self.calls = self.trigger_calls
            
            @trigger(AFTER_CREATE, model=TriggerModel)
            def parent_after_create(trigger_self, old_records, new_records, **kwargs):
                trigger_self.calls.append({
                    'event': 'parent_after_create',
                    'count': len(new_records),
                    'names': [r.name for r in new_records]
                })
        
        # Create child instance using save()
        child = ChildTriggerModel(name="Test Child", value=100, category=self.category)
        child.save()
        
        # Verify parent trigger fired
        parent_calls = [c for c in self.trigger_calls if c.get('event') == 'parent_after_create']
        
        self.assertEqual(len(parent_calls), 1, 
            f"Expected parent AFTER_CREATE to fire once, got {len(parent_calls)} calls")
        
        self.assertEqual(parent_calls[0]['count'], 1)
        self.assertIn('Test Child', parent_calls[0]['names'])
    
    def test_save_update_fires_parent_after_update(self):
        """Verify that save() fires parent AFTER_UPDATE triggers for MTI models."""
        
        # First create the instance
        child = ChildTriggerModel(name="Test Child", value=100, category=self.category)
        child.save()
        
        # Clear calls and register update trigger
        self.trigger_calls.clear()
        
        class ParentTrigger(Trigger):
            def __init__(trigger_self):
                trigger_self.calls = self.trigger_calls
            
            @trigger(AFTER_UPDATE, model=TriggerModel)
            def parent_after_update(trigger_self, old_records, new_records, **kwargs):
                trigger_self.calls.append({
                    'event': 'parent_after_update',
                    'count': len(new_records),
                    'names': [r.name for r in new_records]
                })
        
        # Update the instance
        child.name = "Updated Child"
        child.save()
        
        # Verify parent update trigger fired
        parent_calls = [c for c in self.trigger_calls if c.get('event') == 'parent_after_update']
        
        self.assertEqual(len(parent_calls), 1,
            f"Expected parent AFTER_UPDATE to fire once, got {len(parent_calls)} calls")
        self.assertIn('Updated Child', parent_calls[0]['names'])
    
    def test_delete_fires_parent_after_delete(self):
        """Verify that delete() fires parent AFTER_DELETE triggers for MTI models."""
        
        class ParentTrigger(Trigger):
            def __init__(trigger_self):
                trigger_self.calls = self.trigger_calls
            
            @trigger(AFTER_DELETE, model=TriggerModel)
            def parent_after_delete(trigger_self, old_records, new_records, **kwargs):
                trigger_self.calls.append({
                    'event': 'parent_after_delete',
                    'count': len(new_records),
                    'names': [r.name for r in new_records]
                })
        
        # Create and delete child instance
        child = ChildTriggerModel(name="Test Child", value=100, category=self.category)
        child.save()
        
        self.trigger_calls.clear()
        child.delete()
        
        # Verify parent delete trigger fired
        parent_calls = [c for c in self.trigger_calls if c.get('event') == 'parent_after_delete']
        
        self.assertEqual(len(parent_calls), 1,
            f"Expected parent AFTER_DELETE to fire once, got {len(parent_calls)} calls")
        self.assertIn('Test Child', parent_calls[0]['names'])
    
    def test_save_bypass_triggers_skips_parent_triggers(self):
        """Verify that bypass_triggers=True prevents parent triggers from firing."""
        
        class ParentTrigger(Trigger):
            def __init__(trigger_self):
                trigger_self.calls = self.trigger_calls
            
            @trigger(AFTER_CREATE, model=TriggerModel)
            def parent_after_create(trigger_self, old_records, new_records, **kwargs):
                trigger_self.calls.append({'event': 'parent_after_create'})
        
        # Create with bypass_triggers=True
        child = ChildTriggerModel(name="Test Child", value=100, category=self.category)
        child.save(bypass_triggers=True)
        
        # Verify NO triggers fired
        self.assertEqual(len(self.trigger_calls), 0,
            "No triggers should fire when bypass_triggers=True")
    
    def test_delete_bypass_triggers_skips_parent_triggers(self):
        """Verify that bypass_triggers=True prevents parent delete triggers from firing."""
        
        class ParentTrigger(Trigger):
            def __init__(trigger_self):
                trigger_self.calls = self.trigger_calls
            
            @trigger(AFTER_DELETE, model=TriggerModel)
            def parent_after_delete(trigger_self, old_records, new_records, **kwargs):
                trigger_self.calls.append({'event': 'parent_after_delete'})
        
        # Create instance
        child = ChildTriggerModel(name="Test Child", value=100, category=self.category)
        child.save(bypass_triggers=True)
        
        # Delete with bypass_triggers=True
        child.delete(bypass_triggers=True)
        
        # Verify NO triggers fired
        self.assertEqual(len(self.trigger_calls), 0,
            "No triggers should fire when bypass_triggers=True")
    
    def test_save_vs_bulk_create_equivalence(self):
        """Verify save() and bulk_create() produce identical trigger behavior."""
        
        save_calls = []
        bulk_calls = []
        
        # Test with save()
        class SaveTrigger(Trigger):
            def __init__(trigger_self):
                trigger_self.calls = save_calls
            
            @trigger(AFTER_CREATE, model=TriggerModel)
            def parent_after_create(trigger_self, old_records, new_records, **kwargs):
                trigger_self.calls.append({
                    'event': 'parent_after_create',
                    'count': len(new_records)
                })
        
        child1 = ChildTriggerModel(name="Save Test", value=100, category=self.category)
        child1.save()
        
        # Clear and test with bulk_create()
        clear_triggers()
        
        class BulkTrigger(Trigger):
            def __init__(trigger_self):
                trigger_self.calls = bulk_calls
            
            @trigger(AFTER_CREATE, model=TriggerModel)
            def parent_after_create(trigger_self, old_records, new_records, **kwargs):
                trigger_self.calls.append({
                    'event': 'parent_after_create',
                    'count': len(new_records)
                })
        
        child2 = ChildTriggerModel(name="Bulk Test", value=100, category=self.category)
        ChildTriggerModel.objects.bulk_create([child2])
        
        # Both should have fired parent triggers
        self.assertEqual(len(save_calls), len(bulk_calls),
            "save() and bulk_create() should fire the same number of parent triggers")
        self.assertEqual(save_calls[0]['count'], bulk_calls[0]['count'])
    
    def test_delete_vs_bulk_delete_equivalence(self):
        """Verify delete() and bulk_delete() produce identical trigger behavior."""
        
        delete_calls = []
        bulk_delete_calls = []
        
        class ParentTrigger(Trigger):
            @trigger(AFTER_DELETE, model=TriggerModel)
            def parent_after_delete(self, old_records, new_records, **kwargs):
                if hasattr(self, 'target_list'):
                    self.target_list.append({
                        'event': 'parent_after_delete',
                        'count': len(new_records)
                    })
        
        # Test with delete()
        trigger_instance = ParentTrigger()
        trigger_instance.target_list = delete_calls
        
        child1 = ChildTriggerModel(name="Delete Test", value=100, category=self.category)
        child1.save()
        child1.delete()
        
        # Clear and test with bulk_delete()
        clear_triggers()
        trigger_instance2 = ParentTrigger()
        trigger_instance2.target_list = bulk_delete_calls
        
        child2 = ChildTriggerModel(name="Bulk Delete Test", value=100, category=self.category)
        child2.save()
        ChildTriggerModel.objects.filter(pk=child2.pk).delete()
        
        # Both should have fired parent triggers
        self.assertEqual(len(delete_calls), len(bulk_delete_calls),
            "delete() and bulk_delete() should fire the same number of parent triggers")

