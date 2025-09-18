"""
Consolidated tests for bulk operations functionality.

This module consolidates bulk operation tests to reduce complexity
and improve maintainability while preserving all test coverage.
"""

from unittest.mock import MagicMock, Mock, patch
import pytest
from django.db import transaction
from django.db.models import Case, Subquery, Value, When
from django.test import TestCase, TransactionTestCase

from django_bulk_triggers import TriggerClass
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
from django_bulk_triggers.conditions import HasChanged, IsEqual
from django_bulk_triggers.priority import Priority
from django_bulk_triggers.queryset import TriggerQuerySetMixin
from django_bulk_triggers.context import set_bulk_update_value_map
from tests.models import (
    Category,
    ComplexModel,
    RelatedModel,
    SimpleModel,
    TriggerModel,
    UserModel,
)
from tests.utils import TriggerTracker, assert_trigger_called, create_test_instances


class TestBulkCreate(TransactionTestCase):
    """Test bulk_create functionality."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_bulk_create_basic(self):
        """Test basic bulk_create functionality."""
        tracker = TriggerTracker()

        class BulkCreateTestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                tracker.track("before_create", new_records)

            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_after_create(self, new_records, old_records=None, **kwargs):
                tracker.track("after_create", new_records)

        # Create trigger instance
        bulk_create_trigger = BulkCreateTestTrigger()

        # Create instances
        instances = [
            TriggerModel(name=f"Bulk Test {i}")
            for i in range(5)
        ]

        # Execute bulk_create
        with transaction.atomic():
            result = TriggerModel.objects.bulk_create(instances)

        # Verify instances were created
        self.assertEqual(len(result), 5)
        self.assertEqual(TriggerModel.objects.count(), 5)

        # Verify triggers were called
        assert_trigger_called(tracker, "before_create", instances)
        assert_trigger_called(tracker, "after_create", result)

    def test_bulk_create_with_validation(self):
        """Test bulk_create with validation triggers."""
        tracker = TriggerTracker()

        class ValidationTestTrigger(TriggerClass):
            @trigger(VALIDATE_CREATE, model=TriggerModel)
            def on_validate_create(self, new_records, old_records=None, **kwargs):
                tracker.track("validate_create", new_records)

        # Create trigger instance
        validation_trigger = ValidationTestTrigger()

        # Create instances
        instances = [
            TriggerModel(name=f"Validation Test {i}")
            for i in range(3)
        ]

        # Execute bulk_create
        with transaction.atomic():
            result = TriggerModel.objects.bulk_create(instances)

        # Verify triggers were called
        assert_trigger_called(tracker, "validate_create", instances)

    def test_bulk_create_bypass_triggers(self):
        """Test bulk_create with bypass_triggers=True."""
        tracker = TriggerTracker()

        class BypassTestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel)
            def on_before_create(self, new_records, old_records=None, **kwargs):
                tracker.track("before_create", new_records)

        # Create trigger instance
        bypass_trigger = BypassTestTrigger()

        # Create instances
        instances = [
            TriggerModel(name=f"Bypass Test {i}")
            for i in range(3)
        ]

        # Execute bulk_create with bypass_triggers=True
        with transaction.atomic():
            result = TriggerModel.objects.bulk_create(instances, bypass_triggers=True)

        # Verify instances were created
        self.assertEqual(len(result), 3)

        # Verify triggers were NOT called
        self.assertEqual(len(tracker.calls), 0)

    def test_bulk_create_with_conditions(self):
        """Test bulk_create with trigger conditions."""
        tracker = TriggerTracker()

        class ConditionalTestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel, condition=IsEqual("name", "Special"))
            def on_special_create(self, new_records, old_records=None, **kwargs):
                tracker.track("special_create", new_records)

        # Create trigger instance
        conditional_trigger = ConditionalTestTrigger()

        # Create instances with different names
        instances = [
            TriggerModel(name="Special"),
            TriggerModel(name="Normal"),
            TriggerModel(name="Special"),
        ]

        # Execute bulk_create
        with transaction.atomic():
            result = TriggerModel.objects.bulk_create(instances)

        # Verify instances were created
        self.assertEqual(len(result), 3)

        # Verify only special instances triggered the condition
        special_instances = [inst for inst in instances if inst.name == "Special"]
        assert_trigger_called(tracker, "special_create", special_instances)


class TestBulkUpdate(TransactionTestCase):
    """Test bulk_update functionality."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_bulk_update_basic(self):
        """Test basic bulk_update functionality."""
        tracker = TriggerTracker()

        class BulkUpdateTestTrigger(TriggerClass):
            @trigger(BEFORE_UPDATE, model=TriggerModel)
            def on_before_update(self, new_records, old_records=None, **kwargs):
                tracker.track("before_update", new_records)

            @trigger(AFTER_UPDATE, model=TriggerModel)
            def on_after_update(self, new_records, old_records=None, **kwargs):
                tracker.track("after_update", new_records)

        # Create trigger instance
        bulk_update_trigger = BulkUpdateTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Update Test {i}")
            for i in range(5)
        ]

        # Update all instances
        for instance in instances:
            instance.name = f"Updated {instance.name}"

        # Execute bulk_update
        with transaction.atomic():
            result = TriggerModel.objects.bulk_update(instances, ['name'])

        # Verify update was successful
        self.assertEqual(result, 5)

        # Verify triggers were called
        assert_trigger_called(tracker, "before_update", instances)
        assert_trigger_called(tracker, "after_update", instances)

    def test_bulk_update_with_validation(self):
        """Test bulk_update with validation triggers."""
        tracker = TriggerTracker()

        class ValidationTestTrigger(TriggerClass):
            @trigger(VALIDATE_UPDATE, model=TriggerModel)
            def on_validate_update(self, new_records, old_records=None, **kwargs):
                tracker.track("validate_update", new_records)

        # Create trigger instance
        validation_trigger = ValidationTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Validation Update {i}")
            for i in range(3)
        ]

        # Update all instances
        for instance in instances:
            instance.name = f"Validated {instance.name}"

        # Execute bulk_update
        with transaction.atomic():
            result = TriggerModel.objects.bulk_update(instances, ['name'])

        # Verify triggers were called
        assert_trigger_called(tracker, "validate_update", instances)

    def test_bulk_update_bypass_triggers(self):
        """Test bulk_update with bypass_triggers=True."""
        tracker = TriggerTracker()

        class BypassTestTrigger(TriggerClass):
            @trigger(BEFORE_UPDATE, model=TriggerModel)
            def on_before_update(self, new_records, old_records=None, **kwargs):
                tracker.track("before_update", new_records)

        # Create trigger instance
        bypass_trigger = BypassTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Bypass Update {i}")
            for i in range(3)
        ]

        # Update all instances
        for instance in instances:
            instance.name = f"Bypassed {instance.name}"

        # Execute bulk_update with bypass_triggers=True
        with transaction.atomic():
            result = TriggerModel.objects.bulk_update(instances, ['name'], bypass_triggers=True)

        # Verify update was successful
        self.assertEqual(result, 3)

        # Verify triggers were NOT called
        self.assertEqual(len(tracker.calls), 0)

    def test_bulk_update_with_conditions(self):
        """Test bulk_update with trigger conditions."""
        tracker = TriggerTracker()

        class ConditionalTestTrigger(TriggerClass):
            @trigger(BEFORE_UPDATE, model=TriggerModel, condition=HasChanged("name"))
            def on_name_changed(self, new_records, old_records=None, **kwargs):
                tracker.track("name_changed", new_records)

        # Create trigger instance
        conditional_trigger = ConditionalTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Conditional Update {i}")
            for i in range(3)
        ]

        # Update only some instances
        instances[0].name = "Changed Name"
        instances[1].name = "Changed Name"
        # Leave instances[2] unchanged

        # Execute bulk_update
        with transaction.atomic():
            result = TriggerModel.objects.bulk_update(instances, ['name'])

        # Verify update was successful
        self.assertEqual(result, 3)

        # Verify only changed instances triggered the condition
        changed_instances = instances[:2]
        assert_trigger_called(tracker, "name_changed", changed_instances)


