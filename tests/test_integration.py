"""
Integration tests for django-bulk-triggers.
"""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from django_bulk_triggers import TriggerClass
from django_bulk_triggers.conditions import HasChanged, IsEqual, IsNotEqual, WasEqual
from django_bulk_triggers.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
    VALIDATE_CREATE,
    VALIDATE_DELETE,
    VALIDATE_UPDATE,
)
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.priority import Priority
from tests.models import (
    Category,
    ComplexModel,
    RelatedModel,
    SimpleModel,
    TriggerModel,
    UserModel,
)
from tests.utils import TriggerTracker, create_test_instances

# Define trigger classes at module level to ensure registration
# Use separate trackers for each trigger class
_create_tracker = TriggerTracker()
_update_tracker = TriggerTracker()
_delete_tracker = TriggerTracker()


class BulkCreateTestTrigger(TriggerClass):
    tracker = _create_tracker  # Class variable to persist across instances

    def __init__(self):
        pass  # No need to create instance tracker

    @trigger(BEFORE_CREATE, model=TriggerModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        BulkCreateTestTrigger.tracker.add_call(
            BEFORE_CREATE, new_records, old_records, **kwargs
        )
        # Modify records before creation
        for record in new_records:
            record.name = f"Modified {record.name}"

    @trigger(AFTER_CREATE, model=TriggerModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        BulkCreateTestTrigger.tracker.add_call(
            AFTER_CREATE, new_records, old_records, **kwargs
        )


class BulkUpdateTestTrigger(TriggerClass):
    tracker = _update_tracker  # Class variable to persist across instances

    def __init__(self):
        pass  # No need to create instance tracker

    @trigger(BEFORE_UPDATE, model=TriggerModel)
    def on_before_update(self, new_records, old_records=None, **kwargs):
        BulkUpdateTestTrigger.tracker.add_call(
            BEFORE_UPDATE, new_records, old_records, **kwargs
        )

    @trigger(AFTER_UPDATE, model=TriggerModel)
    def on_after_update(self, new_records, old_records=None, **kwargs):
        BulkUpdateTestTrigger.tracker.add_call(
            AFTER_UPDATE, new_records, old_records, **kwargs
        )


class BulkDeleteTestTrigger(TriggerClass):
    tracker = _delete_tracker  # Class variable to persist across instances

    def __init__(self):
        pass  # No need to create instance tracker

    @trigger(BEFORE_DELETE, model=TriggerModel)
    def on_before_delete(self, new_records, old_records=None, **kwargs):
        BulkDeleteTestTrigger.tracker.add_call(
            BEFORE_DELETE, new_records, old_records, **kwargs
        )

    @trigger(AFTER_DELETE, model=TriggerModel)
    def on_after_delete(self, new_records, old_records=None, **kwargs):
        BulkDeleteTestTrigger.tracker.add_call(
            AFTER_DELETE, new_records, old_records, **kwargs
        )


# Additional trigger classes for specific test scenarios
_conditional_tracker = TriggerTracker()
_complex_conditional_tracker = TriggerTracker()
_error_tracker = TriggerTracker()
_performance_tracker = TriggerTracker()
_related_tracker = TriggerTracker()
_transaction_tracker = TriggerTracker()
_multi_model_tracker = TriggerTracker()
_priority_tracker = TriggerTracker()

# Global flags to control which triggers are active
_active_triggers = set()


class ConditionalTestTrigger(TriggerClass):
    def __init__(self):
        self.tracker = _conditional_tracker

    @trigger(BEFORE_CREATE, model=TriggerModel, condition=IsEqual("status", "active"))
    def on_active_create(self, new_records, old_records=None, **kwargs):
        if "conditional" in _active_triggers:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @trigger(BEFORE_UPDATE, model=TriggerModel, condition=HasChanged("status"))
    def on_status_change(self, new_records, old_records=None, **kwargs):
        if "conditional" in _active_triggers:
            self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)


class ComplexConditionalTestTrigger(TriggerClass):
    def __init__(self):
        self.tracker = _complex_conditional_tracker

    @trigger(
        BEFORE_UPDATE,
        model=TriggerModel,
        condition=(
            HasChanged("status")
            & (IsEqual("status", "active") | IsEqual("status", "inactive"))
        ),
    )
    def on_status_change(self, new_records, old_records=None, **kwargs):
        if "complex_conditional" in _active_triggers:
            self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)


