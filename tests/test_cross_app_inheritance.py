"""
Test trigger inheritance across different apps/modules.

This simulates the scenario where:
1. A core app defines base triggers (registered first)
2. An extension app defines child triggers that override base triggers (registered second)

This mimics Django's INSTALLED_APPS order where apps are imported sequentially.
"""

from django.test import TestCase

from django_bulk_triggers.constants import AFTER_CREATE, BEFORE_CREATE, AFTER_UPDATE
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.engine import run as run_triggers
from django_bulk_triggers.handler import Trigger as TriggerClass
from django_bulk_triggers.registry import clear_triggers, get_triggers


class TestCrossAppInheritance(TestCase):
    """Test that trigger inheritance works across app boundaries."""

    def setUp(self):
        # Ensure a clean registry for each test
        clear_triggers()

    def test_extension_app_overrides_core_app_triggers(self):
        """
        Simulate:
        - augend.financial_accounts app defines FinancialAccountTrigger
        - cimb_singapore.financial_accounts app defines CIMBFinancialAccountTrigger(FinancialAccountTrigger)
        """
        from tests.models import TriggerModel

        core_calls = {"on_create": 0, "on_update": 0, "before_create": 0}
        extension_calls = {"on_create": 0, "on_update": 0}

        # Step 1: Core app is imported first (augend)
        class CoreFinancialAccountTrigger(TriggerClass):
            """Base trigger from core augend app."""

            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                core_calls["on_create"] += 1

            @trigger(AFTER_UPDATE, model=TriggerModel)
            def on_update(self, new_records, old_records=None, **kwargs):
                core_calls["on_update"] += 1

            @trigger(BEFORE_CREATE, model=TriggerModel)
            def before_create(self, new_records, old_records=None, **kwargs):
                core_calls["before_create"] += 1

        # Verify core triggers are registered
        after_create_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        self.assertEqual(len(after_create_triggers), 1)
        self.assertEqual(after_create_triggers[0][0], CoreFinancialAccountTrigger)

        # Step 2: Extension app is imported second (cimb_singapore)
        class CIMBFinancialAccountTrigger(CoreFinancialAccountTrigger):
            """Extension trigger from cimb_singapore app - overrides one method."""

            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                # Override with CIMB-specific logic
                extension_calls["on_create"] += 1

            # Inherit on_update and before_create from parent

        # Verify extension triggers replaced core triggers
        after_create_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        after_update_triggers = get_triggers(TriggerModel, AFTER_UPDATE)
        before_create_triggers = get_triggers(TriggerModel, BEFORE_CREATE)

        # Only CIMBFinancialAccountTrigger should be registered, not CoreFinancialAccountTrigger
        self.assertEqual(len(after_create_triggers), 1)
        self.assertEqual(after_create_triggers[0][0], CIMBFinancialAccountTrigger)
        self.assertEqual(after_create_triggers[0][1], "on_create")

        self.assertEqual(len(after_update_triggers), 1)
        self.assertEqual(after_update_triggers[0][0], CIMBFinancialAccountTrigger)
        self.assertEqual(after_update_triggers[0][1], "on_update")

        self.assertEqual(len(before_create_triggers), 1)
        self.assertEqual(before_create_triggers[0][0], CIMBFinancialAccountTrigger)
        self.assertEqual(before_create_triggers[0][1], "before_create")

        # Step 3: Execute triggers and verify correct inheritance behavior
        obj = TriggerModel(name="test", value=1)

        run_triggers(TriggerModel, AFTER_CREATE, new_records=[obj])
        run_triggers(TriggerModel, AFTER_UPDATE, new_records=[obj], old_records=[obj])

        # Overridden method: Extension implementation executes
        self.assertEqual(extension_calls["on_create"], 1, "Extension on_create should execute (overridden)")
        self.assertEqual(core_calls["on_create"], 0, "Core on_create should NOT execute (was overridden)")

        # Inherited method: Parent implementation executes (standard OOP behavior)
        # The trigger is registered under CIMBFinancialAccountTrigger, but the method body is from parent
        self.assertEqual(core_calls["on_update"], 1, "Core on_update executes (inherited, not overridden)")
        self.assertEqual(extension_calls["on_update"], 0, "Extension has no on_update override")

        # before_create was also inherited
        # Note: before_create wasn't executed in this test, but it's registered under child

    def test_multiple_extension_apps_cascade_inheritance(self):
        """
        Test inheritance chain: Core → Extension1 → Extension2
        
        Simulates:
        - augend defines BaseTrigger
        - cimb_singapore defines CIMBTrigger(BaseTrigger) 
        - cimb_singapore.premium defines PremiumCIMBTrigger(CIMBTrigger)
        """
        from tests.models import TriggerModel

        base_calls = {"on_create": 0}
        cimb_calls = {"on_create": 0}
        premium_calls = {"on_create": 0}

        # App 1: Base
        class BaseTrigger(TriggerClass):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                base_calls["on_create"] += 1

        # App 2: CIMB overrides
        class CIMBTrigger(BaseTrigger):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                cimb_calls["on_create"] += 1

        # App 3: Premium CIMB overrides again
        class PremiumCIMBTrigger(CIMBTrigger):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                premium_calls["on_create"] += 1

        # Verify only the most-derived class is registered
        after_create_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        self.assertEqual(len(after_create_triggers), 1)
        self.assertEqual(after_create_triggers[0][0], PremiumCIMBTrigger)

        # Execute and verify
        obj = TriggerModel(name="test", value=1)
        run_triggers(TriggerModel, AFTER_CREATE, new_records=[obj])

        self.assertEqual(base_calls["on_create"], 0)
        self.assertEqual(cimb_calls["on_create"], 0)
        self.assertEqual(premium_calls["on_create"], 1)

    def test_sibling_apps_dont_interfere(self):
        """
        Test that sibling extension apps don't interfere with each other.
        
        Simulates:
        - augend defines BaseTrigger
        - cimb_singapore defines CIMBTrigger(BaseTrigger)
        - hsbc_singapore defines HSBCTrigger(BaseTrigger)
        
        Both CIMB and HSBC should have independent trigger registrations.
        """
        from tests.models import TriggerModel, SimpleModel

        base_calls = {"on_create": 0}
        cimb_calls = {"on_create": 0}
        hsbc_calls = {"on_create": 0}

        # Base trigger for TriggerModel
        class BaseTrigger(TriggerClass):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                base_calls["on_create"] += 1

        # CIMB extension for TriggerModel
        class CIMBTrigger(BaseTrigger):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                cimb_calls["on_create"] += 1

        # HSBC extension for SimpleModel (different model!)
        class HSBCTrigger(TriggerClass):
            @trigger(AFTER_CREATE, model=SimpleModel)
            def on_create(self, new_records, old_records=None, **kwargs):
                hsbc_calls["on_create"] += 1

        # Verify TriggerModel only has CIMBTrigger
        trigger_model_triggers = get_triggers(TriggerModel, AFTER_CREATE)
        self.assertEqual(len(trigger_model_triggers), 1)
        self.assertEqual(trigger_model_triggers[0][0], CIMBTrigger)

        # Verify SimpleModel only has HSBCTrigger
        simple_model_triggers = get_triggers(SimpleModel, AFTER_CREATE)
        self.assertEqual(len(simple_model_triggers), 1)
        self.assertEqual(simple_model_triggers[0][0], HSBCTrigger)

        # Execute and verify isolation
        trigger_obj = TriggerModel(name="test1", value=1)
        simple_obj = SimpleModel(name="test2", value=2)

        run_triggers(TriggerModel, AFTER_CREATE, new_records=[trigger_obj])
        run_triggers(SimpleModel, AFTER_CREATE, new_records=[simple_obj])

        self.assertEqual(base_calls["on_create"], 0)
        self.assertEqual(cimb_calls["on_create"], 1)
        self.assertEqual(hsbc_calls["on_create"], 1)

