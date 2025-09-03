"""
Integration tests for django-bulk-hooks.
"""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django_bulk_hooks import HookClass
from django_bulk_hooks.decorators import hook
from django_bulk_hooks.constants import (
    BEFORE_CREATE, AFTER_CREATE, BEFORE_UPDATE, AFTER_UPDATE, 
    BEFORE_DELETE, AFTER_DELETE, VALIDATE_CREATE, VALIDATE_UPDATE, VALIDATE_DELETE
)
from django_bulk_hooks.conditions import HasChanged, IsEqual, IsNotEqual, WasEqual
from django_bulk_hooks.priority import Priority
from tests.models import HookModel, UserModel, SimpleModel, ComplexModel, Category, RelatedModel
from tests.utils import HookTracker, create_test_instances

# Define hook classes at module level to ensure registration
# Use separate trackers for each hook class
_create_tracker = HookTracker()
_update_tracker = HookTracker()
_delete_tracker = HookTracker()


class BulkCreateTestHook(HookClass):
    tracker = _create_tracker  # Class variable to persist across instances
    
    def __init__(self):
        pass  # No need to create instance tracker

    @hook(BEFORE_CREATE, model=HookModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        BulkCreateTestHook.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)
        # Modify records before creation
        for record in new_records:
            record.name = f"Modified {record.name}"

    @hook(AFTER_CREATE, model=HookModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        BulkCreateTestHook.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)


class BulkUpdateTestHook(HookClass):
    tracker = _update_tracker  # Class variable to persist across instances
    
    def __init__(self):
        pass  # No need to create instance tracker

    @hook(BEFORE_UPDATE, model=HookModel)
    def on_before_update(self, new_records, old_records=None, **kwargs):
        BulkUpdateTestHook.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)

    @hook(AFTER_UPDATE, model=HookModel)
    def on_after_update(self, new_records, old_records=None, **kwargs):
        BulkUpdateTestHook.tracker.add_call(AFTER_UPDATE, new_records, old_records, **kwargs)


class BulkDeleteTestHook(HookClass):
    tracker = _delete_tracker  # Class variable to persist across instances
    
    def __init__(self):
        pass  # No need to create instance tracker

    @hook(BEFORE_DELETE, model=HookModel)
    def on_before_delete(self, new_records, old_records=None, **kwargs):
        BulkDeleteTestHook.tracker.add_call(BEFORE_DELETE, new_records, old_records, **kwargs)

    @hook(AFTER_DELETE, model=HookModel)
    def on_after_delete(self, new_records, old_records=None, **kwargs):
        BulkDeleteTestHook.tracker.add_call(AFTER_DELETE, new_records, old_records, **kwargs)


# Additional hook classes for specific test scenarios
_conditional_tracker = HookTracker()
_complex_conditional_tracker = HookTracker()
_error_tracker = HookTracker()
_performance_tracker = HookTracker()
_related_tracker = HookTracker()
_transaction_tracker = HookTracker()
_multi_model_tracker = HookTracker()
_priority_tracker = HookTracker()

# Global flags to control which hooks are active
_active_hooks = set()


class ConditionalTestHook(HookClass):
    def __init__(self):
        self.tracker = _conditional_tracker

    @hook(BEFORE_CREATE, model=HookModel, condition=IsEqual("status", "active"))
    def on_active_create(self, new_records, old_records=None, **kwargs):
        if "conditional" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_UPDATE, model=HookModel, condition=HasChanged("status"))
    def on_status_change(self, new_records, old_records=None, **kwargs):
        if "conditional" in _active_hooks:
            self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)


class ComplexConditionalTestHook(HookClass):
    def __init__(self):
        self.tracker = _complex_conditional_tracker

    @hook(
        BEFORE_UPDATE,
        model=HookModel,
        condition=(
            HasChanged("status")
            & (IsEqual("status", "active") | IsEqual("status", "inactive"))
        ),
    )
    def on_status_change(self, new_records, old_records=None, **kwargs):
        if "complex_conditional" in _active_hooks:
            self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)


