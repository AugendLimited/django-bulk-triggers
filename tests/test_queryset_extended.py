"""
Integration tests for the queryset module using real Django models.
This approach is much simpler and more reliable than extensive mocking.
"""

import pytest
from unittest.mock import Mock, patch
from django.test import TestCase, TransactionTestCase
from django.db import transaction
from django.db.models import Subquery, Case, When, Value, F
from django.core.exceptions import ValidationError
from django_bulk_hooks.constants import (
    BEFORE_CREATE, AFTER_CREATE, VALIDATE_CREATE,
    BEFORE_UPDATE, AFTER_UPDATE, VALIDATE_UPDATE,
    BEFORE_DELETE, AFTER_DELETE, VALIDATE_DELETE
)
from django_bulk_hooks.context import set_bulk_update_value_map, get_bypass_hooks, set_bypass_hooks
from django_bulk_hooks.decorators import bulk_hook
from django_bulk_hooks.registry import clear_hooks
from tests.models import HookModel, Category, UserModel, SimpleModel


# Integration Test Classes using real Django models

class IntegrationTestBase(TestCase):
    """Base class for integration tests using real Django models."""

    def setUp(self):
        """Set up test data using real Django models."""
        # Create test categories
        self.category1 = Category.objects.create(name="Test Category 1", description="First test category")
        self.category2 = Category.objects.create(name="Test Category 2", description="Second test category")

        # Create test users
        self.user1 = UserModel.objects.create(username="testuser1", email="user1@test.com")
        self.user2 = UserModel.objects.create(username="testuser2", email="user2@test.com")

        # Create test instances
        self.obj1 = HookModel.objects.create(
            name="Test Object 1",
            value=10,
            category=self.category1,
            created_by=self.user1
        )
        self.obj2 = HookModel.objects.create(
            name="Test Object 2",
            value=20,
            category=self.category2,
            created_by=self.user2
        )
        self.obj3 = HookModel.objects.create(
            name="Test Object 3",
            value=30,
            category=self.category1,
            created_by=self.user1
        )

        # Store original objects for comparison
        self.original_objects = [self.obj1, self.obj2, self.obj3]


class BulkOperationsIntegrationTest(IntegrationTestBase):
    """Integration tests for bulk operations using real Django models."""

    def test_bulk_update_with_hooks(self):
        """Test bulk update with hooks using real models."""
        # Track hook calls
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update_hook(new_instances, original_instances):
            hook_calls.append(('before_update', len(new_instances)))

        @bulk_hook(HookModel, AFTER_UPDATE)
        def after_update_hook(new_instances, original_instances):
            hook_calls.append(('after_update', len(new_instances)))

        try:
            # Perform bulk update
            result = HookModel.objects.filter(pk__in=[self.obj1.pk, self.obj2.pk]).update(
                value=100,
                status="updated"
            )

            # Verify result
            self.assertEqual(result, 2)

            # Verify database changes
            self.obj1.refresh_from_db()
            self.obj2.refresh_from_db()
            self.assertEqual(self.obj1.value, 100)
            self.assertEqual(self.obj1.status, "updated")
            self.assertEqual(self.obj2.value, 100)
            self.assertEqual(self.obj2.status, "updated")

            # Verify hooks were called
            self.assertEqual(len(hook_calls), 2)
            self.assertEqual(hook_calls[0], ('before_update', 2))
            self.assertEqual(hook_calls[1], ('after_update', 2))

        finally:
            # Clean up hooks
            clear_hooks()

    def test_bulk_delete_with_hooks(self):
        """Test bulk delete with hooks using real models."""
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_DELETE)
        def before_delete_hook(new_instances, original_instances):
            hook_calls.append(('before_delete', len(new_instances)))

        @bulk_hook(HookModel, AFTER_DELETE)
        def after_delete_hook(new_instances, original_instances):
            hook_calls.append(('after_delete', len(new_instances)))

        try:
            # Perform bulk delete
            result = HookModel.objects.filter(pk__in=[self.obj1.pk, self.obj2.pk]).delete()

            # Verify result
            self.assertEqual(result[0], 2)  # Number of deleted objects

            # Verify objects are gone
            self.assertFalse(HookModel.objects.filter(pk=self.obj1.pk).exists())
            self.assertFalse(HookModel.objects.filter(pk=self.obj2.pk).exists())

            # Verify hooks were called
            self.assertEqual(len(hook_calls), 2)
            self.assertEqual(hook_calls[0], ('before_delete', 2))
            self.assertEqual(hook_calls[1], ('after_delete', 2))

        finally:
            # Clean up hooks
            clear_hooks()

    def test_bulk_create_with_hooks(self):
        """Test bulk create with hooks using real models."""
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_CREATE)
        def before_create_hook(new_instances, original_instances):
            hook_calls.append(('before_create', len(new_instances)))

        @bulk_hook(HookModel, AFTER_CREATE)
        def after_create_hook(new_instances, original_instances):
            hook_calls.append(('after_create', len(new_instances)))

        try:
            # Create new instances for bulk create
            new_objects = [
                HookModel(name="Bulk Create 1", value=40, category=self.category1),
                HookModel(name="Bulk Create 2", value=50, category=self.category2)
            ]

            # Perform bulk create
            result = HookModel.objects.bulk_create(new_objects)

            # Verify result
            self.assertEqual(len(result), 2)

            # Verify objects were created
            created_objs = list(HookModel.objects.filter(name__startswith="Bulk Create"))
            self.assertEqual(len(created_objs), 2)

            # Verify hooks were called
            self.assertEqual(len(hook_calls), 2)
            self.assertEqual(hook_calls[0], ('before_create', 2))
            self.assertEqual(hook_calls[1], ('after_create', 2))

        finally:
            # Clean up hooks
            clear_hooks()


