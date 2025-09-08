"""
Simple Integration Tests for django-bulk-hooks

This file demonstrates the power of integration testing using real Django models
instead of complex mocking. These tests are:

✅ Simple and readable
✅ Test real functionality
✅ Fast and reliable
✅ Easy to maintain
✅ Catch integration issues

Compare this to the complex mocking approach in test_queryset_extended.py!
"""

from django.test import TestCase
from django.db.models import F, Subquery, Case, When, Value
from django_bulk_hooks.constants import (
    BEFORE_CREATE, AFTER_CREATE,
    BEFORE_UPDATE, AFTER_UPDATE,
    BEFORE_DELETE, AFTER_DELETE
)
from django_bulk_hooks.decorators import bulk_hook
from django_bulk_hooks.registry import clear_hooks
from tests.models import HookModel, Category, UserModel


class SimpleIntegrationTestBase(TestCase):
    """Base class for simple integration tests."""

    def setUp(self):
        """Create test data using real Django models."""
        self.category1 = Category.objects.create(name="Electronics", description="Electronic devices")
        self.category2 = Category.objects.create(name="Books", description="Reading materials")

        self.user1 = UserModel.objects.create(username="alice", email="alice@test.com")
        self.user2 = UserModel.objects.create(username="bob", email="bob@test.com")

        # Create test objects
        self.product1 = HookModel.objects.create(
            name="Laptop", value=1000, category=self.category1, created_by=self.user1
        )
        self.product2 = HookModel.objects.create(
            name="Book", value=20, category=self.category2, created_by=self.user2
        )

    def tearDown(self):
        """Clean up hooks after each test."""
        clear_hooks()


class BulkOperationsTest(SimpleIntegrationTestBase):
    """Test basic bulk operations with hooks."""

    def test_bulk_update_with_hooks(self):
        """Test that bulk update triggers hooks correctly."""
        calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update(new_records, old_records):
            calls.append(('before', len(new_records)))
            # Modify values in hook
            for obj in new_records:
                obj.name = f"Updated {obj.name}"

        @bulk_hook(HookModel, AFTER_UPDATE)
        def after_update(new_records, old_records):
            calls.append(('after', len(new_records)))

        # Perform bulk update
        result = HookModel.objects.filter(pk=self.product1.pk).update(value=1500)

        # Verify result
        self.assertEqual(result, 1)

        # Verify hooks were called
        self.assertEqual(calls, [('before', 1), ('after', 1)])

        # Verify database changes
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.value, 1500)

    def test_bulk_create_with_hooks(self):
        """Test that bulk create triggers hooks correctly."""
        calls = []

        @bulk_hook(HookModel, BEFORE_CREATE)
        def before_create(new_records, old_records):
            calls.append(('before_create', len(new_records)))

        @bulk_hook(HookModel, AFTER_CREATE)
        def after_create(new_records, old_records):
            calls.append(('after_create', len(new_records)))

        # Create new objects
        new_products = [
            HookModel(name="Tablet", value=500, category=self.category1),
            HookModel(name="Headphones", value=100, category=self.category1)
        ]

        result = HookModel.objects.bulk_create(new_products)

        # Verify result
        self.assertEqual(len(result), 2)

        # Verify hooks were called
        self.assertEqual(calls, [('before_create', 2), ('after_create', 2)])

    def test_bulk_delete_with_hooks(self):
        """Test that bulk delete triggers hooks correctly."""
        calls = []

        @bulk_hook(HookModel, BEFORE_DELETE)
        def before_delete(new_records, old_records):
            calls.append(('before_delete', len(new_records)))

        @bulk_hook(HookModel, AFTER_DELETE)
        def after_delete(new_records, old_records):
            calls.append(('after_delete', len(new_records)))

        # Delete objects
        result = HookModel.objects.filter(pk=self.product1.pk).delete()

        # Verify result
        self.assertEqual(result[0], 1)  # Number of deleted objects

        # Verify hooks were called
        self.assertEqual(calls, [('before_delete', 1), ('after_delete', 1)])

        # Verify object is gone
        self.assertFalse(HookModel.objects.filter(pk=self.product1.pk).exists())