class TestBulkDelete(TransactionTestCase):
    """Test bulk_delete functionality."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_bulk_delete_basic(self):
        """Test basic bulk_delete functionality."""
        tracker = TriggerTracker()

        class BulkDeleteTestTrigger(TriggerClass):
            @trigger(BEFORE_DELETE, model=TriggerModel)
            def on_before_delete(self, new_records, old_records=None, **kwargs):
                tracker.track("before_delete", new_records)

            @trigger(AFTER_DELETE, model=TriggerModel)
            def on_after_delete(self, new_records, old_records=None, **kwargs):
                tracker.track("after_delete", new_records)

        # Create trigger instance
        bulk_delete_trigger = BulkDeleteTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Delete Test {i}")
            for i in range(5)
        ]

        # Execute bulk_delete
        with transaction.atomic():
            result = TriggerModel.objects.bulk_delete(instances)

        # Verify delete was successful
        self.assertEqual(result, 5)
        self.assertEqual(TriggerModel.objects.count(), 0)

        # Verify triggers were called
        assert_trigger_called(tracker, "before_delete", instances)
        assert_trigger_called(tracker, "after_delete", instances)

    def test_bulk_delete_with_validation(self):
        """Test bulk_delete with validation triggers."""
        tracker = TriggerTracker()

        class ValidationTestTrigger(TriggerClass):
            @trigger(VALIDATE_DELETE, model=TriggerModel)
            def on_validate_delete(self, new_records, old_records=None, **kwargs):
                tracker.track("validate_delete", new_records)

        # Create trigger instance
        validation_trigger = ValidationTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Validation Delete {i}")
            for i in range(3)
        ]

        # Execute bulk_delete
        with transaction.atomic():
            result = TriggerModel.objects.bulk_delete(instances)

        # Verify triggers were called
        assert_trigger_called(tracker, "validate_delete", instances)

    def test_bulk_delete_bypass_triggers(self):
        """Test bulk_delete with bypass_triggers=True."""
        tracker = TriggerTracker()

        class BypassTestTrigger(TriggerClass):
            @trigger(BEFORE_DELETE, model=TriggerModel)
            def on_before_delete(self, new_records, old_records=None, **kwargs):
                tracker.track("before_delete", new_records)

        # Create trigger instance
        bypass_trigger = BypassTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Bypass Delete {i}")
            for i in range(3)
        ]

        # Execute bulk_delete with bypass_triggers=True
        with transaction.atomic():
            result = TriggerModel.objects.bulk_delete(instances, bypass_triggers=True)

        # Verify delete was successful
        self.assertEqual(result, 3)

        # Verify triggers were NOT called
        self.assertEqual(len(tracker.calls), 0)


class TestBulkOperationsEdgeCases(TransactionTestCase):
    """Test edge cases for bulk operations."""

    def setUp(self):
        # Clear the registry to prevent interference between tests
        from django_bulk_triggers.registry import clear_triggers
        clear_triggers()

    def test_empty_bulk_create(self):
        """Test bulk_create with empty list."""
        result = TriggerModel.objects.bulk_create([])
        self.assertEqual(result, [])

    def test_empty_bulk_update(self):
        """Test bulk_update with empty list."""
        result = TriggerModel.objects.bulk_update([], ['name'])
        self.assertEqual(result, [])

    def test_empty_bulk_delete(self):
        """Test bulk_delete with empty list."""
        result = TriggerModel.objects.bulk_delete([])
        self.assertEqual(result, 0)

    def test_bulk_create_with_batch_size(self):
        """Test bulk_create with batch_size parameter."""
        tracker = TriggerTracker()

        class BatchTestTrigger(TriggerClass):
            @trigger(AFTER_CREATE, model=TriggerModel)
            def on_after_create(self, new_records, old_records=None, **kwargs):
                tracker.track("after_create", new_records)

        # Create trigger instance
        batch_trigger = BatchTestTrigger()

        # Create instances
        instances = [
            TriggerModel(name=f"Batch Test {i}")
            for i in range(10)
        ]

        # Execute bulk_create with batch_size
        with transaction.atomic():
            result = TriggerModel.objects.bulk_create(instances, batch_size=3)

        # Verify instances were created
        self.assertEqual(len(result), 10)

        # Verify triggers were called
        assert_trigger_called(tracker, "after_create", result)

    def test_bulk_update_auto_detect_fields(self):
        """Test bulk_update with auto-detected fields."""
        tracker = TriggerTracker()

        class AutoDetectTestTrigger(TriggerClass):
            @trigger(BEFORE_UPDATE, model=TriggerModel)
            def on_before_update(self, new_records, old_records=None, **kwargs):
                tracker.track("before_update", new_records)

        # Create trigger instance
        auto_detect_trigger = AutoDetectTestTrigger()

        # Create instances first
        instances = [
            TriggerModel.objects.create(name=f"Auto Detect {i}")
            for i in range(3)
        ]

        # Update instances (fields will be auto-detected)
        for instance in instances:
            instance.name = f"Auto Detected {instance.name}"

        # Execute bulk_update without specifying fields
        with transaction.atomic():
            result = TriggerModel.objects.bulk_update(instances)

        # Verify update was successful
        self.assertEqual(result, 3)

        # Verify triggers were called
        assert_trigger_called(tracker, "before_update", instances)
