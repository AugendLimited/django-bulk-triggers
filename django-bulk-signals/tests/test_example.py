"""
Example usage of django-bulk-signals.

This module demonstrates how to use django-bulk-signals in a real-world scenario,
similar to Salesforce trigger patterns.
"""

from unittest.mock import Mock, patch

from django.db import models
from django.test import TestCase
from django_bulk_signals import BulkSignalManager
from django_bulk_signals.conditions import (
    ChangesTo,
    HasChanged,
    IsEqual,
    changes_to,
    has_changed,
    is_equal,
)
from django_bulk_signals.decorators import (
    after_create,
    after_delete,
    after_update,
    before_create,
    before_delete,
    before_update,
)


class Account(models.Model):
    """Account model - similar to Salesforce Account."""

    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="active")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    objects = BulkSignalManager()

    class Meta:
        app_label = "tests"


class Opportunity(models.Model):
    """Opportunity model - similar to Salesforce Opportunity."""

    name = models.CharField(max_length=100)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stage = models.CharField(max_length=20, default="prospecting")

    objects = BulkSignalManager()

    class Meta:
        app_label = "tests"


class TestSalesforceStyleTriggers(TestCase):
    """Test Salesforce-style trigger patterns."""

    def setUp(self):
        """Set up test data."""
        self.accounts = [
            Account(name="Account 1", status="active", balance=1000),
            Account(name="Account 2", status="inactive", balance=2000),
            Account(name="Account 3", status="active", balance=3000),
        ]

        # Set PKs for testing
        for i, account in enumerate(self.accounts):
            account.pk = i + 1

    def test_before_create_trigger(self):
        """Test BEFORE_CREATE trigger pattern."""
        trigger_fired = False

        @before_create(Account)
        def validate_account_creation(sender, instances, **kwargs):
            nonlocal trigger_fired
            trigger_fired = True

            # Validate all accounts before creation
            for account in instances:
                if not account.name:
                    raise ValueError("Account name is required")
                if account.balance < 0:
                    raise ValueError("Account balance cannot be negative")

        with patch("django.db.models.QuerySet.bulk_create") as mock_bulk_create:
            mock_bulk_create.return_value = self.accounts

            Account.objects.bulk_create(self.accounts)

            self.assertTrue(trigger_fired)
            mock_bulk_create.assert_called_once()

    def test_after_create_trigger(self):
        """Test AFTER_CREATE trigger pattern."""
        trigger_fired = False
        created_accounts = []

        @after_create(Account)
        def notify_account_creation(sender, instances, **kwargs):
            nonlocal trigger_fired, created_accounts
            trigger_fired = True
            created_accounts = instances

            # Send notifications, create related records, etc.
            for account in instances:
                # Create default opportunity for new account
                Opportunity.objects.create(
                    name=f"Default Opportunity for {account.name}",
                    account=account,
                    amount=0,
                    stage="prospecting",
                )

        with (
            patch("django.db.models.QuerySet.bulk_create") as mock_bulk_create,
            patch("django.db.models.QuerySet.create") as mock_create,
        ):
            mock_bulk_create.return_value = self.accounts

            Account.objects.bulk_create(self.accounts)

            self.assertTrue(trigger_fired)
            self.assertEqual(len(created_accounts), 3)
            # Should create 3 opportunities (one for each account)
            self.assertEqual(mock_create.call_count, 3)

    def test_before_update_trigger_with_condition(self):
        """Test BEFORE_UPDATE trigger with condition."""
        trigger_fired = False
        updated_accounts = []

        @before_update(Account, condition=HasChanged("status"))
        def handle_status_change(sender, instances, originals, **kwargs):
            nonlocal trigger_fired, updated_accounts
            trigger_fired = True
            updated_accounts = instances

            # Handle status changes
            for account, original in zip(instances, originals):
                if account.status != original.status:
                    if account.status == "inactive":
                        # Set balance to 0 when account becomes inactive
                        account.balance = 0
                    elif account.status == "active" and original.status == "inactive":
                        # Restore previous balance when reactivating
                        account.balance = original.balance

        # Set up test data
        self.accounts[0].status = "inactive"  # Changed
        self.accounts[1].status = "inactive"  # Same as original
        self.accounts[2].status = "active"  # Same as original

        originals = [
            Account(pk=1, name="Account 1", status="active", balance=1000),
            Account(pk=2, name="Account 2", status="inactive", balance=2000),
            Account(pk=3, name="Account 3", status="active", balance=3000),
        ]

        with (
            patch("django.db.models.QuerySet.bulk_update") as mock_bulk_update,
            patch("django_bulk_signals.queryset.BulkSignalQuerySet.filter") as mock_filter,
            patch.object(Opportunity.objects, "filter") as mock_opp_filter,
        ):
            mock_bulk_update.return_value = 3
            # Create a mock queryset that can be iterated
            mock_queryset = Mock()
            mock_queryset.__iter__ = Mock(return_value=iter(originals))
            mock_filter.return_value = mock_queryset
            
            # Mock the opportunity filter to return empty queryset
            mock_opp_queryset = Mock()
            mock_opp_queryset.__iter__ = Mock(return_value=iter([]))
            mock_opp_filter.return_value = mock_opp_queryset

            Account.objects.bulk_update(self.accounts, ["status"])

            self.assertTrue(trigger_fired)
            # Should only process accounts where status changed
            self.assertEqual(len(updated_accounts), 1)
            # Account 1 should have balance set to 0
            self.assertEqual(updated_accounts[0].balance, 0)

    def test_after_update_trigger_with_multiple_conditions(self):
        """Test AFTER_UPDATE trigger with multiple conditions."""
        trigger_fired = False

        @after_update(Account, condition=HasChanged("balance"))
        def update_related_opportunities(sender, instances, originals, **kwargs):
            nonlocal trigger_fired
            trigger_fired = True

            # Update related opportunities when account balance changes
            for account, original in zip(instances, originals):
                if account.balance != original.balance:
                    # Update all opportunities for this account
                    opportunities = Opportunity.objects.filter(account=account)
                    for opp in opportunities:
                        # Adjust opportunity amount based on account balance
                        opp.amount = account.balance * 0.1
                        opp.save()

        # Set up test data
        self.accounts[0].balance = 1500  # Changed
        self.accounts[1].balance = 2000  # Same as original
        self.accounts[2].balance = 3500  # Changed

        originals = [
            Account(pk=1, name="Account 1", status="active", balance=1000),
            Account(pk=2, name="Account 2", status="inactive", balance=2000),
            Account(pk=3, name="Account 3", status="active", balance=3000),
        ]

        with (
            patch("django.db.models.QuerySet.bulk_update") as mock_bulk_update,
            patch("django_bulk_signals.queryset.BulkSignalQuerySet.filter") as mock_filter,
            patch.object(Opportunity.objects, "filter") as mock_opp_filter,
            patch.object(Opportunity, "save") as mock_save,
        ):
            mock_bulk_update.return_value = 3
            # Create a mock queryset that can be iterated
            mock_queryset = Mock()
            mock_queryset.__iter__ = Mock(return_value=iter(originals))
            mock_filter.return_value = mock_queryset
            
            # Mock the opportunity filter to return empty queryset
            mock_opp_queryset = Mock()
            mock_opp_queryset.__iter__ = Mock(return_value=iter([]))
            mock_opp_filter.return_value = mock_opp_queryset

            Account.objects.bulk_update(self.accounts, ["balance"])

            self.assertTrue(trigger_fired)

    def test_before_delete_trigger(self):
        """Test BEFORE_DELETE trigger pattern."""
        trigger_fired = False
        accounts_to_delete = []

        @before_delete(Account)
        def validate_account_deletion(sender, instances, **kwargs):
            nonlocal trigger_fired, accounts_to_delete
            trigger_fired = True
            accounts_to_delete = instances

            # Prevent deletion of accounts with open opportunities
            for account in instances:
                open_opportunities = Opportunity.objects.filter(
                    account=account,
                    stage__in=["prospecting", "qualification", "proposal"],
                )
                if open_opportunities.exists():
                    raise ValueError(
                        f"Cannot delete account {account.name} with open opportunities"
                    )

        with (
            patch("django.db.models.QuerySet.delete") as mock_delete,
            patch.object(Opportunity.objects, "filter") as mock_opp_filter,
        ):
            mock_delete.return_value = (3, {})
            # Mock the opportunity filter to return no open opportunities
            mock_queryset = Mock()
            mock_queryset.exists.return_value = False
            mock_opp_filter.return_value = mock_queryset

            Account.objects.bulk_delete(self.accounts)

            self.assertTrue(trigger_fired)
            self.assertEqual(len(accounts_to_delete), 3)

    def test_after_delete_trigger(self):
        """Test AFTER_DELETE trigger pattern."""
        trigger_fired = False
        deleted_accounts = []

        @after_delete(Account)
        def cleanup_after_deletion(sender, instances, **kwargs):
            nonlocal trigger_fired, deleted_accounts
            trigger_fired = True
            deleted_accounts = instances

            # Clean up related data after account deletion
            for account in instances:
                # Archive related opportunities
                opportunities = Opportunity.objects.filter(account=account)
                for opp in opportunities:
                    opp.stage = "archived"
                    opp.save()

        with (
            patch("django.db.models.QuerySet.delete") as mock_delete,
            patch("django.db.models.QuerySet.filter") as mock_filter,
            patch.object(Opportunity, "save") as mock_save,
        ):
            mock_delete.return_value = (3, {})

            Account.objects.bulk_delete(self.accounts)

            self.assertTrue(trigger_fired)
            self.assertEqual(len(deleted_accounts), 3)

    def test_complex_trigger_scenario(self):
        """Test a complex real-world trigger scenario."""
        # This simulates a complex business scenario with multiple triggers

        @before_update(Account, condition=ChangesTo("status", "inactive"))
        def handle_account_deactivation(sender, instances, originals, **kwargs):
            # When account becomes inactive, close all opportunities
            for account in instances:
                opportunities = Opportunity.objects.filter(account=account)
                for opp in opportunities:
                    opp.stage = "closed_lost"
                    opp.save()

        @after_update(Account, condition=HasChanged("balance"))
        def update_account_summary(sender, instances, originals, **kwargs):
            # Update account summary when balance changes
            for account, original in zip(instances, originals):
                if account.balance != original.balance:
                    # Update summary fields, send notifications, etc.
                    pass

        @before_delete(Account)
        def validate_deletion(sender, instances, **kwargs):
            # Validate that accounts can be deleted
            for account in instances:
                if account.balance > 0:
                    raise ValueError("Cannot delete account with positive balance")

        # Test the complex scenario
        self.accounts[0].status = "inactive"  # Changes to inactive
        self.accounts[1].balance = 2500  # Balance changes

        originals = [
            Account(pk=1, name="Account 1", status="active", balance=1000),
            Account(pk=2, name="Account 2", status="inactive", balance=2000),
            Account(pk=3, name="Account 3", status="active", balance=3000),
        ]

        with (
            patch("django.db.models.QuerySet.bulk_update") as mock_bulk_update,
            patch("django_bulk_signals.queryset.BulkSignalQuerySet.filter") as mock_filter,
            patch.object(Opportunity.objects, "filter") as mock_opp_filter,
            patch.object(Opportunity, "save") as mock_save,
        ):
            mock_bulk_update.return_value = 3
            # Create a mock queryset that can be iterated
            mock_queryset = Mock()
            mock_queryset.__iter__ = Mock(return_value=iter(originals))
            mock_filter.return_value = mock_queryset
            
            # Mock the opportunity filter to return empty queryset
            mock_opp_queryset = Mock()
            mock_opp_queryset.__iter__ = Mock(return_value=iter([]))
            mock_opp_filter.return_value = mock_opp_queryset

            Account.objects.bulk_update(self.accounts, ["status", "balance"])

            # All triggers should fire appropriately
            mock_bulk_update.assert_called_once()