class AdvancedQueriesTest(SimpleIntegrationTestBase):
    """Test advanced query operations with hooks."""

    def test_subquery_with_hooks(self):
        """Test bulk update with Subquery expressions."""
        calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update(new_records, old_records):
            calls.append(('before_update', len(new_records)))

        # Create additional products for subquery testing
        expensive_product = HookModel.objects.create(
            name="Expensive Item", value=2000, category=self.category1
        )

        # Use subquery to update products cheaper than the most expensive
        expensive_values = HookModel.objects.filter(value__gt=100).values('value')
        result = HookModel.objects.filter(
            value__lt=Subquery(expensive_values[:1])
        ).update(status="discounted")

        # Verify hooks were called
        self.assertEqual(len(calls), 1)

        # Verify some products were updated
        self.assertGreater(result, 0)

        # Clean up
        expensive_product.delete()

    def test_case_when_with_hooks(self):
        """Test bulk update with Case/When expressions."""
        calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update(new_records, old_records):
            calls.append(('before_update', len(new_records)))

        # Use Case/When to categorize products by updating status
        case_expression = Case(
            When(value__lt=100, then=Value("budget")),
            When(value__gte=100, then=Value("premium")),
            default=Value("standard")
        )

        result = HookModel.objects.update(status=case_expression)

        # Verify hooks were called for all objects
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 2)  # Both products updated

        # Verify result
        self.assertEqual(result, 2)


class RelationFieldsTest(SimpleIntegrationTestBase):
    """Test operations involving foreign key relationships."""

    def test_foreign_key_updates(self):
        """Test bulk updates involving foreign key fields."""
        calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update(new_records, old_records):
            calls.append(('before_update', len(new_records)))

        # Update products to change category
        result = HookModel.objects.filter(
            pk=self.product1.pk
        ).update(category=self.category2)

        # Verify hooks were called
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 1)

        # Verify foreign key change
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.category, self.category2)

    def test_user_field_updates(self):
        """Test bulk updates involving user foreign key fields."""
        calls = []

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update(new_records, old_records):
            calls.append(('before_update', len(new_records)))

        # Update products to change creator
        result = HookModel.objects.filter(
            pk=self.product1.pk
        ).update(created_by=self.user2)

        # Verify hooks were called
        self.assertEqual(len(calls), 1)

        # Verify user change
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.created_by, self.user2)


class WorkflowIntegrationTest(SimpleIntegrationTestBase):
    """Test complete workflows combining multiple operations."""

    def test_complete_crud_workflow(self):
        """Test a complete Create-Read-Update-Delete workflow."""
        workflow_calls = []

        # Register hooks for all operations
        @bulk_hook(HookModel, BEFORE_CREATE)
        def before_create(new_records, old_records):
            workflow_calls.append('before_create')

        @bulk_hook(HookModel, AFTER_CREATE)
        def after_create(new_records, old_records):
            workflow_calls.append('after_create')

        @bulk_hook(HookModel, BEFORE_UPDATE)
        def before_update(new_records, old_records):
            workflow_calls.append('before_update')

        @bulk_hook(HookModel, AFTER_UPDATE)
        def after_update(new_records, old_records):
            workflow_calls.append('after_update')

        @bulk_hook(HookModel, BEFORE_DELETE)
        def before_delete(new_records, old_records):
            workflow_calls.append('before_delete')

        @bulk_hook(HookModel, AFTER_DELETE)
        def after_delete(new_records, old_records):
            workflow_calls.append('after_delete')

        # 1. Create new products
        new_products = [
            HookModel(name="Workflow Product 1", value=300, category=self.category1),
            HookModel(name="Workflow Product 2", value=400, category=self.category2)
        ]

        created = HookModel.objects.bulk_create(new_products)
        self.assertEqual(len(created), 2)
        self.assertIn('before_create', workflow_calls)
        self.assertIn('after_create', workflow_calls)

        # Get created objects
        workflow_products = list(HookModel.objects.filter(name__startswith="Workflow"))
        self.assertEqual(len(workflow_products), 2)

        # 2. Update products
        result = HookModel.objects.filter(
            name__startswith="Workflow"
        ).update(value=F('value') + 100)

        self.assertEqual(result, 2)
        self.assertIn('before_update', workflow_calls)
        self.assertIn('after_update', workflow_calls)

        # 3. Delete products
        result = HookModel.objects.filter(
            name__startswith="Workflow"
        ).delete()

        self.assertEqual(result[0], 2)
        self.assertIn('before_delete', workflow_calls)
        self.assertIn('after_delete', workflow_calls)

        # Verify complete workflow
        expected_calls = [
            'before_create', 'after_create',
            'before_update', 'after_update',
            'before_delete', 'after_delete'
        ]

        for call in expected_calls:
            self.assertIn(call, workflow_calls)

        # Verify objects are gone
        self.assertEqual(
            HookModel.objects.filter(name__startswith="Workflow").count(),
            0
        )