class ErrorTestTrigger(TriggerClass):
    error_count = 0  # Class variable to persist across instances

    def __init__(self):
        self.tracker = _error_tracker

    @trigger(BEFORE_CREATE, model=TriggerModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        if "error" in _active_triggers:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)
            # Simulate an error
            if len(new_records) > 1:
                ErrorTestTrigger.error_count += 1  # Use class variable
                raise ValueError("Simulated error")


class PerformanceTestTrigger(TriggerClass):
    def __init__(self):
        self.tracker = _performance_tracker

    @trigger(BEFORE_CREATE, model=TriggerModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        if "performance" in _active_triggers:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


class RelatedTestTrigger(TriggerClass):
    def __init__(self):
        self.tracker = _related_tracker

    @trigger(AFTER_CREATE, model=TriggerModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        if "related" in _active_triggers:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
            # Create related objects when this trigger is active
            for record in new_records:
                RelatedModel.objects.create(
                    trigger_model=record,
                    amount=record.value * 2,
                    description=f"Related to {record.name}",
                )


class TransactionTestTrigger(TriggerClass):
    def __init__(self):
        self.tracker = _transaction_tracker

    @trigger(AFTER_CREATE, model=TriggerModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        if "transaction" in _active_triggers:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)


class MultiModelTestTrigger(TriggerClass):
    def __init__(self):
        self.tracker = _multi_model_tracker

    @trigger(BEFORE_CREATE, model=TriggerModel)
    def on_test_model_create(self, new_records, old_records=None, **kwargs):
        if "multi_model" in _active_triggers:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @trigger(BEFORE_CREATE, model=SimpleModel)
    def on_simple_model_create(self, new_records, old_records=None, **kwargs):
        if "multi_model" in _active_triggers:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


class PriorityTestTrigger(TriggerClass):
    execution_order = []  # Class variable to persist across instances

    def __init__(self):
        self.tracker = _priority_tracker

    @trigger(BEFORE_CREATE, model=TriggerModel, priority=Priority.LOW)
    def low_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_triggers:
            PriorityTestTrigger.execution_order.append("low")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @trigger(BEFORE_CREATE, model=TriggerModel, priority=Priority.HIGH)
    def high_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_triggers:
            PriorityTestTrigger.execution_order.append("high")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @trigger(BEFORE_CREATE, model=TriggerModel, priority=Priority.NORMAL)
    def normal_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_triggers:
            PriorityTestTrigger.execution_order.append("normal")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


# Additional trigger classes for real-world scenarios
class InventoryTrigger(TriggerClass):
    low_stock_alerts = []  # Class variable to persist across instances
    tracker = TriggerTracker()  # Class variable to persist across instances

    def __init__(self):
        pass  # No need to create instance tracker

    @trigger(BEFORE_UPDATE, model=TriggerModel, condition=HasChanged("value"))
    def check_stock_levels(self, new_records, old_records=None, **kwargs):
        if "inventory" in _active_triggers:
            InventoryTrigger.tracker.add_call(
                BEFORE_UPDATE, new_records, old_records, **kwargs
            )
            # Check for low stock
            for new_record, old_record in zip(new_records, old_records or []):
                if new_record.value < 10 and old_record.value >= 10:
                    InventoryTrigger.low_stock_alerts.append(new_record.name)

    @trigger(AFTER_DELETE, model=TriggerModel)
    def log_deletion(self, new_records, old_records=None, **kwargs):
        if "inventory" in _active_triggers:
            InventoryTrigger.tracker.add_call(
                AFTER_DELETE, new_records, old_records, **kwargs
            )


class AuditTrigger(TriggerClass):
    audit_log = []  # Class variable to persist across instances

    def __init__(self):
        self.tracker = TriggerTracker()

    @trigger(AFTER_CREATE, model=TriggerModel)
    def log_creation(self, new_records, old_records=None, **kwargs):
        if "audit" in _active_triggers:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
            for record in new_records:
                AuditTrigger.audit_log.append(
                    f"Created: {record.name} by {record.created_by.username}"
                )

    @trigger(AFTER_UPDATE, model=TriggerModel, condition=HasChanged("status"))
    def log_status_change(self, new_records, old_records=None, **kwargs):
        if "audit" in _active_triggers:
            self.tracker.add_call(AFTER_UPDATE, new_records, old_records, **kwargs)
            for new_record, old_record in zip(new_records, old_records or []):
                AuditTrigger.audit_log.append(
                    f"Status changed: {new_record.name} {old_record.status} -> {new_record.status}"
                )

    @trigger(AFTER_DELETE, model=TriggerModel)
    def log_deletion(self, new_records, old_records=None, **kwargs):
        if "audit" in _active_triggers:
            self.tracker.add_call(AFTER_DELETE, new_records, old_records, **kwargs)
            # For AFTER_DELETE, new_records contains the deleted records
            for record in new_records:
                AuditTrigger.audit_log.append(f"Deleted: {record.name}")


class UserRegistrationTrigger(TriggerClass):
    welcome_emails_sent = []  # Class variable to persist across instances
    tracker = TriggerTracker()  # Class variable to persist across instances

    def __init__(self):
        pass  # No need to create instance tracker

    @trigger(BEFORE_CREATE, model=SimpleModel)
    def validate_user(self, new_records, old_records=None, **kwargs):
        UserRegistrationTrigger.tracker.add_call(
            BEFORE_CREATE, new_records, old_records, **kwargs
        )
        # Validate name format (should not be empty)
        for user in new_records:
            if not user.name or len(user.name.strip()) == 0:
                raise ValueError(f"Invalid name: {user.name}")

    @trigger(AFTER_CREATE, model=SimpleModel)
    def send_welcome_email(self, new_records, old_records=None, **kwargs):
        UserRegistrationTrigger.tracker.add_call(
            AFTER_CREATE, new_records, old_records, **kwargs
        )
        # Simulate sending welcome emails (using names)
        for user in new_records:
            UserRegistrationTrigger.welcome_emails_sent.append(user.name)


class TestFullSystemIntegration(TestCase):
    """Test the entire system working together."""

    def setUp(self):
        from django.utils import timezone

        self.tracker = TriggerTracker()

        # Create test data using bulk_create to avoid RETURNING clause issues
        users = UserModel.objects.bulk_create(
            [
                UserModel(
                    username="testuser",
                    email="test@example.com",
                    is_active=True,
                    created_at=timezone.now(),
                )
            ]
        )
        self.user = users[0]

        categories = Category.objects.bulk_create(
            [Category(name="Test Category", description="", is_active=True)]
        )
        self.category = categories[0]

        # Reset the trackers for each test
        _create_tracker.reset()
        _update_tracker.reset()
        _delete_tracker.reset()
        _conditional_tracker.reset()
        _complex_conditional_tracker.reset()
        _error_tracker.reset()
        _performance_tracker.reset()
        _related_tracker.reset()
        _transaction_tracker.reset()
        _multi_model_tracker.reset()
        _priority_tracker.reset()

        # Reset trigger class variables
        AuditTrigger.audit_log.clear()
        InventoryTrigger.low_stock_alerts.clear()
        UserRegistrationTrigger.welcome_emails_sent.clear()

        # Clear active triggers
        _active_triggers.clear()

        # Re-register test triggers after clearing
        self._register_test_triggers()

    def _register_test_triggers(self):
        """Register the triggers needed for this test class."""
        from tests.utils import re_register_test_triggers

        re_register_test_triggers()

    def test_complete_bulk_create_workflow(self):
        """Test complete bulk_create workflow with triggers."""

        trigger_instance = BulkCreateTestTrigger()

        # Create test instances
        test_instances = [
            TriggerModel(
                name="Test 1", value=1, created_by=self.user, category=self.category
            ),
            TriggerModel(
                name="Test 2", value=2, created_by=self.user, category=self.category
            ),
            TriggerModel(
                name="Test 3", value=3, created_by=self.user, category=self.category
            ),
        ]

        # Perform bulk_create
        created_instances = TriggerModel.objects.bulk_create(test_instances)

        # Verify triggers were called
        self.assertEqual(len(trigger_instance.tracker.before_create_calls), 1)
        self.assertEqual(len(trigger_instance.tracker.after_create_calls), 1)

        # Verify before_create modified the names
        before_call = trigger_instance.tracker.before_create_calls[0]
        self.assertEqual(len(before_call["new_records"]), 3)
        for record in before_call["new_records"]:
            self.assertTrue(record.name.startswith("Modified "))

        # Verify instances were created
        self.assertEqual(len(created_instances), 3)
        for instance in created_instances:
            self.assertIsNotNone(instance.pk)

    def test_complete_bulk_update_workflow(self):
        """Test complete bulk_update workflow with triggers."""

        trigger_instance = BulkUpdateTestTrigger()

        # Create initial instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
            TriggerModel(name="Test 3", value=3, created_by=self.user),
        ]
        created_instances = TriggerModel.objects.bulk_create(test_instances)

        # Modify instances for update
        for instance in created_instances:
            instance.value *= 2
            instance.status = "updated"

        # Perform bulk_update - fields are auto-detected
        updated_count = TriggerModel.objects.bulk_update(created_instances)

        # Verify triggers were called
        self.assertEqual(len(trigger_instance.tracker.before_update_calls), 1)
        self.assertEqual(len(trigger_instance.tracker.after_update_calls), 1)

        # Verify update was successful
        self.assertEqual(updated_count, 3)

        # Verify data was updated
        for instance in created_instances:
            instance.refresh_from_db()
            self.assertIn(instance.value, [2, 4, 6])
            self.assertEqual(instance.status, "updated")

    def test_complete_bulk_delete_workflow(self):
        """Test complete bulk_delete workflow with triggers."""

        trigger_instance = BulkDeleteTestTrigger()

        # Create instances to delete (without triggers)
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
            TriggerModel(name="Test 3", value=3, created_by=self.user),
        ]
        created_instances = TriggerModel.objects.bulk_create(
            test_instances, bypass_triggers=True
        )

        # Perform bulk_delete
        deleted_count = TriggerModel.objects.bulk_delete(created_instances)

        # Verify triggers were called
        self.assertEqual(len(trigger_instance.tracker.before_delete_calls), 1)
        self.assertEqual(len(trigger_instance.tracker.after_delete_calls), 1)

        # Verify deletion was successful
        self.assertEqual(deleted_count, 3)

        # Verify instances are gone
        remaining_count = TriggerModel.objects.count()
        self.assertEqual(remaining_count, 0)

    def test_triggers_with_conditions(self):
        """Test triggers with various conditions."""

        _active_triggers.add("conditional")
        trigger_instance = ConditionalTestTrigger()

        # Create instances with different statuses
        test_instances = [
            TriggerModel(name="Active 1", status="active", created_by=self.user),
            TriggerModel(name="Inactive 1", status="inactive", created_by=self.user),
            TriggerModel(name="Active 2", status="active", created_by=self.user),
        ]

        # Only active instances should trigger the trigger
        TriggerModel.objects.bulk_create(test_instances)
        self.assertEqual(len(trigger_instance.tracker.before_create_calls), 1)

        # Get created instances
        created_instances = TriggerModel.objects.all()

        # Update status of some instances
        for i, instance in enumerate(created_instances):
            if i == 0:  # Change from active to inactive
                instance.status = "inactive"
            elif i == 1:  # Change from inactive to active
                instance.status = "active"
            # i == 2: No change

        # Only changed instances should trigger the trigger
        TriggerModel.objects.bulk_update(created_instances)
        self.assertEqual(len(trigger_instance.tracker.before_update_calls), 1)

    def test_triggers_with_priorities(self):
        """Test triggers with different priorities."""

        _active_triggers.add("priority")
        trigger_instance = PriorityTestTrigger()

        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Perform bulk_create
        TriggerModel.objects.bulk_create(test_instances)

        # Verify execution order (high priority first)
        expected_order = ["high", "normal", "low"]
        self.assertEqual(trigger_instance.execution_order, expected_order)

        # Also verify that triggers were called
        self.assertEqual(
            len(trigger_instance.tracker.before_create_calls), 3
        )  # One call per priority level

    def test_triggers_with_bypass(self):
        """Test triggers with bypass_triggers parameter."""

        # Use the pre-defined trigger class
        trigger_instance = BulkCreateTestTrigger()

        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Test without bypass (triggers should run)
        TriggerModel.objects.bulk_create(test_instances, bypass_triggers=False)
        self.assertEqual(len(trigger_instance.tracker.before_create_calls), 1)

        # Clear tracker
        trigger_instance.tracker.reset()

        # Test with bypass (triggers should not run)
        test_instances2 = [
            TriggerModel(name="Test 3", value=3, created_by=self.user),
            TriggerModel(name="Test 4", value=4, created_by=self.user),
        ]
        TriggerModel.objects.bulk_create(test_instances2, bypass_triggers=True)
        self.assertEqual(len(trigger_instance.tracker.before_create_calls), 0)

    def test_triggers_with_transactions(self):
        """Test triggers with database transactions."""

        _active_triggers.add("transaction")
        trigger_instance = TransactionTestTrigger()

        # Test with transaction
        with transaction.atomic():
            test_instances = [
                TriggerModel(name="Test 1", value=1, created_by=self.user),
                TriggerModel(name="Test 2", value=2, created_by=self.user),
            ]

            # Triggers are called immediately (not deferred)
            TriggerModel.objects.bulk_create(test_instances)

            # Trigger should have been called immediately
            self.assertEqual(len(trigger_instance.tracker.after_create_calls), 1)

        # After transaction commits, trigger should be called
        self.assertEqual(len(trigger_instance.tracker.after_create_calls), 1)

    def test_triggers_with_related_objects(self):
        """Test triggers with related objects."""

        _active_triggers.add("related")
        trigger_instance = RelatedTestTrigger()
        trigger_instance._create_related = True

        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Perform bulk_create
        created_instances = TriggerModel.objects.bulk_create(test_instances)

        # Verify triggers were called
        self.assertEqual(len(trigger_instance.tracker.after_create_calls), 1)

        # Verify related objects were created
        for instance in created_instances:
            related_count = RelatedModel.objects.filter(trigger_model=instance).count()
            self.assertEqual(related_count, 1)

            related = RelatedModel.objects.get(trigger_model=instance)
            self.assertEqual(related.amount, instance.value * 2)

    def test_triggers_with_error_handling(self):
        """Test triggers with error handling."""

        _active_triggers.add("error")
        trigger_instance = ErrorTestTrigger()

        # Create test instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
        ]

        # This should raise an exception due to the trigger error
        with self.assertRaises(ValueError):
            TriggerModel.objects.bulk_create(test_instances)

        # Verify trigger was called and error was raised
        self.assertEqual(len(trigger_instance.tracker.before_create_calls), 1)
        self.assertEqual(trigger_instance.error_count, 1)

        # Verify instances were NOT created due to the exception
        self.assertEqual(TriggerModel.objects.count(), 0)

    def test_triggers_with_complex_conditions(self):
        """Test triggers with complex condition combinations."""

        _active_triggers.add("complex_conditional")
        trigger_instance = ComplexConditionalTestTrigger()

        # Create initial instances
        test_instances = [
            TriggerModel(name="Test 1", status="pending", created_by=self.user),
            TriggerModel(name="Test 2", status="pending", created_by=self.user),
        ]
        created_instances = TriggerModel.objects.bulk_create(test_instances)

        # Update statuses
        created_instances[0].status = "active"
        created_instances[1].status = "inactive"

        # Only the changed instances should trigger the trigger
        TriggerModel.objects.bulk_update(created_instances)
        self.assertEqual(len(trigger_instance.tracker.before_update_calls), 1)

        # Update again without changes
        TriggerModel.objects.bulk_update(created_instances)
        self.assertEqual(
            len(trigger_instance.tracker.before_update_calls), 1
        )  # No additional calls

    def test_triggers_with_multiple_models(self):
        """Test triggers with multiple model types."""

        _active_triggers.add("multi_model")
        trigger_instance = MultiModelTestTrigger()

        # Create TriggerModel instances
        test_instances = [
            TriggerModel(name="Test 1", value=1, created_by=self.user),
            TriggerModel(name="Test 2", value=2, created_by=self.user),
        ]
        TriggerModel.objects.bulk_create(test_instances)

        # Create SimpleModel instances
        simple_instances = [
            SimpleModel(name="Simple 1", value=1),
            SimpleModel(name="Simple 2", value=2),
        ]
        SimpleModel.objects.bulk_create(simple_instances)

        # Verify triggers were called for both models
        self.assertEqual(len(trigger_instance.tracker.before_create_calls), 2)

    def test_triggers_performance(self):
        """Test triggers performance with large datasets."""

        _active_triggers.add("performance")
        trigger_instance = PerformanceTestTrigger()

        # Create many instances
        test_instances = []
        for i in range(100):
            test_instances.append(
                TriggerModel(name=f"Test {i}", value=i, created_by=self.user)
            )

        # Test bulk_create performance
        with self.assertNumQueries(
            4
        ):  # SAVEPOINT + INSERT (batch 1) + INSERT (batch 2) + RELEASE - with transaction.atomic
            created_instances = TriggerModel.objects.bulk_create(test_instances)

        # Verify triggers were called
        self.assertEqual(len(trigger_instance.tracker.before_create_calls), 1)
        self.assertEqual(len(created_instances), 100)

        # Test bulk_update performance
        # The auto-detection implementation does additional queries to detect changes
        # plus the bulk update query - refactored implementation
        with self.assertNumQueries(
            214
        ):  # SAVEPOINT + Individual SELECT queries for originals + bulk update query + RELEASE - optimized implementation
            updated_count = TriggerModel.objects.bulk_update(created_instances)

        self.assertEqual(updated_count, 100)

        # Test bulk_delete performance
        # The refactored implementation includes individual SELECT queries for field caching
        with self.assertNumQueries(
            105
        ):  # SAVEPOINT + 100 individual SELECTs + 1 bulk SELECT + 2 DELETE queries + RELEASE - refactored implementation
            deleted_count = TriggerModel.objects.bulk_delete(created_instances)

        self.assertEqual(deleted_count, 100)