class ErrorTestHook(HookClass):
    error_count = 0  # Class variable to persist across instances
    
    def __init__(self):
        self.tracker = _error_tracker

    @hook(BEFORE_CREATE, model=HookModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        if "error" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)
            # Simulate an error
            if len(new_records) > 1:
                ErrorTestHook.error_count += 1  # Use class variable
                raise ValueError("Simulated error")


class PerformanceTestHook(HookClass):
    def __init__(self):
        self.tracker = _performance_tracker

    @hook(BEFORE_CREATE, model=HookModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        if "performance" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


class RelatedTestHook(HookClass):
    def __init__(self):
        self.tracker = _related_tracker

    @hook(AFTER_CREATE, model=HookModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        if "related" in _active_hooks:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
            # Create related objects when this hook is active
            for record in new_records:
                RelatedModel.objects.create(
                    hook_model=record,
                    amount=record.value * 2,
                    description=f"Related to {record.name}",
                )


class TransactionTestHook(HookClass):
    def __init__(self):
        self.tracker = _transaction_tracker

    @hook(AFTER_CREATE, model=HookModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        if "transaction" in _active_hooks:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)


class MultiModelTestHook(HookClass):
    def __init__(self):
        self.tracker = _multi_model_tracker

    @hook(BEFORE_CREATE, model=HookModel)
    def on_test_model_create(self, new_records, old_records=None, **kwargs):
        if "multi_model" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_CREATE, model=SimpleModel)
    def on_simple_model_create(self, new_records, old_records=None, **kwargs):
        if "multi_model" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


class PriorityTestHook(HookClass):
    execution_order = []  # Class variable to persist across instances
    
    def __init__(self):
        self.tracker = _priority_tracker

    @hook(BEFORE_CREATE, model=HookModel, priority=Priority.LOW)
    def low_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_hooks:
            PriorityTestHook.execution_order.append("low")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_CREATE, model=HookModel, priority=Priority.HIGH)
    def high_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_hooks:
            PriorityTestHook.execution_order.append("high")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_CREATE, model=HookModel, priority=Priority.NORMAL)
    def normal_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_hooks:
            PriorityTestHook.execution_order.append("normal")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


# Additional hook classes for real-world scenarios
class InventoryHook(HookClass):
    low_stock_alerts = []  # Class variable to persist across instances
    tracker = HookTracker()  # Class variable to persist across instances
    
    def __init__(self):
        pass  # No need to create instance tracker

    @hook(BEFORE_UPDATE, model=HookModel, condition=HasChanged("value"))
    def check_stock_levels(self, new_records, old_records=None, **kwargs):
        if "inventory" in _active_hooks:
            InventoryHook.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)
            # Check for low stock
            for new_record, old_record in zip(new_records, old_records or []):
                if new_record.value < 10 and old_record.value >= 10:
                    InventoryHook.low_stock_alerts.append(new_record.name)

    @hook(AFTER_DELETE, model=HookModel)
    def log_deletion(self, new_records, old_records=None, **kwargs):
        if "inventory" in _active_hooks:
            InventoryHook.tracker.add_call(AFTER_DELETE, new_records, old_records, **kwargs)


class AuditHook(HookClass):
    audit_log = []  # Class variable to persist across instances
    
    def __init__(self):
        self.tracker = HookTracker()

    @hook(AFTER_CREATE, model=HookModel)
    def log_creation(self, new_records, old_records=None, **kwargs):
        if "audit" in _active_hooks:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
            for record in new_records:
                AuditHook.audit_log.append(
                    f"Created: {record.name} by {record.created_by.username}"
                )

    @hook(AFTER_UPDATE, model=HookModel, condition=HasChanged("status"))
    def log_status_change(self, new_records, old_records=None, **kwargs):
        if "audit" in _active_hooks:
            self.tracker.add_call(AFTER_UPDATE, new_records, old_records, **kwargs)
            for new_record, old_record in zip(new_records, old_records or []):
                AuditHook.audit_log.append(
                    f"Status changed: {new_record.name} {old_record.status} -> {new_record.status}"
                )

    @hook(AFTER_DELETE, model=HookModel)
    def log_deletion(self, new_records, old_records=None, **kwargs):
        if "audit" in _active_hooks:
            self.tracker.add_call(AFTER_DELETE, new_records, old_records, **kwargs)
            # For AFTER_DELETE, new_records contains the deleted records
            for record in new_records:
                AuditHook.audit_log.append(f"Deleted: {record.name}")


