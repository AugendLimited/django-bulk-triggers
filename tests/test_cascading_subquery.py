"""
Test cascading triggers with Subquery updates.

This tests the scenario where:
1. A subquery update on one model triggers changes
2. Those changes should cascade to trigger updates on related models

This is the pattern:
  LoanTransaction -> DailyLoanSummary (via subquery) -> LoanAccount
"""

from django.db import models
from django.db.models import OuterRef, Subquery, Sum, Count
from django.test import TestCase

from django_bulk_triggers import TriggerClass
from django_bulk_triggers.conditions import HasChanged
from django_bulk_triggers.constants import AFTER_UPDATE
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.manager import BulkTriggerManager
from django_bulk_triggers.registry import clear_triggers


# Test models simulating the user's scenario
class LoanAccount(models.Model):
    """Top-level loan account aggregate."""
    name = models.CharField(max_length=100)
    total_disbursement = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_disbursements_count = models.IntegerField(default=0)

    objects = BulkTriggerManager()

    class Meta:
        app_label = "tests"


class DailyLoanSummary(models.Model):
    """Daily summary for a loan account."""
    loan_account = models.ForeignKey(LoanAccount, on_delete=models.CASCADE)
    date = models.DateField()
    disbursement = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    disbursements = models.IntegerField(default=0)

    objects = BulkTriggerManager()

    class Meta:
        app_label = "tests"


class LoanTransaction(models.Model):
    """Individual loan transaction."""
    daily_loan_summary = models.ForeignKey(DailyLoanSummary, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=50)
    status = models.CharField(max_length=50)

    objects = BulkTriggerManager()

    class Meta:
        app_label = "tests"


class CascadingTriggerHandler(TriggerClass):
    """Handler for cascading triggers."""

    # Class variables to track calls
    summary_update_called = False
    account_update_called = False
    summary_disbursements_changed = []
    account_totals_changed = []

    def __init__(self):
        pass

    @classmethod
    def reset(cls):
        """Reset tracking variables."""
        cls.summary_update_called = False
        cls.account_update_called = False
        cls.summary_disbursements_changed.clear()
        cls.account_totals_changed.clear()

    @trigger(
        AFTER_UPDATE,
        model=DailyLoanSummary,
        condition=HasChanged("disbursement", has_changed=True) | HasChanged("disbursements", has_changed=True),
    )
    def aggregate_to_loan_account(self, old_records, new_records, **kwargs):
        """When DailyLoanSummary changes, aggregate to LoanAccount."""
        CascadingTriggerHandler.summary_update_called = True
        
        # Track which summaries changed
        for new_rec, old_rec in zip(new_records, old_records):
            CascadingTriggerHandler.summary_disbursements_changed.append({
                'id': new_rec.id,
                'old_disbursement': old_rec.disbursement if old_rec else None,
                'new_disbursement': new_rec.disbursement,
                'old_count': old_rec.disbursements if old_rec else None,
                'new_count': new_rec.disbursements,
            })

        # Get unique loan account IDs
        loan_account_ids = list(set(record.loan_account_id for record in new_records))

        # Aggregate to loan accounts
        for loan_account_id in loan_account_ids:
            summaries = DailyLoanSummary.objects.filter(loan_account_id=loan_account_id)
            total_disbursement = sum(s.disbursement for s in summaries)
            total_count = sum(s.disbursements for s in summaries)

            LoanAccount.objects.filter(pk=loan_account_id).update(
                total_disbursement=total_disbursement,
                total_disbursements_count=total_count,
            )

    @trigger(
        AFTER_UPDATE,
        model=LoanAccount,
        condition=HasChanged("total_disbursement", has_changed=True) | HasChanged("total_disbursements_count", has_changed=True),
    )
    def track_account_changes(self, old_records, new_records, **kwargs):
        """Track when LoanAccount totals change."""
        CascadingTriggerHandler.account_update_called = True
        
        for new_rec, old_rec in zip(new_records, old_records):
            CascadingTriggerHandler.account_totals_changed.append({
                'id': new_rec.id,
                'old_total': old_rec.total_disbursement if old_rec else None,
                'new_total': new_rec.total_disbursement,
                'old_count': old_rec.total_disbursements_count if old_rec else None,
                'new_count': new_rec.total_disbursements_count,
            })


