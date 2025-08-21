"""
Integration tests for django-bulk-hooks.
"""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import TestCase

from django_bulk_hooks import BulkHookManager, Hook
from django_bulk_hooks.conditions import HasChanged, IsEqual, IsNotEqual, WasEqual
from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.decorators import hook
from django_bulk_hooks.priority import Priority
from tests.models import Category, RelatedModel, SimpleModel, TestModel, User
from tests.utils import TestHookTracker, create_test_instances

# Define hook classes at module level to ensure registration
# Use separate trackers for each hook class
_create_tracker = TestHookTracker()
_update_tracker = TestHookTracker()
_delete_tracker = TestHookTracker()


class BulkCreateTestHook(Hook):
    def __init__(self):
        self.tracker = _create_tracker

    @hook(BEFORE_CREATE, model=TestModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)
        # Modify records before creation
        for record in new_records:
            record.name = f"Modified {record.name}"

    @hook(AFTER_CREATE, model=TestModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)


class BulkUpdateTestHook(Hook):
    def __init__(self):
        self.tracker = _update_tracker

    @hook(BEFORE_UPDATE, model=TestModel)
    def on_before_update(self, new_records, old_records=None, **kwargs):
        self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)

    @hook(AFTER_UPDATE, model=TestModel)
    def on_after_update(self, new_records, old_records=None, **kwargs):
        self.tracker.add_call(AFTER_UPDATE, new_records, old_records, **kwargs)


class BulkDeleteTestHook(Hook):
    def __init__(self):
        self.tracker = _delete_tracker

    @hook(BEFORE_DELETE, model=TestModel)
    def on_before_delete(self, new_records, old_records=None, **kwargs):
        self.tracker.add_call(BEFORE_DELETE, new_records, old_records, **kwargs)

    @hook(AFTER_DELETE, model=TestModel)
    def on_after_delete(self, new_records, old_records=None, **kwargs):
        self.tracker.add_call(AFTER_DELETE, new_records, old_records, **kwargs)


# Additional hook classes for specific test scenarios
_conditional_tracker = TestHookTracker()
_complex_conditional_tracker = TestHookTracker()
_error_tracker = TestHookTracker()
_performance_tracker = TestHookTracker()
_related_tracker = TestHookTracker()
_transaction_tracker = TestHookTracker()
_multi_model_tracker = TestHookTracker()
_priority_tracker = TestHookTracker()

# Global flags to control which hooks are active
_active_hooks = set()


class ConditionalTestHook(Hook):
    def __init__(self):
        self.tracker = _conditional_tracker

    @hook(BEFORE_CREATE, model=TestModel, condition=IsEqual("status", "active"))
    def on_active_create(self, new_records, old_records=None, **kwargs):
        if "conditional" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_UPDATE, model=TestModel, condition=HasChanged("status"))
    def on_status_change(self, new_records, old_records=None, **kwargs):
        if "conditional" in _active_hooks:
            self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)


class ComplexConditionalTestHook(Hook):
    def __init__(self):
        self.tracker = _complex_conditional_tracker

    @hook(
        BEFORE_UPDATE,
        model=TestModel,
        condition=(
            HasChanged("status")
            & (IsEqual("status", "active") | IsEqual("status", "inactive"))
        ),
    )
    def on_status_change(self, new_records, old_records=None, **kwargs):
        if "complex_conditional" in _active_hooks:
            self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)


class ErrorTestHook(Hook):
    error_count = 0  # Class variable to persist across instances
    
    def __init__(self):
        self.tracker = _error_tracker

    @hook(BEFORE_CREATE, model=TestModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        if "error" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)
            # Simulate an error
            if len(new_records) > 1:
                ErrorTestHook.error_count += 1  # Use class variable
                raise ValueError("Simulated error")


class PerformanceTestHook(Hook):
    def __init__(self):
        self.tracker = _performance_tracker

    @hook(BEFORE_CREATE, model=TestModel)
    def on_before_create(self, new_records, old_records=None, **kwargs):
        if "performance" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