class UserRegistrationHook(HookClass):
    welcome_emails_sent = []  # Class variable to persist across instances
    tracker = HookTracker()  # Class variable to persist across instances
    
    def __init__(self):
        pass  # No need to create instance tracker

    @hook(BEFORE_CREATE, model=HookModel)
    def validate_user(self, new_records, old_records=None, **kwargs):
        UserRegistrationHook.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)
        # Validate name format (should not be empty)
        for user in new_records:
            if not user.name or len(user.name.strip()) == 0:
                raise ValueError(f"Invalid name: {user.name}")

    @hook(AFTER_CREATE, model=HookModel)
    def send_welcome_email(self, new_records, old_records=None, **kwargs):
        UserRegistrationHook.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
        # Simulate sending welcome emails (using names)
        for user in new_records:
            UserRegistrationHook.welcome_emails_sent.append(user.name)


class TestFullSystemIntegration(TestCase):
    """Test the entire system working together."""

    def setUp(self):
        from django.utils import timezone

        self.tracker = HookTracker()

        # Create test data using bulk_create to avoid RETURNING clause issues
        users = UserModel.objects.bulk_create([
            UserModel(username="testuser", email="test@example.com", is_active=True, created_at=timezone.now())
        ])
        self.user = users[0]

        categories = Category.objects.bulk_create([
            Category(name="Test Category", description="", is_active=True)
        ])
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

        # Reset hook class variables
        AuditHook.audit_log.clear()
        InventoryHook.low_stock_alerts.clear()
        UserRegistrationHook.welcome_emails_sent.clear()

        # Clear active hooks
        _active_hooks.clear()
        
        # Re-register test hooks after clearing
        self._register_test_hooks()
    
    def _register_test_hooks(self):
        """Register the hooks needed for this test class."""
        from tests.utils import re_register_test_hooks
        re_register_test_hooks()

    def test_complete_bulk_create_workflow(self):
        """Test complete bulk_create workflow with hooks."""

        hook_instance = BulkCreateTestHook()

        # Create test instances
        test_instances = [
            HookModel(
                name="Test 1", value=1, created_by=self.user, category=self.category
            ),
            HookModel(
                name="Test 2", value=2, created_by=self.user, category=self.category
            ),
            HookModel(
                name="Test 3", value=3, created_by=self.user, category=self.category
            ),
        ]

        # Perform bulk_create
        created_instances = HookModel.objects.bulk_create(test_instances)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)
        self.assertEqual(len(hook_instance.tracker.after_create_calls), 1)

        # Verify before_create modified the names
        before_call = hook_instance.tracker.before_create_calls[0]
        self.assertEqual(len(before_call["new_records"]), 3)
        for record in before_call["new_records"]:
            self.assertTrue(record.name.startswith("Modified "))

        # Verify instances were created
        self.assertEqual(len(created_instances), 3)
        for instance in created_instances:
            self.assertIsNotNone(instance.pk)

    def test_complete_bulk_update_workflow(self):
        """Test complete bulk_update workflow with hooks."""

        hook_instance = BulkUpdateTestHook()

        # Create initial instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
            HookModel(name="Test 3", value=3, created_by=self.user),
        ]
        created_instances = HookModel.objects.bulk_create(test_instances)

        # Modify instances for update
        for instance in created_instances:
            instance.value *= 2
            instance.status = "updated"

        # Perform bulk_update
        updated_count = HookModel.objects.bulk_update(
            created_instances, ["value", "status"]
        )

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.before_update_calls), 1)
        self.assertEqual(len(hook_instance.tracker.after_update_calls), 1)

        # Verify update was successful
        self.assertEqual(updated_count, 3)

        # Verify data was updated
        for instance in created_instances:
            instance.refresh_from_db()
            self.assertIn(instance.value, [2, 4, 6])
            self.assertEqual(instance.status, "updated")

    def test_complete_bulk_delete_workflow(self):
        """Test complete bulk_delete workflow with hooks."""

        hook_instance = BulkDeleteTestHook()

        # Create instances to delete (without hooks)
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
            HookModel(name="Test 3", value=3, created_by=self.user),
        ]
        created_instances = HookModel.objects.bulk_create(
            test_instances, bypass_hooks=True
        )

        # Perform bulk_delete
        deleted_count = HookModel.objects.bulk_delete(created_instances)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.before_delete_calls), 1)
        self.assertEqual(len(hook_instance.tracker.after_delete_calls), 1)

        # Verify deletion was successful
        self.assertEqual(deleted_count, 3)

        # Verify instances are gone
        remaining_count = HookModel.objects.count()
        self.assertEqual(remaining_count, 0)

    def test_hooks_with_conditions(self):
        """Test hooks with various conditions."""

        _active_hooks.add("conditional")
        hook_instance = ConditionalTestHook()

        # Create instances with different statuses
        test_instances = [
            HookModel(name="Active 1", status="active", created_by=self.user),
            HookModel(name="Inactive 1", status="inactive", created_by=self.user),
            HookModel(name="Active 2", status="active", created_by=self.user),
        ]

        # Only active instances should trigger the hook
        HookModel.objects.bulk_create(test_instances)
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)

        # Get created instances
        created_instances = HookModel.objects.all()

        # Update status of some instances
        for i, instance in enumerate(created_instances):
            if i == 0:  # Change from active to inactive
                instance.status = "inactive"
            elif i == 1:  # Change from inactive to active
                instance.status = "active"
            # i == 2: No change

        # Only changed instances should trigger the hook
        HookModel.objects.bulk_update(created_instances, ["status"])
        self.assertEqual(len(hook_instance.tracker.before_update_calls), 1)

    def test_hooks_with_priorities(self):
        """Test hooks with different priorities."""

        _active_hooks.add("priority")
        hook_instance = PriorityTestHook()

        # Create test instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Perform bulk_create
        HookModel.objects.bulk_create(test_instances)

        # Verify execution order (high priority first)
        expected_order = ["high", "normal", "low"]
        self.assertEqual(hook_instance.execution_order, expected_order)

        # Also verify that hooks were called
        self.assertEqual(
            len(hook_instance.tracker.before_create_calls), 3
        )  # One call per priority level

    def test_hooks_with_bypass(self):
        """Test hooks with bypass_hooks parameter."""

        # Use the pre-defined hook class
        hook_instance = BulkCreateTestHook()

        # Create test instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Test without bypass (hooks should run)
        HookModel.objects.bulk_create(test_instances, bypass_hooks=False)
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)

        # Clear tracker
        hook_instance.tracker.reset()

        # Test with bypass (hooks should not run)
        test_instances2 = [
            HookModel(name="Test 3", value=3, created_by=self.user),
            HookModel(name="Test 4", value=4, created_by=self.user),
        ]
        HookModel.objects.bulk_create(test_instances2, bypass_hooks=True)
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 0)

    def test_hooks_with_transactions(self):
        """Test hooks with database transactions."""

        _active_hooks.add("transaction")
        hook_instance = TransactionTestHook()

        # Test with transaction
        with transaction.atomic():
            test_instances = [
                HookModel(name="Test 1", value=1, created_by=self.user),
                HookModel(name="Test 2", value=2, created_by=self.user),
            ]

            # Hooks are called immediately (not deferred)
            HookModel.objects.bulk_create(test_instances)

            # Hook should have been called immediately
            self.assertEqual(len(hook_instance.tracker.after_create_calls), 1)

        # After transaction commits, hook should be called
        self.assertEqual(len(hook_instance.tracker.after_create_calls), 1)

    def test_hooks_with_related_objects(self):
        """Test hooks with related objects."""

        _active_hooks.add("related")
        hook_instance = RelatedTestHook()
        hook_instance._create_related = True

        # Create test instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Perform bulk_create
        created_instances = HookModel.objects.bulk_create(test_instances)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.after_create_calls), 1)

        # Verify related objects were created
        for instance in created_instances:
            related_count = RelatedModel.objects.filter(hook_model=instance).count()
            self.assertEqual(related_count, 1)

            related = RelatedModel.objects.get(hook_model=instance)
            self.assertEqual(related.amount, instance.value * 2)

    def test_hooks_with_error_handling(self):
        """Test hooks with error handling."""

        _active_hooks.add("error")
        hook_instance = ErrorTestHook()

        # Create test instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
        ]

        # This should raise an exception due to the hook error
        with self.assertRaises(ValueError):
            HookModel.objects.bulk_create(test_instances)

        # Verify hook was called and error was raised
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)
        self.assertEqual(hook_instance.error_count, 1)

        # Verify instances were NOT created due to the exception
        self.assertEqual(HookModel.objects.count(), 0)

    def test_hooks_with_complex_conditions(self):
        """Test hooks with complex condition combinations."""

        _active_hooks.add("complex_conditional")
        hook_instance = ComplexConditionalTestHook()

        # Create initial instances
        test_instances = [
            HookModel(name="Test 1", status="pending", created_by=self.user),
            HookModel(name="Test 2", status="pending", created_by=self.user),
        ]
        created_instances = HookModel.objects.bulk_create(test_instances)

        # Update statuses
        created_instances[0].status = "active"
        created_instances[1].status = "inactive"

        # Only the changed instances should trigger the hook
        HookModel.objects.bulk_update(created_instances, ["status"])
        self.assertEqual(len(hook_instance.tracker.before_update_calls), 1)

        # Update again without changes
        HookModel.objects.bulk_update(created_instances, ["status"])
        self.assertEqual(
            len(hook_instance.tracker.before_update_calls), 1
        )  # No additional calls

    def test_hooks_with_multiple_models(self):
        """Test hooks with multiple model types."""

        _active_hooks.add("multi_model")
        hook_instance = MultiModelTestHook()

        # Create HookModel instances
        test_instances = [
            HookModel(name="Test 1", value=1, created_by=self.user),
            HookModel(name="Test 2", value=2, created_by=self.user),
        ]
        HookModel.objects.bulk_create(test_instances)

        # Create SimpleModel instances
        simple_instances = [
            SimpleModel(name="Simple 1", value=1),
            SimpleModel(name="Simple 2", value=2),
        ]
        SimpleModel.objects.bulk_create(simple_instances)

        # Verify hooks were called for both models
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 2)

    def test_hooks_performance(self):
        """Test hooks performance with large datasets."""

        _active_hooks.add("performance")
        hook_instance = PerformanceTestHook()

        # Create many instances
        test_instances = []
        for i in range(100):
            test_instances.append(
                HookModel(name=f"Test {i}", value=i, created_by=self.user)
            )

        # Test bulk_create performance
        with self.assertNumQueries(3):  # SAVEPOINT, INSERT, RELEASE SAVEPOINT
            created_instances = HookModel.objects.bulk_create(test_instances)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)
        self.assertEqual(len(created_instances), 100)

        # Test bulk_update performance
        # The current implementation does individual queries for each instance
        # plus the bulk update query, so we expect more than 1 query
        with self.assertNumQueries(107):  # 100 individual SELECTs + 1 bulk UPDATE + 1 bulk SELECT + 6 transaction queries
            updated_count = HookModel.objects.bulk_update(created_instances, ["value"])

        self.assertEqual(updated_count, 100)

        # Test bulk_delete performance
        # The current implementation does individual queries for each instance
        # plus the bulk delete queries, so we expect more than 1 query
        with self.assertNumQueries(105):  # 100 individual SELECTs + 1 bulk SELECT + 2 DELETE queries + 2 transaction queries
            deleted_count = HookModel.objects.bulk_delete(created_instances)

        self.assertEqual(deleted_count, 100)


