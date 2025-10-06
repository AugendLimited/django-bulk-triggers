from django.test import TestCase

from django_bulk_triggers.constants import AFTER_CREATE, BEFORE_CREATE
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.engine import run as run_triggers
from django_bulk_triggers.handler import Trigger as TriggerClass
from django_bulk_triggers.registry import clear_triggers, get_triggers


class TestInheritanceOverrides(TestCase):
    def setUp(self):
        # Ensure a clean registry for each test
        clear_triggers()

    def test_child_overrides_parent_registration(self):
        from tests.models import TriggerModel

        parent_calls = {"on_create": 0, "before_create": 0}
        child_calls = {"on_create": 0, "before_create": 0}

        class ParentTrigger(TriggerClass):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                parent_calls["on_create"] += 1

            @trigger(BEFORE_CREATE, model=TriggerModel)
            def before_create(self, new_records, old_records=None, **kwargs):
                parent_calls["before_create"] += 1

        class ChildTrigger(ParentTrigger):
            # Override one method, inherit the other
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                child_calls["on_create"] += 1

            # Inherit ParentTrigger.before_create

        # Validate registry: only ChildTrigger methods should be active
        after_create_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        before_create_triggers = get_triggers(TriggerModel, BEFORE_CREATE)

        # AFTER_CREATE should contain only ChildTrigger.on_create
        self.assertTrue(any(
            cls == ChildTrigger and method == "on_create" for cls, method, _, _ in after_create_triggers
        ))
        self.assertFalse(any(
            cls == ParentTrigger and method == "on_create" for cls, method, _, _ in after_create_triggers
        ))

        # BEFORE_CREATE should contain only ChildTrigger.before_create (inherited, but registered under child)
        self.assertTrue(any(
            cls == ChildTrigger and method == "before_create" for cls, method, _, _ in before_create_triggers
        ))
        self.assertFalse(any(
            cls == ParentTrigger and method == "before_create" for cls, method, _, _ in before_create_triggers
        ))

    def test_child_executes_only_child_override(self):
        from tests.models import TriggerModel

        parent_calls = {"on_create": 0}
        child_calls = {"on_create": 0, "before_create": 0}

        class ParentTrigger(TriggerClass):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                parent_calls["on_create"] += 1

            @trigger(BEFORE_CREATE, model=TriggerModel)
            def before_create(self, new_records, old_records=None, **kwargs):
                child_calls["before_create"] -= 100  # should never execute as parent, will be re-registered under child

        class ChildTrigger(ParentTrigger):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                child_calls["on_create"] += 1

            # Inherit before_create; will be registered with ChildTrigger as owner

        # Use an unsaved instance to avoid implicit manager-based trigger execution
        obj = TriggerModel(name="t1", value=1)

        # Debug: Check what's registered
        after_create_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        print(f"\nDEBUG: Registered AFTER_CREATE triggers: {after_create_triggers}")
        for cls, method, cond, pri in after_create_triggers:
            print(f"  - {cls.__name__}.{method}")

        # Trigger AFTER_CREATE once explicitly
        run_triggers(TriggerModel, AFTER_CREATE, new_records=[obj])

        # We expect only child on_create executed, parent not
        print(f"DEBUG: parent_calls={parent_calls}, child_calls={child_calls}")
        self.assertEqual(parent_calls["on_create"], 0, "Parent trigger should not have been called")
        self.assertEqual(child_calls["on_create"], 1, "Child trigger should have been called exactly once")

        # Also ensure BEFORE_CREATE is bound to ChildTrigger in registry
        before_create_triggers = get_triggers(TriggerModel, BEFORE_CREATE)
        self.assertTrue(any(
            cls == ChildTrigger and method == "before_create" for cls, method, _, _ in before_create_triggers
        ))
        self.assertFalse(any(
            cls == ParentTrigger and method == "before_create" for cls, method, _, _ in before_create_triggers
        ))