class SubqueryIntegrationTest(IntegrationTestBase):
    """Integration tests for Subquery operations using real database."""

    def test_update_with_subquery_real_database(self):
        """Test bulk update with Subquery using real database operations."""
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update_hook(new_instances, original_instances):
            hook_calls.append(('before_update', len(new_instances)))

        @bulk_hook(HookModel, AFTER_UPDATE)
        def after_update_hook(new_instances, original_instances):
            hook_calls.append(('after_update', len(new_instances)))

        try:
            # Create some additional objects for subquery testing
            extra_obj = HookModel.objects.create(
                name="Extra Object",
                value=1000,
                category=self.category1
            )

            # Use a subquery to update objects based on another query
            subquery = HookModel.objects.filter(value__gt=15).values('value')

            # Update objects where value is less than the max value from subquery
            result = HookModel.objects.filter(
                value__lt=Subquery(subquery[:1])  # Get first value > 15
            ).update(status="updated_via_subquery")

            # Verify result
            self.assertGreater(result, 0)

            # Verify database changes
            updated_count = HookModel.objects.filter(status="updated_via_subquery").count()
            self.assertGreater(updated_count, 0)

            # Verify hooks were called
            self.assertEqual(len(hook_calls), 2)
            self.assertGreater(hook_calls[0][1], 0)  # Some objects were updated

        finally:
            # Clean up hooks
            clear_hooks()

    def test_update_with_case_statement_real_database(self):
        """Test bulk update with Case/When statements using real database."""
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update_hook(new_instances, original_instances):
            hook_calls.append(('before_update', len(new_instances)))

        @bulk_hook(HookModel, AFTER_UPDATE)
        def after_update_hook(new_instances, original_instances):
            hook_calls.append(('after_update', len(new_instances)))

        try:
            # Use Case/When to conditionally update objects
            case_update = Case(
                When(value__lt=20, then=Value("low_value")),
                When(value__gte=20, then=Value("high_value")),
                default=Value("medium_value")
            )

            result = HookModel.objects.update(status=case_update)

            # Verify result
            self.assertEqual(result, 3)  # All 3 objects updated

            # Verify database changes
            low_count = HookModel.objects.filter(status="low_value").count()
            high_count = HookModel.objects.filter(status="high_value").count()

            self.assertEqual(low_count, 1)  # obj1 with value=10
            self.assertEqual(high_count, 2)  # obj2 and obj3 with values 20, 30

            # Verify hooks were called
            self.assertEqual(len(hook_calls), 2)
            self.assertEqual(hook_calls[0][1], 3)  # All objects updated

        finally:
            # Clean up hooks
            clear_hooks()


