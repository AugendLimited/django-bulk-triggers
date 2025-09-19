"""
Integration tests for django-bulk-signals.

These tests demonstrate real-world usage patterns and verify that the package
works correctly when used as intended by end users.
"""

from django.db import models
from django.dispatch import receiver
from django.test import TestCase
from django.utils import timezone
from django_bulk_signals.models import BulkSignalModel
from django_bulk_signals.signals import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)


# Real-world example models that users would create
class User(BulkSignalModel):
    """Example user model that users would create."""

    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "tests"


class Order(BulkSignalModel):
    """Example order model that users would create."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_name = models.CharField(max_length=200)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "tests"


class AuditLog(models.Model):
    """Audit log model to track bulk operations."""

    operation_type = models.CharField(max_length=20)  # create, update, delete
    model_name = models.CharField(max_length=100)
    instance_count = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)

    class Meta:
        app_label = "tests"


# Signal receivers - this is how users would actually connect signals
@receiver(bulk_pre_create, sender=User)
@receiver(bulk_pre_create, sender=Order)
def audit_pre_create(sender, instances, **kwargs):
    """Audit pre-create signal - this is what users would write."""
    # Get the current test instance for tracking
    test_instance = getattr(TestBulkSignalsIntegration, "_current_instance", None)
    if test_instance:
        test_instance.signal_calls["pre_create"].append(
            {"sender": sender.__name__, "count": len(instances), "kwargs": kwargs}
        )


@receiver(bulk_post_create, sender=User)
@receiver(bulk_post_create, sender=Order)
def audit_post_create(sender, instances, **kwargs):
    """Audit post-create signal - this is what users would write."""
    # Get the current test instance for tracking
    test_instance = getattr(TestBulkSignalsIntegration, "_current_instance", None)
    if test_instance:
        test_instance.signal_calls["post_create"].append(
            {"sender": sender.__name__, "count": len(instances), "kwargs": kwargs}
        )

        # Create audit log entry (filter out non-serializable objects)
        serializable_kwargs = {
            k: v
            for k, v in kwargs.items()
            if not hasattr(v, "__class__")
            or v.__class__.__name__ not in ["Signal", "WeakSet"]
        }

        AuditLog.objects.create(
            operation_type="create",
            model_name=sender.__name__,
            instance_count=len(instances),
            details={"kwargs": serializable_kwargs},
        )


@receiver(bulk_pre_update, sender=User)
@receiver(bulk_pre_update, sender=Order)
def audit_pre_update(sender, instances, originals, fields, **kwargs):
    """Audit pre-update signal - this is what users would write."""
    # Get the current test instance for tracking
    test_instance = getattr(TestBulkSignalsIntegration, "_current_instance", None)
    if test_instance:
        test_instance.signal_calls["pre_update"].append(
            {
                "sender": sender.__name__,
                "count": len(instances),
                "fields": fields,
                "kwargs": kwargs,
            }
        )


@receiver(bulk_post_update, sender=User)
@receiver(bulk_post_update, sender=Order)
def audit_post_update(sender, instances, originals, fields, **kwargs):
    """Audit post-update signal - this is what users would write."""
    # Get the current test instance for tracking
    test_instance = getattr(TestBulkSignalsIntegration, "_current_instance", None)
    if test_instance:
        test_instance.signal_calls["post_update"].append(
            {
                "sender": sender.__name__,
                "count": len(instances),
                "fields": fields,
                "kwargs": kwargs,
            }
        )

        # Create audit log entry (filter out non-serializable objects)
        serializable_kwargs = {
            k: v
            for k, v in kwargs.items()
            if not hasattr(v, "__class__")
            or v.__class__.__name__ not in ["Signal", "WeakSet"]
        }

        AuditLog.objects.create(
            operation_type="update",
            model_name=sender.__name__,
            instance_count=len(instances),
            details={"fields": fields, "kwargs": serializable_kwargs},
        )


@receiver(bulk_pre_delete, sender=User)
@receiver(bulk_pre_delete, sender=Order)
def audit_pre_delete(sender, instances, **kwargs):
    """Audit pre-delete signal - this is what users would write."""
    # Get the current test instance for tracking
    test_instance = getattr(TestBulkSignalsIntegration, "_current_instance", None)
    if test_instance:
        test_instance.signal_calls["pre_delete"].append(
            {"sender": sender.__name__, "count": len(instances), "kwargs": kwargs}
        )


@receiver(bulk_post_delete, sender=User)
@receiver(bulk_post_delete, sender=Order)
def audit_post_delete(sender, instances, **kwargs):
    """Audit post-delete signal - this is what users would write."""
    # Get the current test instance for tracking
    test_instance = getattr(TestBulkSignalsIntegration, "_current_instance", None)
    if test_instance:
        test_instance.signal_calls["post_delete"].append(
            {"sender": sender.__name__, "count": len(instances), "kwargs": kwargs}
        )

        # Create audit log entry (filter out non-serializable objects)
        serializable_kwargs = {
            k: v
            for k, v in kwargs.items()
            if not hasattr(v, "__class__")
            or v.__class__.__name__ not in ["Signal", "WeakSet"]
        }

        AuditLog.objects.create(
            operation_type="delete",
            model_name=sender.__name__,
            instance_count=len(instances),
            details={"kwargs": serializable_kwargs},
        )


class TestBulkSignalsIntegration(TestCase):
    """Test real-world usage patterns."""

    def setUp(self):
        """Set up test data for each test."""
        # Set the current test instance for signal receivers
        TestBulkSignalsIntegration._current_instance = self

        # Clear any existing audit logs
        AuditLog.objects.all().delete()

        # Reset signal calls tracking for this test
        self.signal_calls = {
            "pre_create": [],
            "post_create": [],
            "pre_update": [],
            "post_update": [],
            "pre_delete": [],
            "post_delete": [],
        }

    def test_bulk_create_users(self):
        """Test bulk creating users - real-world scenario."""
        # Create multiple users at once
        users = [
            User(username="alice", email="alice@example.com"),
            User(username="bob", email="bob@example.com"),
            User(username="charlie", email="charlie@example.com"),
        ]

        # Bulk create users
        created_users = User.objects.bulk_create(users)

        # Verify users were created
        self.assertEqual(len(created_users), 3)
        self.assertEqual(User.objects.count(), 3)

        # Verify signals were fired
        self.assertEqual(len(self.signal_calls["pre_create"]), 1)
        self.assertEqual(len(self.signal_calls["post_create"]), 1)

        # Verify signal data
        pre_call = self.signal_calls["pre_create"][0]
        self.assertEqual(pre_call["sender"], "User")
        self.assertEqual(pre_call["count"], 3)

        post_call = self.signal_calls["post_create"][0]
        self.assertEqual(post_call["sender"], "User")
        self.assertEqual(post_call["count"], 3)

        # Verify audit log was created
        audit_logs = AuditLog.objects.filter(operation_type="create", model_name="User")
        self.assertEqual(audit_logs.count(), 1)
        self.assertEqual(audit_logs.first().instance_count, 3)

    def test_bulk_update_users(self):
        """Test bulk updating users - real-world scenario."""
        # Create users first
        users = [
            User.objects.create(username="alice", email="alice@example.com"),
            User.objects.create(username="bob", email="bob@example.com"),
        ]

        # Modify users
        users[0].email = "alice.new@example.com"
        users[0].is_active = False
        users[1].email = "bob.new@example.com"

        # Bulk update users
        updated_count = User.objects.bulk_update(users, fields=["email", "is_active"])

        # Verify update worked
        self.assertEqual(updated_count, 2)

        # Verify signals were fired
        self.assertEqual(len(self.signal_calls["pre_update"]), 1)
        self.assertEqual(len(self.signal_calls["post_update"]), 1)

        # Verify signal data
        pre_call = self.signal_calls["pre_update"][0]
        self.assertEqual(pre_call["sender"], "User")
        self.assertEqual(pre_call["count"], 2)
        self.assertIn("email", pre_call["fields"])
        self.assertIn("is_active", pre_call["fields"])

        # Verify audit log was created
        audit_logs = AuditLog.objects.filter(operation_type="update", model_name="User")
        self.assertEqual(audit_logs.count(), 1)
        self.assertEqual(audit_logs.first().instance_count, 2)

    def test_bulk_delete_users(self):
        """Test bulk deleting users - real-world scenario."""
        # Create users first
        users = [
            User.objects.create(username="alice", email="alice@example.com"),
            User.objects.create(username="bob", email="bob@example.com"),
        ]

        # Bulk delete users
        deleted_count = User.objects.bulk_delete(users)

        # Verify delete worked
        self.assertEqual(deleted_count, 2)
        self.assertEqual(User.objects.count(), 0)

        # Verify signals were fired
        self.assertEqual(len(self.signal_calls["pre_delete"]), 1)
        self.assertEqual(len(self.signal_calls["post_delete"]), 1)

        # Verify signal data
        pre_call = self.signal_calls["pre_delete"][0]
        self.assertEqual(pre_call["sender"], "User")
        self.assertEqual(pre_call["count"], 2)

        # Verify audit log was created
        audit_logs = AuditLog.objects.filter(operation_type="delete", model_name="User")
        self.assertEqual(audit_logs.count(), 1)
        self.assertEqual(audit_logs.first().instance_count, 2)

    def test_auto_field_detection(self):
        """Test automatic field detection - real-world scenario."""
        # Create user
        user = User.objects.create(username="alice", email="alice@example.com")
        original_updated_at = user.updated_at

        # Wait a bit to ensure timestamp difference
        import time

        time.sleep(0.01)

        # Modify user
        user.email = "alice.new@example.com"
        user.is_active = False

        # Bulk update without specifying fields (auto-detection)
        updated_count = User.objects.bulk_update([user])

        # Verify update worked
        self.assertEqual(updated_count, 1)

        # Verify auto_now field was updated
        user.refresh_from_db()
        self.assertGreater(user.updated_at, original_updated_at)

        # Verify signals were fired with detected fields
        pre_call = self.signal_calls["pre_update"][0]
        detected_fields = pre_call["fields"]

        # Should detect both changed fields plus auto_now field
        self.assertIn("email", detected_fields)
        self.assertIn("is_active", detected_fields)
        self.assertIn("updated_at", detected_fields)  # auto_now field
        self.assertNotIn("id", detected_fields)  # PK should be excluded

    def test_mixed_operations(self):
        """Test mixed bulk operations - real-world scenario."""
        # Create some users
        users = [
            User.objects.create(username="alice", email="alice@example.com"),
            User.objects.create(username="bob", email="bob@example.com"),
        ]

        # Create some orders
        orders = [
            Order.objects.create(user=users[0], product_name="Widget A", price=10.00),
            Order.objects.create(user=users[1], product_name="Widget B", price=20.00),
        ]

        # Modify users
        users[0].email = "alice.new@example.com"
        users[1].email = "bob.new@example.com"

        # Modify orders
        orders[0].status = "shipped"
        orders[1].status = "delivered"

        # Bulk update both models
        User.objects.bulk_update(users, fields=["email"])
        Order.objects.bulk_update(orders, fields=["status"])

        # Verify signals were fired for both models
        user_pre_calls = [
            call for call in self.signal_calls["pre_update"] if call["sender"] == "User"
        ]
        user_post_calls = [
            call
            for call in self.signal_calls["post_update"]
            if call["sender"] == "User"
        ]
        order_pre_calls = [
            call
            for call in self.signal_calls["pre_update"]
            if call["sender"] == "Order"
        ]
        order_post_calls = [
            call
            for call in self.signal_calls["post_update"]
            if call["sender"] == "Order"
        ]

        self.assertEqual(len(user_pre_calls), 1)
        self.assertEqual(len(user_post_calls), 1)
        self.assertEqual(len(order_pre_calls), 1)
        self.assertEqual(len(order_post_calls), 1)

        # Verify audit logs were created for both models
        user_audit_logs = AuditLog.objects.filter(
            operation_type="update", model_name="User"
        )
        order_audit_logs = AuditLog.objects.filter(
            operation_type="update", model_name="Order"
        )

        self.assertEqual(user_audit_logs.count(), 1)
        self.assertEqual(order_audit_logs.count(), 1)

    def test_signal_arguments_passed_through(self):
        """Test that signal arguments are passed through correctly."""
        # Create users with specific arguments
        users = [
            User(username="alice", email="alice@example.com"),
            User(username="bob", email="bob@example.com"),
        ]

        # Bulk create with arguments
        User.objects.bulk_create(users, batch_size=100, ignore_conflicts=True)

        # Verify arguments were passed to signals
        pre_call = self.signal_calls["pre_create"][0]
        self.assertEqual(pre_call["kwargs"]["batch_size"], 100)
        self.assertEqual(pre_call["kwargs"]["ignore_conflicts"], True)

        post_call = self.signal_calls["post_create"][0]
        self.assertEqual(post_call["kwargs"]["batch_size"], 100)
        self.assertEqual(post_call["kwargs"]["ignore_conflicts"], True)

    def test_foreign_key_relationships(self):
        """Test bulk operations with foreign key relationships."""
        # Create user
        user = User.objects.create(username="alice", email="alice@example.com")

        # Create orders
        orders = [
            Order(user=user, product_name="Widget A", price=10.00),
            Order(user=user, product_name="Widget B", price=20.00),
        ]

        # Bulk create orders
        created_orders = Order.objects.bulk_create(orders)

        # Verify orders were created with correct relationships
        self.assertEqual(len(created_orders), 2)
        self.assertEqual(Order.objects.count(), 2)

        # Verify foreign key relationships
        for order in created_orders:
            self.assertEqual(order.user, user)

        # Verify signals were fired
        order_pre_calls = [
            call
            for call in self.signal_calls["pre_create"]
            if call["sender"] == "Order"
        ]
        order_post_calls = [
            call
            for call in self.signal_calls["post_create"]
            if call["sender"] == "Order"
        ]

        self.assertEqual(len(order_pre_calls), 1)
        self.assertEqual(len(order_post_calls), 1)

    def test_error_handling(self):
        """Test error handling in bulk operations."""
        # Try to bulk create users with duplicate usernames
        users = [
            User(username="alice", email="alice@example.com"),
            User(username="alice", email="alice2@example.com"),  # Duplicate username
        ]

        # This should raise an IntegrityError
        with self.assertRaises(Exception):  # IntegrityError or similar
            User.objects.bulk_create(users)

        # Verify no users were created
        self.assertEqual(User.objects.count(), 0)

        # Verify signals were still fired (pre_create at least)
        self.assertEqual(len(self.signal_calls["pre_create"]), 1)
        # post_create might not fire if the operation fails