class RelatedTestHook(Hook):
    def __init__(self):
        self.tracker = _related_tracker

    @hook(AFTER_CREATE, model=TestModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        if "related" in _active_hooks:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
            # Create related objects when this hook is active
            for record in new_records:
                RelatedModel.objects.create(
                    test_model=record,
                    amount=record.value * 10,
                    description=f"Related to {record.name}",
                )


class TransactionTestHook(Hook):
    def __init__(self):
        self.tracker = _transaction_tracker

    @hook(AFTER_CREATE, model=TestModel)
    def on_after_create(self, new_records, old_records=None, **kwargs):
        if "transaction" in _active_hooks:
            self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)


class MultiModelTestHook(Hook):
    def __init__(self):
        self.tracker = _multi_model_tracker

    @hook(BEFORE_CREATE, model=TestModel)
    def on_test_model_create(self, new_records, old_records=None, **kwargs):
        if "multi_model" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_CREATE, model=SimpleModel)
    def on_simple_model_create(self, new_records, old_records=None, **kwargs):
        if "multi_model" in _active_hooks:
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


class PriorityTestHook(Hook):
    execution_order = []  # Class variable to persist across instances
    
    def __init__(self):
        self.tracker = _priority_tracker

    @hook(BEFORE_CREATE, model=TestModel, priority=Priority.LOW)
    def low_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_hooks:
            PriorityTestHook.execution_order.append("low")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_CREATE, model=TestModel, priority=Priority.HIGH)
    def high_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_hooks:
            PriorityTestHook.execution_order.append("high")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)

    @hook(BEFORE_CREATE, model=TestModel, priority=Priority.NORMAL)
    def normal_priority(self, new_records, old_records=None, **kwargs):
        if "priority" in _active_hooks:
            PriorityTestHook.execution_order.append("normal")  # Use class variable
            self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)


