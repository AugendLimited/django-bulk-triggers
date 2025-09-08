"""
Test to verify that Subquery objects in update operations work correctly with triggers.
"""

from django.db import models
from django.db.models import OuterRef, Subquery, Sum
from django.test import TestCase

from django_bulk_triggers import TriggerClass
from django_bulk_triggers.constants import AFTER_UPDATE
from django_bulk_triggers.context import TriggerContext
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.manager import BulkTriggerManager
from django_bulk_triggers.queryset import TriggerQuerySetMixin
from tests.models import RelatedModel, TriggerModel, UserModel


class SubqueryTriggerTest(TriggerClass):
    """Trigger to test Subquery functionality."""

    after_update_called = False  # Class variable to persist across instances
    computed_values = []  # Class variable to persist across instances
    foreign_key_values = []  # Class variable to persist across instances

    def __init__(self):
        pass  # No need to initialize instance variables

    @classmethod
    def reset(cls):
        """Reset the trigger state for testing."""
        cls.after_update_called = False
        cls.computed_values.clear()
        cls.foreign_key_values.clear()

    @trigger(AFTER_UPDATE, model=TriggerModel)
    def test_subquery_access(self, new_records, old_records):
        SubqueryTriggerTest.after_update_called = True  # Use class variable
        for record in new_records:
            # This should now contain the computed value, not the Subquery object
            SubqueryTriggerTest.computed_values.append(
                record.computed_value
            )  # Use class variable
            # This should contain the User instance, not a raw ID
            SubqueryTriggerTest.foreign_key_values.append(
                record.created_by
            )  # Use class variable


class SubqueryTriggersTestCase(TestCase):
    """Test case for Subquery trigger functionality."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers

        clear_triggers()

        # Create test data
        self.user = UserModel.objects.create(username="testuser")
        self.trigger_model = TriggerModel.objects.create(
            name="Test", value=10, created_by=self.user
        )
        self.related1 = RelatedModel.objects.create(
            trigger_model=self.trigger_model, amount=5
        )
        self.related2 = RelatedModel.objects.create(
            trigger_model=self.trigger_model, amount=15
        )

        # Create trigger instance and manually register it
        self.trigger = SubqueryTriggerTest()

        # Manually register the trigger since the metaclass registration was cleared
        from django_bulk_triggers.registry import register_trigger

        register_trigger(
            model=TriggerModel,
            event=AFTER_UPDATE,
            handler_cls=SubqueryTriggerTest,
            method_name="test_subquery_access",
            condition=None,
            priority=50,
        )

        # Reset trigger state before each test
        self.trigger.reset()

    def test_subquery_in_triggers(self):
        """Test that Subquery computed values are accessible in triggers."""

        # Perform update with Subquery
        TriggerModel.objects.filter(pk=self.trigger_model.pk).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(trigger_model=OuterRef("pk"))
                .values("trigger_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify that the trigger was called and received computed values
        self.assertTrue(self.trigger.after_update_called)
        self.assertEqual(len(self.trigger.computed_values), 1)
        # The computed value should be 20 (5 + 15)
        self.assertEqual(self.trigger.computed_values[0], 20)

        # Verify the database was actually updated
        self.trigger_model.refresh_from_db()
        self.assertEqual(self.trigger_model.computed_value, 20)

    def test_bulk_subquery_performance(self):
        """Test that bulk Subquery operations are efficient."""

        # Create multiple test models for bulk testing
        test_models = []
        for i in range(10):
            model = TriggerModel.objects.create(name=f"Test{i}", value=i)
            RelatedModel.objects.create(trigger_model=model, amount=i * 2)
            RelatedModel.objects.create(trigger_model=model, amount=i * 3)
            test_models.append(model)

        # Perform bulk update with Subquery
        pks = [model.pk for model in test_models]
        TriggerModel.objects.filter(pk__in=pks).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(trigger_model=OuterRef("pk"))
                .values("trigger_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify all triggers received computed values
        self.assertTrue(self.trigger.after_update_called)
        self.assertEqual(len(self.trigger.computed_values), 10)

        # Verify all computed values are correct
        for i, value in enumerate(self.trigger.computed_values):
            expected = i * 2 + i * 3  # sum of the two related amounts
            self.assertEqual(value, expected)

    def test_subquery_object_not_passed_to_triggers(self):
        """Test that Subquery objects are not passed to triggers, only computed values."""

        # Perform update with Subquery
        TriggerModel.objects.filter(pk=self.trigger_model.pk).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(trigger_model=OuterRef("pk"))
                .values("trigger_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify that the trigger received actual values, not Subquery objects
        self.assertTrue(self.trigger.after_update_called)
        for value in self.trigger.computed_values:
            # The value should be an integer, not a Subquery object
            self.assertIsInstance(value, int)
            self.assertNotEqual(type(value).__name__, "Subquery")

    def test_foreign_key_fields_preserved(self):
        """Test that foreign key fields are preserved correctly after Subquery updates."""

        # Perform update with Subquery
        TriggerModel.objects.filter(pk=self.trigger_model.pk).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(trigger_model=OuterRef("pk"))
                .values("trigger_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify that the trigger was called
        self.assertTrue(self.trigger.after_update_called)

        # Verify that foreign key fields are still intact
        # The trigger should have access to the created_by field as a User instance
        self.assertEqual(len(self.trigger.foreign_key_values), 1)
        self.assertIsInstance(self.trigger.foreign_key_values[0], UserModel)
        self.assertEqual(self.trigger.foreign_key_values[0].username, "testuser")

    @trigger(AFTER_UPDATE, model=TriggerModel)
    def modify_status_after_update(self, new_records, old_records):
        """Trigger method to modify status field in AFTER_UPDATE."""
        for record in new_records:
            # Modify the status field in the AFTER_UPDATE trigger
            record.status = "modified_by_after_trigger"

    def test_after_update_trigger_modifications_persisted(self):
        """Test that AFTER_UPDATE trigger modifications are persisted to the database."""

        try:
            # Manually register the trigger
            from django_bulk_triggers.registry import register_trigger

            register_trigger(
                model=TriggerModel,
                event=AFTER_UPDATE,
                handler_cls=self.__class__,
                method_name="modify_status_after_update",
                condition=None,
                priority=50,
            )

            # Perform update with Subquery to trigger the AFTER_UPDATE flow
            TriggerModel.objects.filter(pk=self.trigger_model.pk).update(
                computed_value=Subquery(
                    RelatedModel.objects.filter(trigger_model=OuterRef("pk"))
                    .values("trigger_model")
                    .annotate(total=Sum("amount"))
                    .values("total")[:1]
                )
            )

            # Refresh the instance from the database
            self.trigger_model.refresh_from_db()

            # Verify that the AFTER_UPDATE trigger modification was persisted
            self.assertEqual(self.trigger_model.status, "modified_by_after_trigger")

        finally:
            # Clean up the trigger
            from django_bulk_triggers.registry import clear_triggers

            clear_triggers()