class TestRealWorldScenarios(TestCase):
    """Test real-world usage scenarios."""

    def setUp(self):
        from django.utils import timezone

        # Create test data using bulk_create to avoid RETURNING clause issues
        users = UserModel.objects.bulk_create(
            [
                UserModel(
                    username="testuser",
                    email="test@example.com",
                    is_active=True,
                    created_at=timezone.now(),
                )
            ]
        )
        self.user = users[0]

        categories = Category.objects.bulk_create(
            [Category(name="Test Category", description="", is_active=True)]
        )
        self.category = categories[0]

        # Reset trigger class variables
        AuditTrigger.audit_log.clear()
        InventoryTrigger.low_stock_alerts.clear()
        UserRegistrationTrigger.welcome_emails_sent.clear()

        # Reset trackers
        UserRegistrationTrigger.tracker.reset()

        # Clear active triggers
        _active_triggers.clear()

        # Re-register test triggers after clearing
        self._register_test_triggers()

    def _register_test_triggers(self):
        """Register the triggers needed for this test class."""
        from tests.utils import re_register_test_triggers

        re_register_test_triggers()

    def test_user_registration_workflow(self):
        """Test a user registration workflow with triggers using TriggerModel."""

        _active_triggers.add("user_registration")
        trigger_instance = UserRegistrationTrigger()

        # Register multiple users using SimpleModel with available fields
        new_users = [
            SimpleModel(name="user1", value=100),
            SimpleModel(name="user2", value=200),
            SimpleModel(name="user3", value=300),
        ]

        # This should trigger validation and welcome emails
        created_users = SimpleModel.objects.bulk_create(new_users)

        # Verify triggers were called
        self.assertEqual(len(UserRegistrationTrigger.tracker.before_create_calls), 1)
        self.assertEqual(len(UserRegistrationTrigger.tracker.after_create_calls), 1)

        # Verify welcome emails were sent (using names instead of emails)
        self.assertEqual(len(UserRegistrationTrigger.welcome_emails_sent), 3)
        self.assertIn("user1", UserRegistrationTrigger.welcome_emails_sent)
        self.assertIn("user2", UserRegistrationTrigger.welcome_emails_sent)
        self.assertIn("user3", UserRegistrationTrigger.welcome_emails_sent)

    def test_inventory_management_workflow(self):
        """Test an inventory management workflow with triggers."""

        _active_triggers.add("inventory")
        trigger_instance = InventoryTrigger()

        # Create inventory items
        inventory_items = [
            TriggerModel(name="Item 1", value=50, created_by=self.user),
            TriggerModel(name="Item 2", value=15, created_by=self.user),
            TriggerModel(name="Item 3", value=25, created_by=self.user),
        ]
        created_items = TriggerModel.objects.bulk_create(inventory_items)

        # Update stock levels (some going below 10)
        created_items[0].value = 5  # Goes below 10
        created_items[1].value = 8  # Goes below 10
        created_items[2].value = 20  # Stays above 10

        TriggerModel.objects.bulk_update(created_items)

        # Verify low stock alerts
        self.assertEqual(len(InventoryTrigger.low_stock_alerts), 2)
        # Triggers are modifying names, so expect "Modified Item X"
        self.assertIn("Modified Item 1", InventoryTrigger.low_stock_alerts)
        self.assertIn("Modified Item 2", InventoryTrigger.low_stock_alerts)

        # Delete some items
        TriggerModel.objects.bulk_delete([created_items[0]])

        # Verify deletion was logged
        self.assertEqual(len(InventoryTrigger.tracker.after_delete_calls), 1)

    def test_audit_trail_workflow(self):
        """Test an audit trail workflow with triggers."""

        _active_triggers.add("audit")
        trigger_instance = AuditTrigger()

        # Create records
        records = [
            TriggerModel(name="Record 1", status="draft", created_by=self.user),
            TriggerModel(name="Record 2", status="draft", created_by=self.user),
        ]
        created_records = TriggerModel.objects.bulk_create(records)

        # Update statuses
        created_records[0].status = "published"
        created_records[1].status = "archived"
        TriggerModel.objects.bulk_update(created_records)

        # Delete one record
        TriggerModel.objects.bulk_delete([created_records[0]])

        # Verify audit log
        print(f"Audit log contents: {AuditTrigger.audit_log}")
        # Triggers are modifying names, so we expect 5 entries: 2 creates + 2 updates + 1 delete
        self.assertEqual(len(AuditTrigger.audit_log), 5)
        # Triggers are modifying names, so expect "Modified Record X"
        self.assertIn("Created: Modified Record 1 by testuser", AuditTrigger.audit_log)
        self.assertIn("Created: Modified Record 2 by testuser", AuditTrigger.audit_log)
        self.assertIn(
            "Status changed: Modified Record 1 draft -> published",
            AuditTrigger.audit_log,
        )
        self.assertIn(
            "Status changed: Modified Record 2 draft -> archived",
            AuditTrigger.audit_log,
        )
        self.assertIn("Deleted: Modified Record 1", AuditTrigger.audit_log)