class TestFullSystemIntegration(TestCase):
    """Test the entire system working together."""

    def setUp(self):
        self.tracker = TestHookTracker()
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.category = Category.objects.create(name="Test Category")
        
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

        # Clear active hooks
        _active_hooks.clear()
    
    def _register_test_hooks(self):
        """Register the hooks needed for this test class."""
        # The hooks are automatically registered when the classes are defined
        # We just need to ensure they're available
        pass

    def test_complete_bulk_create_workflow(self):
        """Test complete bulk_create workflow with hooks."""

        hook_instance = BulkCreateTestHook()

        # Create test instances
        test_instances = [
            TestModel(
                name="Test 1", value=1, created_by=self.user, category=self.category
            ),
            TestModel(
                name="Test 2", value=2, created_by=self.user, category=self.category
            ),
            TestModel(
                name="Test 3", value=3, created_by=self.user, category=self.category
            ),
        ]

        # Perform bulk_create
        created_instances = TestModel.objects.bulk_create(test_instances)

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
            TestModel(name="Test 1", value=1, created_by=self.user),
            TestModel(name="Test 2", value=2, created_by=self.user),
            TestModel(name="Test 3", value=3, created_by=self.user),
        ]
        created_instances = TestModel.objects.bulk_create(test_instances)

        # Modify instances for update
        for instance in created_instances:
            instance.value *= 2
            instance.status = "updated"

        # Perform bulk_update
        updated_count = TestModel.objects.bulk_update(
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
            TestModel(name="Test 1", value=1, created_by=self.user),
            TestModel(name="Test 2", value=2, created_by=self.user),
            TestModel(name="Test 3", value=3, created_by=self.user),
        ]
        created_instances = TestModel.objects.bulk_create(
            test_instances, bypass_hooks=True
        )

        # Perform bulk_delete
        deleted_count = TestModel.objects.bulk_delete(created_instances)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.before_delete_calls), 1)
        self.assertEqual(len(hook_instance.tracker.after_delete_calls), 1)

        # Verify deletion was successful
        self.assertEqual(deleted_count, 3)

        # Verify instances are gone
        remaining_count = TestModel.objects.count()
        self.assertEqual(remaining_count, 0)

    def test_hooks_with_conditions(self):
        """Test hooks with various conditions."""

        _active_hooks.add("conditional")
        hook_instance = ConditionalTestHook()

        # Create instances with different statuses
        test_instances = [
            TestModel(name="Active 1", status="active", created_by=self.user),
            TestModel(name="Inactive 1", status="inactive", created_by=self.user),
            TestModel(name="Active 2", status="active", created_by=self.user),
        ]

        # Only active instances should trigger the hook
        TestModel.objects.bulk_create(test_instances)
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)

        # Get created instances
        created_instances = TestModel.objects.all()

        # Update status of some instances
        for i, instance in enumerate(created_instances):
            if i == 0:  # Change from active to inactive
                instance.status = "inactive"
            elif i == 1:  # Change from inactive to active
                instance.status = "active"
            # i == 2: No change

        # Only changed instances should trigger the hook
        TestModel.objects.bulk_update(created_instances, ["status"])
        self.assertEqual(len(hook_instance.tracker.before_update_calls), 1)

    def test_hooks_with_priorities(self):
        """Test hooks with different priorities."""

        _active_hooks.add("priority")
        hook_instance = PriorityTestHook()

        # Create test instances
        test_instances = [
            TestModel(name="Test 1", value=1, created_by=self.user),
            TestModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Perform bulk_create
        TestModel.objects.bulk_create(test_instances)

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
            TestModel(name="Test 1", value=1, created_by=self.user),
            TestModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Test without bypass (hooks should run)
        TestModel.objects.bulk_create(test_instances, bypass_hooks=False)
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)

        # Clear tracker
        hook_instance.tracker.reset()

        # Test with bypass (hooks should not run)
        test_instances2 = [
            TestModel(name="Test 3", value=3, created_by=self.user),
            TestModel(name="Test 4", value=4, created_by=self.user),
        ]
        TestModel.objects.bulk_create(test_instances2, bypass_hooks=True)
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 0)

    def test_hooks_with_transactions(self):
        """Test hooks with database transactions."""

        _active_hooks.add("transaction")
        hook_instance = TransactionTestHook()

        # Test with transaction
        with transaction.atomic():
            test_instances = [
                TestModel(name="Test 1", value=1, created_by=self.user),
                TestModel(name="Test 2", value=2, created_by=self.user),
            ]

            # Hooks are called immediately (not deferred)
            TestModel.objects.bulk_create(test_instances)

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
            TestModel(name="Test 1", value=1, created_by=self.user),
            TestModel(name="Test 2", value=2, created_by=self.user),
        ]

        # Perform bulk_create
        created_instances = TestModel.objects.bulk_create(test_instances)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.after_create_calls), 1)

        # Verify related objects were created
        for instance in created_instances:
            related_count = RelatedModel.objects.filter(test_model=instance).count()
            self.assertEqual(related_count, 1)

            related = RelatedModel.objects.get(test_model=instance)
            self.assertEqual(related.amount, instance.value * 10)

    def test_hooks_with_error_handling(self):
        """Test hooks with error handling."""

        _active_hooks.add("error")
        hook_instance = ErrorTestHook()

        # Create test instances
        test_instances = [
            TestModel(name="Test 1", value=1, created_by=self.user),
            TestModel(name="Test 2", value=2, created_by=self.user),
        ]

        # This should raise an exception due to the hook error
        with self.assertRaises(ValueError):
            TestModel.objects.bulk_create(test_instances)

        # Verify hook was called and error was raised
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)
        self.assertEqual(hook_instance.error_count, 1)

        # Verify instances were NOT created due to the exception
        self.assertEqual(TestModel.objects.count(), 0)

    def test_hooks_with_complex_conditions(self):
        """Test hooks with complex condition combinations."""

        _active_hooks.add("complex_conditional")
        hook_instance = ComplexConditionalTestHook()

        # Create initial instances
        test_instances = [
            TestModel(name="Test 1", status="pending", created_by=self.user),
            TestModel(name="Test 2", status="pending", created_by=self.user),
        ]
        created_instances = TestModel.objects.bulk_create(test_instances)

        # Update statuses
        created_instances[0].status = "active"
        created_instances[1].status = "inactive"

        # Only the changed instances should trigger the hook
        TestModel.objects.bulk_update(created_instances, ["status"])
        self.assertEqual(len(hook_instance.tracker.before_update_calls), 1)

        # Update again without changes
        TestModel.objects.bulk_update(created_instances, ["status"])
        self.assertEqual(
            len(hook_instance.tracker.before_update_calls), 1
        )  # No additional calls

    def test_hooks_with_multiple_models(self):
        """Test hooks with multiple model types."""

        _active_hooks.add("multi_model")
        hook_instance = MultiModelTestHook()

        # Create TestModel instances
        test_instances = [
            TestModel(name="Test 1", value=1, created_by=self.user),
            TestModel(name="Test 2", value=2, created_by=self.user),
        ]
        TestModel.objects.bulk_create(test_instances)

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
                TestModel(name=f"Test {i}", value=i, created_by=self.user)
            )

        # Test bulk_create performance
        with self.assertNumQueries(3):  # SAVEPOINT, INSERT, RELEASE SAVEPOINT
            created_instances = TestModel.objects.bulk_create(test_instances)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)
        self.assertEqual(len(created_instances), 100)

        # Test bulk_update performance
        # The current implementation does individual queries for each instance
        # plus the bulk update query, so we expect more than 1 query
        with self.assertNumQueries(107):  # 100 individual SELECTs + 1 bulk UPDATE + 1 bulk SELECT + 6 transaction queries
            updated_count = TestModel.objects.bulk_update(created_instances, ["value"])

        self.assertEqual(updated_count, 100)

        # Test bulk_delete performance
        # The current implementation does individual queries for each instance
        # plus the bulk delete queries, so we expect more than 1 query
        with self.assertNumQueries(105):  # 100 individual SELECTs + 1 bulk SELECT + 2 DELETE queries + 2 transaction queries
            deleted_count = TestModel.objects.bulk_delete(created_instances)

        self.assertEqual(deleted_count, 100)