class CascadingSubqueryTestCase(TestCase):
    """Test cascading triggers with subquery updates."""

    def setUp(self):
        """Set up test data."""
        # Clear registry
        clear_triggers()

        # Create test data
        self.loan_account = LoanAccount.objects.create(
            name="Test Loan",
            total_disbursement=0,
            total_disbursements_count=0,
        )

        self.daily_summary = DailyLoanSummary.objects.create(
            loan_account=self.loan_account,
            date="2024-01-01",
            disbursement=0,
            disbursements=0,
        )

        self.transaction1 = LoanTransaction.objects.create(
            daily_loan_summary=self.daily_summary,
            amount=100.00,
            transaction_type="DISBURSEMENT",
            status="COMPLETE",
        )

        self.transaction2 = LoanTransaction.objects.create(
            daily_loan_summary=self.daily_summary,
            amount=200.00,
            transaction_type="DISBURSEMENT",
            status="COMPLETE",
        )

        # Register triggers
        from django_bulk_triggers.registry import register_trigger

        self.handler = CascadingTriggerHandler()
        
        # Register the summary -> account trigger
        register_trigger(
            DailyLoanSummary,
            "after_update",
            CascadingTriggerHandler,
            "aggregate_to_loan_account",
            condition=HasChanged("disbursement", has_changed=True) | HasChanged("disbursements", has_changed=True),
            priority=100,
        )

        # Register the account change tracking trigger
        register_trigger(
            LoanAccount,
            "after_update",
            CascadingTriggerHandler,
            "track_account_changes",
            condition=HasChanged("total_disbursement", has_changed=True) | HasChanged("total_disbursements_count", has_changed=True),
            priority=200,
        )

        # Reset tracking
        CascadingTriggerHandler.reset()

    def tearDown(self):
        """Clean up."""
        clear_triggers()

    def test_cascading_subquery_triggers(self):
        """
        Test that subquery updates cascade through triggers.
        
        Steps:
        1. Update DailyLoanSummary using Subquery (aggregates from transactions)
        2. This should trigger aggregate_to_loan_account
        3. Which updates LoanAccount
        4. Which should trigger track_account_changes
        """
        # Update daily summary with subquery aggregation
        result = DailyLoanSummary.objects.filter(pk=self.daily_summary.pk).update(
            disbursement=Subquery(
                LoanTransaction.objects.filter(daily_loan_summary_id=OuterRef("pk"))
                .filter(transaction_type="DISBURSEMENT", status="COMPLETE")
                .values("daily_loan_summary_id")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            ),
            disbursements=Subquery(
                LoanTransaction.objects.filter(daily_loan_summary_id=OuterRef("pk"))
                .filter(transaction_type="DISBURSEMENT", status="COMPLETE")
                .values("daily_loan_summary_id")
                .annotate(count=Count("id"))
                .values("count")[:1]
            ),
        )

        # Verify update happened
        self.assertEqual(result, 1)

        # Verify DailyLoanSummary was updated correctly
        self.daily_summary.refresh_from_db()
        self.assertEqual(self.daily_summary.disbursement, 300.00)  # 100 + 200
        self.assertEqual(self.daily_summary.disbursements, 2)

        # CRITICAL: Verify first trigger fired (DailyLoanSummary -> LoanAccount)
        self.assertTrue(
            CascadingTriggerHandler.summary_update_called,
            "First trigger (aggregate_to_loan_account) should have been called"
        )
        self.assertEqual(len(CascadingTriggerHandler.summary_disbursements_changed), 1)
        
        # Verify the HasChanged condition detected the change
        summary_change = CascadingTriggerHandler.summary_disbursements_changed[0]
        self.assertEqual(summary_change['old_disbursement'], 0)
        self.assertEqual(summary_change['new_disbursement'], 300.00)
        self.assertEqual(summary_change['old_count'], 0)
        self.assertEqual(summary_change['new_count'], 2)

        # CRITICAL: Verify second trigger fired (LoanAccount totals changed)
        self.assertTrue(
            CascadingTriggerHandler.account_update_called,
            "Second trigger (track_account_changes) should have been called after cascade"
        )
        self.assertEqual(len(CascadingTriggerHandler.account_totals_changed), 1)

        # Verify LoanAccount was updated correctly
        self.loan_account.refresh_from_db()
        self.assertEqual(self.loan_account.total_disbursement, 300.00)
        self.assertEqual(self.loan_account.total_disbursements_count, 2)

        # Verify the account change was tracked
        account_change = CascadingTriggerHandler.account_totals_changed[0]
        self.assertEqual(account_change['old_total'], 0)
        self.assertEqual(account_change['new_total'], 300.00)
        self.assertEqual(account_change['old_count'], 0)
        self.assertEqual(account_change['new_count'], 2)

    def test_multiple_summaries_cascade(self):
        """Test cascading with multiple daily summaries for the same account."""
        # Create another daily summary
        daily_summary2 = DailyLoanSummary.objects.create(
            loan_account=self.loan_account,
            date="2024-01-02",
            disbursement=0,
            disbursements=0,
        )

        LoanTransaction.objects.create(
            daily_loan_summary=daily_summary2,
            amount=150.00,
            transaction_type="DISBURSEMENT",
            status="COMPLETE",
        )

        # Reset tracking
        CascadingTriggerHandler.reset()

        # Update both summaries using bulk update with subquery
        DailyLoanSummary.objects.filter(
            loan_account=self.loan_account
        ).update(
            disbursement=Subquery(
                LoanTransaction.objects.filter(daily_loan_summary_id=OuterRef("pk"))
                .filter(transaction_type="DISBURSEMENT", status="COMPLETE")
                .values("daily_loan_summary_id")
                .annotate(total=Sum("amount"))
                .values("total")[:1]
            ),
            disbursements=Subquery(
                LoanTransaction.objects.filter(daily_loan_summary_id=OuterRef("pk"))
                .filter(transaction_type="DISBURSEMENT", status="COMPLETE")
                .values("daily_loan_summary_id")
                .annotate(count=Count("id"))
                .values("count")[:1]
            ),
        )

        # Verify both triggers fired
        self.assertTrue(CascadingTriggerHandler.summary_update_called)
        self.assertTrue(CascadingTriggerHandler.account_update_called)

        # Verify both summaries were processed
        self.assertEqual(len(CascadingTriggerHandler.summary_disbursements_changed), 2)

        # Verify final totals
        self.loan_account.refresh_from_db()
        self.assertEqual(self.loan_account.total_disbursement, 450.00)  # 300 + 150
        self.assertEqual(self.loan_account.total_disbursements_count, 3)  # 2 + 1