class TestRealWorldScenarios(TestCase):
    """Test real-world usage scenarios."""

    def setUp(self):
        from django.utils import timezone

        # Create test data using bulk_create to avoid RETURNING clause issues
        users = UserModel.objects.bulk_create([
            UserModel(username="testuser", email="test@example.com", is_active=True, created_at=timezone.now())
        ])
        self.user = users[0]

        categories = Category.objects.bulk_create([
            Category(name="Test Category", description="", is_active=True)
        ])
        self.category = categories[0]
        
        # Reset hook class variables
        AuditHook.audit_log.clear()
        InventoryHook.low_stock_alerts.clear()
        UserRegistrationHook.welcome_emails_sent.clear()
        
        # Reset trackers
        UserRegistrationHook.tracker.reset()
        
        # Clear active hooks
        _active_hooks.clear()
        
        # Re-register test hooks after clearing
        self._register_test_hooks()

    def _register_test_hooks(self):
        """Register the hooks needed for this test class."""
        from tests.utils import re_register_test_hooks
        re_register_test_hooks()

    def test_user_registration_workflow(self):
        """Test a user registration workflow with hooks using HookModel."""

        _active_hooks.add("user_registration")
        hook_instance = UserRegistrationHook()

        # Register multiple users using SimpleModel with available fields
        new_users = [
            SimpleModel(name="user1", value=100),
            SimpleModel(name="user2", value=200),
            SimpleModel(name="user3", value=300),
        ]

        # This should trigger validation and welcome emails
        created_users = SimpleModel.objects.bulk_create(new_users)

        # Verify hooks were called
        self.assertEqual(len(UserRegistrationHook.tracker.before_create_calls), 1)
        self.assertEqual(len(UserRegistrationHook.tracker.after_create_calls), 1)

        # Verify welcome emails were sent (using names instead of emails)
        self.assertEqual(len(UserRegistrationHook.welcome_emails_sent), 3)
        self.assertIn("user1", UserRegistrationHook.welcome_emails_sent)
        self.assertIn("user2", UserRegistrationHook.welcome_emails_sent)
        self.assertIn("user3", UserRegistrationHook.welcome_emails_sent)

    def test_inventory_management_workflow(self):
        """Test an inventory management workflow with hooks."""

        _active_hooks.add("inventory")
        hook_instance = InventoryHook()

        # Create inventory items
        inventory_items = [
            HookModel(name="Item 1", value=50, created_by=self.user),
            HookModel(name="Item 2", value=15, created_by=self.user),
            HookModel(name="Item 3", value=25, created_by=self.user),
        ]
        created_items = HookModel.objects.bulk_create(inventory_items)

        # Update stock levels (some going below 10)
        created_items[0].value = 5  # Goes below 10
        created_items[1].value = 8  # Goes below 10
        created_items[2].value = 20  # Stays above 10

        HookModel.objects.bulk_update(created_items, ["value"])

        # Verify low stock alerts
        self.assertEqual(len(InventoryHook.low_stock_alerts), 2)
        # Hooks are modifying names, so expect "Modified Item X"
        self.assertIn("Modified Item 1", InventoryHook.low_stock_alerts)
        self.assertIn("Modified Item 2", InventoryHook.low_stock_alerts)

        # Delete some items
        HookModel.objects.bulk_delete([created_items[0]])

        # Verify deletion was logged
        self.assertEqual(len(InventoryHook.tracker.after_delete_calls), 1)

    def test_audit_trail_workflow(self):
        """Test an audit trail workflow with hooks."""

        _active_hooks.add("audit")
        hook_instance = AuditHook()
        


        # Create records
        records = [
            HookModel(name="Record 1", status="draft", created_by=self.user),
            HookModel(name="Record 2", status="draft", created_by=self.user),
        ]
        created_records = HookModel.objects.bulk_create(records)

        # Update statuses
        created_records[0].status = "published"
        created_records[1].status = "archived"
        HookModel.objects.bulk_update(created_records, ["status"])

        # Delete one record
        HookModel.objects.bulk_delete([created_records[0]])

        # Verify audit log
        print(f"Audit log contents: {AuditHook.audit_log}")
        # Hooks are modifying names, so we expect 5 entries: 2 creates + 2 updates + 1 delete
        self.assertEqual(len(AuditHook.audit_log), 5)
        # Hooks are modifying names, so expect "Modified Record X"
        self.assertIn("Created: Modified Record 1 by testuser", AuditHook.audit_log)
        self.assertIn("Created: Modified Record 2 by testuser", AuditHook.audit_log)
        self.assertIn(
            "Status changed: Modified Record 1 draft -> published", AuditHook.audit_log
        )
        self.assertIn(
            "Status changed: Modified Record 2 draft -> archived", AuditHook.audit_log
        )
        self.assertIn("Deleted: Modified Record 1", AuditHook.audit_log)