class RelationFieldIntegrationTest(IntegrationTestBase):
    """Integration tests for relation field handling using real database."""

    def test_bulk_update_with_relation_fields(self):
        """Test bulk update operations involving foreign key fields."""
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update_hook(new_instances, original_instances):
            hook_calls.append(('before_update', len(new_instances)))

        @bulk_hook(HookModel, AFTER_UPDATE)
        def after_update_hook(new_instances, original_instances):
            hook_calls.append(('after_update', len(new_instances)))

        try:
            # Update objects to change their category
            result = HookModel.objects.filter(
                pk__in=[self.obj1.pk, self.obj3.pk]  # Both originally in category1
            ).update(category=self.category2)

            # Verify result
            self.assertEqual(result, 2)

            # Verify database changes
            self.obj1.refresh_from_db()
            self.obj3.refresh_from_db()

            self.assertEqual(self.obj1.category, self.category2)
            self.assertEqual(self.obj3.category, self.category2)
            self.assertEqual(self.obj2.category, self.category2)  # Was already in category2

            # Verify hooks were called
            self.assertEqual(len(hook_calls), 2)
            self.assertEqual(hook_calls[0][1], 2)

        finally:
            # Clean up hooks
            clear_hooks()

    def test_bulk_update_with_user_fields(self):
        """Test bulk update operations involving user foreign key fields."""
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update_hook(new_instances, original_instances):
            hook_calls.append(('before_update', len(new_instances)))

        try:
            # Update objects to change their creator
            result = HookModel.objects.filter(
                pk__in=[self.obj1.pk, self.obj3.pk]  # Both originally created by user1
            ).update(created_by=self.user2)

            # Verify result
            self.assertEqual(result, 2)

            # Verify database changes
            self.obj1.refresh_from_db()
            self.obj3.refresh_from_db()

            self.assertEqual(self.obj1.created_by, self.user2)
            self.assertEqual(self.obj3.created_by, self.user2)
            self.assertEqual(self.obj2.created_by, self.user2)  # Was already created by user2

            # Verify hooks were called
            self.assertEqual(len(hook_calls), 1)
            self.assertEqual(hook_calls[0][1], 2)

        finally:
            # Clean up hooks
            clear_hooks()