class TestRealWorldScenarios(TestCase):
    """Test real-world usage scenarios."""

    def setUp(self):
        self.user = User.objects.create(username="testuser", email="test@example.com")
        self.category = Category.objects.create(name="Test Category")

    def test_user_registration_workflow(self):
        """Test a user registration workflow with hooks."""

        class UserRegistrationHook(Hook):
            def __init__(self):
                self.tracker = TestHookTracker()
                self.welcome_emails_sent = []

            @hook(BEFORE_CREATE, model=User)
            def validate_user(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(BEFORE_CREATE, new_records, old_records, **kwargs)
                # Validate email format
                for user in new_records:
                    if "@" not in user.email:
                        raise ValueError(f"Invalid email: {user.email}")

            @hook(AFTER_CREATE, model=User)
            def send_welcome_email(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
                # Simulate sending welcome emails
                for user in new_records:
                    self.welcome_emails_sent.append(user.email)

        hook_instance = UserRegistrationHook()

        # Register multiple users
        new_users = [
            User(username="user1", email="user1@example.com"),
            User(username="user2", email="user2@example.com"),
            User(username="user3", email="user3@example.com"),
        ]

        # This should trigger validation and welcome emails
        created_users = User.objects.bulk_create(new_users)

        # Verify hooks were called
        self.assertEqual(len(hook_instance.tracker.before_create_calls), 1)
        self.assertEqual(len(hook_instance.tracker.after_create_calls), 1)

        # Verify welcome emails were sent
        self.assertEqual(len(hook_instance.welcome_emails_sent), 3)
        self.assertIn("user1@example.com", hook_instance.welcome_emails_sent)
        self.assertIn("user2@example.com", hook_instance.welcome_emails_sent)
        self.assertIn("user3@example.com", hook_instance.welcome_emails_sent)

    def test_inventory_management_workflow(self):
        """Test an inventory management workflow with hooks."""

        class InventoryHook(Hook):
            def __init__(self):
                self.tracker = TestHookTracker()
                self.low_stock_alerts = []

            @hook(BEFORE_UPDATE, model=TestModel, condition=HasChanged("value"))
            def check_stock_levels(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(BEFORE_UPDATE, new_records, old_records, **kwargs)
                # Check for low stock
                for new_record, old_record in zip(new_records, old_records or []):
                    if new_record.value < 10 and old_record.value >= 10:
                        self.low_stock_alerts.append(new_record.name)

            @hook(AFTER_DELETE, model=TestModel)
            def log_deletion(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(AFTER_DELETE, new_records, old_records, **kwargs)

        hook_instance = InventoryHook()

        # Create inventory items
        inventory_items = [
            TestModel(name="Item 1", value=50, created_by=self.user),
            TestModel(name="Item 2", value=15, created_by=self.user),
            TestModel(name="Item 3", value=25, created_by=self.user),
        ]
        created_items = TestModel.objects.bulk_create(inventory_items)

        # Update stock levels (some going below 10)
        created_items[0].value = 5  # Goes below 10
        created_items[1].value = 8  # Goes below 10
        created_items[2].value = 20  # Stays above 10

        TestModel.objects.bulk_update(created_items, ["value"])

        # Verify low stock alerts
        self.assertEqual(len(hook_instance.low_stock_alerts), 2)
        self.assertIn("Item 1", hook_instance.low_stock_alerts)
        self.assertIn("Item 2", hook_instance.low_stock_alerts)

        # Delete some items
        TestModel.objects.bulk_delete([created_items[0]])

        # Verify deletion was logged
        self.assertEqual(len(hook_instance.tracker.after_delete_calls), 1)

    def test_audit_trail_workflow(self):
        """Test an audit trail workflow with hooks."""

        class AuditHook(Hook):
            def __init__(self):
                self.tracker = TestHookTracker()
                self.audit_log = []

            @hook(AFTER_CREATE, model=TestModel)
            def log_creation(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(AFTER_CREATE, new_records, old_records, **kwargs)
                for record in new_records:
                    self.audit_log.append(
                        f"Created: {record.name} by {record.created_by.username}"
                    )

            @hook(AFTER_UPDATE, model=TestModel, condition=HasChanged("status"))
            def log_status_change(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(AFTER_UPDATE, new_records, old_records, **kwargs)
                for new_record, old_record in zip(new_records, old_records or []):
                    self.audit_log.append(
                        f"Status changed: {record.name} {old_record.status} -> {new_record.status}"
                    )

            @hook(AFTER_DELETE, model=TestModel)
            def log_deletion(self, new_records, old_records=None, **kwargs):
                self.tracker.add_call(AFTER_DELETE, new_records, old_records, **kwargs)
                for record in old_records:
                    self.audit_log.append(f"Deleted: {record.name}")

        hook_instance = AuditHook()

        # Create records
        records = [
            TestModel(name="Record 1", status="draft", created_by=self.user),
            TestModel(name="Record 2", status="draft", created_by=self.user),
        ]
        created_records = TestModel.objects.bulk_create(records)

        # Update statuses
        created_records[0].status = "published"
        created_records[1].status = "archived"
        TestModel.objects.bulk_update(created_records, ["status"])

        # Delete one record
        TestModel.objects.bulk_delete([created_records[0]])

        # Verify audit log
        self.assertEqual(len(hook_instance.audit_log), 4)
        self.assertIn("Created: Record 1 by testuser", hook_instance.audit_log)
        self.assertIn("Created: Record 2 by testuser", hook_instance.audit_log)
        self.assertIn(
            "Status changed: Record 1 draft -> published", hook_instance.audit_log
        )
        self.assertIn(
            "Status changed: Record 2 draft -> archived", hook_instance.audit_log
        )
        self.assertIn("Deleted: Record 1", hook_instance.audit_log)
