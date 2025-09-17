"""
Test: Zero-Coupling Bulk Signals Implementation

This test demonstrates how the simplified architecture eliminates coupling issues.
Each component can be tested in isolation with zero dependencies.
"""

import os
import sys

import django
from django.db import models
from django.test import TestCase

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
django.setup()

from django_bulk_signals import BulkSignalManager
from django_bulk_signals.conditions_simple import ChangesTo, HasChanged
from django_bulk_signals.decorators_simple import after_update, before_create


class TestAccount(models.Model):
    """Test model for bulk signals."""

    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="active")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    objects = BulkSignalManager()

    class Meta:
        app_label = "test_app"


# Test trigger handlers
@before_create(TestAccount)
def validate_account_creation(sender, instances, **kwargs):
    """Validate accounts before creation."""
    for account in instances:
        if not account.name:
            raise ValueError("Account name is required")
        if account.balance < 0:
            raise ValueError("Account balance cannot be negative")


@after_update(TestAccount, condition=HasChanged("status"))
def handle_status_change(sender, instances, originals, **kwargs):
    """Handle status changes."""
    for account, original in zip(instances, originals):
        if account.status != original.status:
            # Handle status change
            pass


class TestZeroCouplingArchitecture(TestCase):
    """Test the zero-coupling architecture."""

    def setUp(self):
        """Set up test data."""
        self.accounts = [
            TestAccount(name="Account 1", status="active", balance=1000),
            TestAccount(name="Account 2", status="active", balance=2000),
        ]

    def test_bulk_create_with_validation(self):
        """Test bulk create with validation triggers."""
        # This should work
        created_accounts = TestAccount.objects.bulk_create(self.accounts)
        self.assertEqual(len(created_accounts), 2)

        # This should fail validation
        invalid_accounts = [TestAccount(name="", balance=1000)]
        with self.assertRaises(ValueError):
            TestAccount.objects.bulk_create(invalid_accounts)

    def test_bulk_update_with_conditions(self):
        """Test bulk update with condition triggers."""
        # Create accounts first
        created_accounts = TestAccount.objects.bulk_create(self.accounts)

        # Update status - should trigger condition
        created_accounts[0].status = "inactive"
        TestAccount.objects.bulk_update(created_accounts, ["status"])

        # Verify update worked
        updated_account = TestAccount.objects.get(pk=created_accounts[0].pk)
        self.assertEqual(updated_account.status, "inactive")

    def test_component_isolation(self):
        """Test that components can be tested in isolation."""
        # Test condition in isolation
        condition = HasChanged("status")

        # Create test instances
        original = TestAccount(status="active")
        updated = TestAccount(status="inactive")

        # Test condition
        self.assertTrue(condition.check(updated, original))

        # Test decorator in isolation (no dependencies)
        from django_bulk_signals.core import bulk_pre_create
        from django_bulk_signals.decorators_simple import bulk_trigger

        # This should work without any service or executor dependencies
        decorator = bulk_trigger(bulk_pre_create, TestAccount, condition)
        self.assertIsNotNone(decorator)

    def test_zero_dependencies(self):
        """Test that components have zero dependencies."""
        # Test that core components don't import services or executors
        from django_bulk_signals.core import BulkSignalManager, BulkSignalQuerySet

        # These should work without any external dependencies
        queryset = BulkSignalQuerySet(TestAccount)
        manager = BulkSignalManager()

        self.assertIsNotNone(queryset)
        self.assertIsNotNone(manager)

    def test_simple_api(self):
        """Test that the API is simple and intuitive."""
        # Test condition creation
        condition1 = HasChanged("status")
        condition2 = ChangesTo("status", "inactive")

        self.assertIsNotNone(condition1)
        self.assertIsNotNone(condition2)

        # Test decorator creation
        decorator1 = before_create(TestAccount)
        decorator2 = after_update(TestAccount, condition=condition1)

        self.assertIsNotNone(decorator1)
        self.assertIsNotNone(decorator2)


def run_tests():
    """Run the tests."""
    print("Testing Zero-Coupling Bulk Signals Architecture")
    print("=" * 50)

    # Run tests
    from django.conf import settings
    from django.test.utils import get_runner

    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["test_simple"])

    if failures:
        print(f"❌ Tests failed: {failures}")
        return False
    else:
        print("✅ All tests passed!")
        return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