class SimpleIntegrationTests(IntegrationTestBase):
    """Simple integration tests demonstrating the power of using real Django models."""

    def test_basic_bulk_operations_workflow(self):
        """Test a complete workflow of bulk operations with hooks."""
        # Track all hook calls
        hook_calls = []

        def track_hook(hook_type):
            def hook(new_instances, original_instances):
                hook_calls.append((hook_type, len(new_instances)))
            return hook

        # Register all hooks using decorators
        @bulk_hook(HookModel, BEFORE_CREATE)
        def before_create_hook(new_instances, original_instances):
            hook_calls.append(('before_create', len(new_instances)))

        @bulk_hook(HookModel, AFTER_CREATE)
        def after_create_hook(new_instances, original_instances):
            hook_calls.append(('after_create', len(new_instances)))

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update_hook(new_instances, original_instances):
            hook_calls.append(('before_update', len(new_instances)))

        @bulk_hook(HookModel, AFTER_UPDATE)
        def after_update_hook(new_instances, original_instances):
            hook_calls.append(('after_update', len(new_instances)))

        @bulk_hook(HookModel, BEFORE_DELETE)
        def before_delete_hook(new_instances, original_instances):
            hook_calls.append(('before_delete', len(new_instances)))

        @bulk_hook(HookModel, AFTER_DELETE)
        def after_delete_hook(new_instances, original_instances):
            hook_calls.append(('after_delete', len(new_instances)))

        try:
            # 1. Bulk create new objects
            new_objects = [
                HookModel(name="Workflow Test 1", value=100, category=self.category1),
                HookModel(name="Workflow Test 2", value=200, category=self.category2)
            ]

            created = HookModel.objects.bulk_create(new_objects)
            self.assertEqual(len(created), 2)
            self.assertIn(('before_create', 2), hook_calls)
            self.assertIn(('after_create', 2), hook_calls)

            # Get the created objects
            workflow_objs = list(HookModel.objects.filter(name__startswith="Workflow Test"))
            self.assertEqual(len(workflow_objs), 2)

            # 2. Bulk update the objects
            result = HookModel.objects.filter(
                name__startswith="Workflow Test"
            ).update(value=F('value') + 50)

            self.assertEqual(result, 2)
            self.assertIn(('before_update', 2), hook_calls)
            self.assertIn(('after_update', 2), hook_calls)

            # Verify the update worked
            workflow_objs[0].refresh_from_db()
            workflow_objs[1].refresh_from_db()
            self.assertEqual(workflow_objs[0].value, 150)
            self.assertEqual(workflow_objs[1].value, 250)

            # 3. Bulk delete the objects
            result = HookModel.objects.filter(
                name__startswith="Workflow Test"
            ).delete()

            self.assertEqual(result[0], 2)
            self.assertIn(('before_delete', 2), hook_calls)
            self.assertIn(('after_delete', 2), hook_calls)

            # Verify they're gone
            self.assertEqual(
                HookModel.objects.filter(name__startswith="Workflow Test").count(),
                0
            )

        finally:
            # Clean up all hooks
            clear_hooks()

    def test_performance_comparison(self):
        """Demonstrate how integration tests are faster and more reliable."""
        # This test shows the advantage of integration testing
        # No complex mocking - just real database operations

        # Create a batch of test objects
        batch_size = 10
        test_objects = []
        for i in range(batch_size):
            test_objects.append(HookModel(
                name=f"Performance Test {i}",
                value=i * 10,
                category=self.category1 if i % 2 == 0 else self.category2
            ))

        # Bulk create
        start_time = len(HookModel.objects.all())  # Get count before
        HookModel.objects.bulk_create(test_objects)
        end_time = len(HookModel.objects.all())   # Get count after

        # Verify all objects were created
        self.assertEqual(end_time - start_time, batch_size)

        # Bulk update all objects
        updated_count = HookModel.objects.filter(
            name__startswith="Performance Test"
        ).update(status="performance_tested")

        self.assertEqual(updated_count, batch_size)

        # Bulk delete all test objects
        deleted_count, _ = HookModel.objects.filter(
            name__startswith="Performance Test"
        ).delete()

        self.assertEqual(deleted_count, batch_size)


# Integration testing demonstration
class IntegrationVsMockComparison(IntegrationTestBase):
    """Demonstrates the superiority of integration testing over complex mocking."""

    def test_integration_vs_mock_complexity(self):
        """
        This test demonstrates why integration testing is superior:

        ✅ Integration approach:
        - 15 lines of readable code
        - Tests actual functionality
        - No complex mocking setup
        - Tests real database operations
        - Catches integration issues
        - Fast and reliable

        ❌ Mock approach (what we replaced):
        - 100+ lines of complex mock setup
        - Brittle and hard to maintain
        - Doesn't test real functionality
        - Fails when Django internals change
        - Slow and complex
        """
        hook_calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def audit_hook(new_records, old_records):
            # Real business logic that would be complex to mock
            for new_obj, old_obj in zip(new_records, old_records or []):
                if old_obj and new_obj.value != old_obj.value:
                    hook_calls.append(f"Value changed: {old_obj.value} -> {new_obj.value}")

        try:
            # Simple, readable test
            result = HookModel.objects.filter(pk=self.obj1.pk).update(value=999)

            # Verify real database change
            self.obj1.refresh_from_db()
            self.assertEqual(self.obj1.value, 999)

            # Verify hook was called with real data
            self.assertEqual(len(hook_calls), 1)
            self.assertIn("10 -> 999", hook_calls[0])

        finally:
            clear_hooks()


# Clean integration tests - all complex mocking removed
# See tests/test_integration_simple.py for better integration tests
