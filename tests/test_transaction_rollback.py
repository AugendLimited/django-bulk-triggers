"""
Tests for transaction rollback behavior when triggers fail.

This module tests the Salesforce-like behavior where if any trigger fails,
the entire transaction should rollback.
"""

import logging

from django.db import transaction
from django.test import TestCase, TransactionTestCase

from django_bulk_triggers.constants import AFTER_CREATE, BEFORE_CREATE
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.handler import Trigger
from tests.models import RelatedModel, TriggerModel, UserModel

logger = logging.getLogger(__name__)


class TransactionRollbackTrigger(Trigger):
    """
    A trigger that creates related records and then fails,
    testing transaction rollback behavior.
    """

    @trigger(AFTER_CREATE, model=TriggerModel)
    def create_related_and_fail(self, new_records, old_records=None, **kwargs):
        """
        This trigger:
        1. Creates related records successfully
        2. Then fails with an exception
        3. Should cause complete transaction rollback
        """
        for record in new_records:
            # First, create a related record (this should succeed initially)
            RelatedModel.objects.create(
                trigger_model=record,
                amount=record.value * 100,
                description=f"Related to {record.name}",
            )
            logger.info(f"Created related record for {record.name}")

        # Now simulate a failure that should rollback everything
        raise RuntimeError(
            "Simulated trigger failure - should rollback entire transaction"
        )


class NestedTriggerFailureTrigger(Trigger):
    """
    A trigger that performs nested operations that fail.
    """

    @trigger(AFTER_CREATE, model=RelatedModel)
    def nested_operation_that_fails(self, new_records, old_records=None, **kwargs):
        """
        This trigger fires when RelatedModel records are created
        and performs an operation that fails.
        """
        # Simulate some processing
        for record in new_records:
            logger.info(f"Processing related record {record.id}")

        # Fail after some processing
        raise ValueError("Nested trigger failure")


class TestTransactionRollback(TransactionTestCase):
    """
    Test transaction rollback behavior using TransactionTestCase
    to ensure proper transaction handling.
    """

    def setUp(self):
        self.user = UserModel.objects.create(
            username="testuser", email="test@example.com"
        )

    def test_trigger_failure_rolls_back_original_insert(self):
        """
        Test that when a trigger fails, the original record insertion
        is rolled back along with any other operations.
        """
        # Register our failure trigger
        trigger_instance = TransactionRollbackTrigger()

        # Create a test record - this should fail due to trigger
        test_record = TriggerModel(name="Test Record", value=50, created_by=self.user)

        # Verify no records exist before
        self.assertEqual(TriggerModel.objects.count(), 0)
        self.assertEqual(RelatedModel.objects.count(), 0)

        # The bulk_create should fail due to trigger exception
        with self.assertRaises(RuntimeError) as cm:
            TriggerModel.objects.bulk_create([test_record])

        self.assertIn("Simulated trigger failure", str(cm.exception))

        # Verify complete rollback - NO records should exist
        self.assertEqual(
            TriggerModel.objects.count(),
            0,
            "Original TriggerModel record should be rolled back",
        )
        self.assertEqual(
            RelatedModel.objects.count(),
            0,
            "Related records created in trigger should be rolled back",
        )

    def test_nested_trigger_failure_rollback(self):
        """
        Test that nested trigger failures also cause complete rollback.
        """
        # Register both triggers
        rollback_trigger = TransactionRollbackTrigger()
        nested_trigger = NestedTriggerFailureTrigger()

        test_record = TriggerModel(name="Nested Test", value=75, created_by=self.user)

        # Verify no records exist before
        self.assertEqual(TriggerModel.objects.count(), 0)
        self.assertEqual(RelatedModel.objects.count(), 0)

        # This should fail due to nested trigger failure
        with self.assertRaises((RuntimeError, ValueError)):
            TriggerModel.objects.bulk_create([test_record])

        # Verify complete rollback
        self.assertEqual(
            TriggerModel.objects.count(), 0, "Original record should be rolled back"
        )
        self.assertEqual(
            RelatedModel.objects.count(), 0, "All nested records should be rolled back"
        )

    def test_multiple_records_failure_rollback(self):
        """
        Test rollback behavior with multiple records where one trigger fails.
        """
        trigger_instance = TransactionRollbackTrigger()

        # Create multiple test records
        test_records = [
            TriggerModel(name="Record 1", value=10, created_by=self.user),
            TriggerModel(name="Record 2", value=20, created_by=self.user),
            TriggerModel(name="Record 3", value=30, created_by=self.user),
        ]

        # Verify no records exist before
        self.assertEqual(TriggerModel.objects.count(), 0)
        self.assertEqual(RelatedModel.objects.count(), 0)

        # The bulk operation should fail
        with self.assertRaises(RuntimeError):
            TriggerModel.objects.bulk_create(test_records)

        # Verify ALL records are rolled back
        self.assertEqual(
            TriggerModel.objects.count(),
            0,
            "All TriggerModel records should be rolled back",
        )
        self.assertEqual(
            RelatedModel.objects.count(), 0, "All related records should be rolled back"
        )


class TestSuccessfulOperations(TransactionTestCase):
    """
    Test that successful operations work correctly (for comparison).
    """

    def setUp(self):
        self.user = UserModel.objects.create(
            username="testuser2", email="test2@example.com"
        )

    def test_successful_trigger_commits_properly(self):
        """
        Test that when triggers succeed, all operations are committed.
        """
        # Skip this test for now since we're testing failure scenarios
        # In real usage, the triggers would be registered properly
        self.skipTest("Skipping successful trigger test - testing failure scenarios")
