"""
Test to verify that Subquery objects in update operations work correctly with hooks.
"""

from django.db import models
from django.db.models import OuterRef, Subquery, Sum
from django.test import TestCase

from django_bulk_hooks import AFTER_UPDATE, Hook, hook
from django_bulk_hooks.models import HookModelMixin


class User(models.Model):
    """Test user model for foreign key testing."""

    username = models.CharField(max_length=100)


class TestModel(HookModelMixin):
    """Test model for Subquery hook testing."""

    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)
    computed_value = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True
    )


class RelatedModel(models.Model):
    """Related model for Subquery testing."""

    test_model = models.ForeignKey(TestModel, on_delete=models.CASCADE)
    amount = models.IntegerField()


class SubqueryHookTest(Hook):
    """Hook to test Subquery functionality."""

    def __init__(self):
        self.after_update_called = False
        self.computed_values = []
        self.foreign_key_values = []

    @hook(AFTER_UPDATE, model=TestModel)
    def test_subquery_access(self, new_records, old_records):
        self.after_update_called = True
        for record in new_records:
            # This should now contain the computed value, not the Subquery object
            self.computed_values.append(record.computed_value)
            # This should contain the User instance, not a raw ID
            self.foreign_key_values.append(record.created_by)


class SubqueryHooksTestCase(TestCase):
    """Test case for Subquery hook functionality."""

    def setUp(self):
        # Create test data
        self.user = User.objects.create(username="testuser")
        self.test_model = TestModel.objects.create(
            name="Test", value=10, created_by=self.user
        )
        self.related1 = RelatedModel.objects.create(
            test_model=self.test_model, amount=5
        )
        self.related2 = RelatedModel.objects.create(
            test_model=self.test_model, amount=15
        )

        # Create hook instance
        self.hook = SubqueryHookTest()

    def test_subquery_in_hooks(self):
        """Test that Subquery computed values are accessible in hooks."""

        # Perform update with Subquery
        TestModel.objects.filter(pk=self.test_model.pk).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(test_model=OuterRef("pk"))
                .values("test_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify that the hook was called and received computed values
        self.assertTrue(self.hook.after_update_called)
        self.assertEqual(len(self.hook.computed_values), 1)
        # The computed value should be 20 (5 + 15)
        self.assertEqual(self.hook.computed_values[0], 20)

        # Verify the database was actually updated
        self.test_model.refresh_from_db()
        self.assertEqual(self.test_model.computed_value, 20)

    def test_bulk_subquery_performance(self):
        """Test that bulk Subquery operations are efficient."""

        # Create multiple test models for bulk testing
        test_models = []
        for i in range(10):
            model = TestModel.objects.create(name=f"Test{i}", value=i)
            RelatedModel.objects.create(test_model=model, amount=i * 2)
            RelatedModel.objects.create(test_model=model, amount=i * 3)
            test_models.append(model)

        # Perform bulk update with Subquery
        pks = [model.pk for model in test_models]
        TestModel.objects.filter(pk__in=pks).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(test_model=OuterRef("pk"))
                .values("test_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify all hooks received computed values
        self.assertTrue(self.hook.after_update_called)
        self.assertEqual(len(self.hook.computed_values), 10)

        # Verify all computed values are correct
        for i, value in enumerate(self.hook.computed_values):
            expected = i * 2 + i * 3  # sum of the two related amounts
            self.assertEqual(value, expected)

    def test_subquery_object_not_passed_to_hooks(self):
        """Test that Subquery objects are not passed to hooks, only computed values."""

        # Perform update with Subquery
        TestModel.objects.filter(pk=self.test_model.pk).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(test_model=OuterRef("pk"))
                .values("test_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify that the hook received actual values, not Subquery objects
        self.assertTrue(self.hook.after_update_called)
        for value in self.hook.computed_values:
            # The value should be an integer, not a Subquery object
            self.assertIsInstance(value, int)
            self.assertNotEqual(type(value).__name__, "Subquery")

    def test_foreign_key_fields_preserved(self):
        """Test that foreign key fields are preserved correctly after Subquery updates."""

        # Perform update with Subquery
        TestModel.objects.filter(pk=self.test_model.pk).update(
            computed_value=Subquery(
                RelatedModel.objects.filter(test_model=OuterRef("pk"))
                .values("test_model")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            )
        )

        # Verify that the hook was called
        self.assertTrue(self.hook.after_update_called)

        # Verify that foreign key fields are still intact
        # The hook should have access to the created_by field as a User instance
        self.assertEqual(len(self.hook.foreign_key_values), 1)
        self.assertIsInstance(self.hook.foreign_key_values[0], User)
        self.assertEqual(self.hook.foreign_key_values[0].username, "testuser")
