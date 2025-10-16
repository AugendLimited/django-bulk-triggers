"""
Test Subquery with OuterRef in update operations.

This test ensures that Subquery expressions with OuterRef("pk") work correctly
when used in QuerySet.update() operations through the bulk-trigger framework.

Regression test for bug where FK field refresh was skipped, causing a second
UPDATE to revert the Subquery result.
"""

import pytest
from decimal import Decimal
from django.db import models
from django.db.models import OuterRef, Subquery
from django_bulk_triggers.manager import BulkTriggerManager
from django_bulk_triggers.decorators import bulk_trigger


# Test models for Subquery/OuterRef testing
class SubqueryCurrency(models.Model):
    """Currency model for testing Subquery operations."""
    code = models.CharField(max_length=3, unique=True)
    
    class Meta:
        app_label = 'tests'
    
    def __str__(self):
        return self.code


class SubqueryFinancialAccount(models.Model):
    """Financial account with currency FK."""
    currency = models.ForeignKey(SubqueryCurrency, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    
    class Meta:
        app_label = 'tests'
    
    def __str__(self):
        return self.name


class SubqueryOffer(models.Model):
    """Offer model with currency FK that will be updated via Subquery."""
    name = models.CharField(max_length=100)
    currency = models.ForeignKey(
        SubqueryCurrency,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    
    objects = BulkTriggerManager()
    
    class Meta:
        app_label = 'tests'
    
    def __str__(self):
        return self.name


class SubqueryRevenueStream(models.Model):
    """Revenue stream linking offer to financial account."""
    offer = models.ForeignKey(SubqueryOffer, on_delete=models.CASCADE)
    financial_account = models.ForeignKey(
        SubqueryFinancialAccount,
        on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    priority = models.IntegerField(default=0)
    
    class Meta:
        app_label = 'tests'
        ordering = ['priority', 'pk']


@pytest.mark.django_db(transaction=True)
class TestSubqueryOuterRef:
    """Test Subquery with OuterRef in update operations."""
    
    def test_subquery_outerref_pk_fk_update(self):
        """
        Test that Subquery with OuterRef("pk") correctly updates a FK field.
        
        This is a regression test for a bug where:
        1. The Subquery UPDATE would execute correctly
        2. But FK field refresh was skipped during instance refresh
        3. Causing a second UPDATE to revert the Subquery result
        """
        # Create currencies
        usd = SubqueryCurrency.objects.create(code='USD')
        eur = SubqueryCurrency.objects.create(code='EUR')
        
        # Create financial account with EUR
        account_eur = SubqueryFinancialAccount.objects.create(
            currency=eur,
            name='EUR Account'
        )
        
        # Create offer with USD
        offer = SubqueryOffer.objects.create(
            name='Test Offer',
            currency=usd
        )
        
        # Create revenue stream linking offer to EUR account
        SubqueryRevenueStream.objects.create(
            offer=offer,
            financial_account=account_eur,
            amount=Decimal('100.00'),
            priority=1
        )
        
        # Verify initial state
        assert offer.currency.code == 'USD'
        
        # Update offer currency using Subquery with OuterRef("pk")
        # This should set the currency to the financial account's currency (EUR)
        result = SubqueryOffer.objects.filter(pk=offer.pk).update(
            currency_id=Subquery(
                SubqueryRevenueStream.objects
                .filter(offer_id=OuterRef("pk"))
                .order_by("priority", "pk")
                .values("financial_account__currency_id")[:1]
            )
        )
        
        # Verify the update was applied
        assert result == 1
        
        # Refresh and verify the currency was updated
        offer.refresh_from_db()
        assert offer.currency.code == 'EUR', \
            f"Expected currency to be EUR, but got {offer.currency.code}"
    
    def test_subquery_outerref_with_multiple_records(self):
        """
        Test Subquery with OuterRef when multiple offers are updated.
        """
        # Create currencies
        usd = SubqueryCurrency.objects.create(code='USD')
        eur = SubqueryCurrency.objects.create(code='EUR')
        gbp = SubqueryCurrency.objects.create(code='GBP')
        
        # Create financial accounts
        account_eur = SubqueryFinancialAccount.objects.create(
            currency=eur,
            name='EUR Account'
        )
        account_gbp = SubqueryFinancialAccount.objects.create(
            currency=gbp,
            name='GBP Account'
        )
        
        # Create offers with USD
        offer1 = SubqueryOffer.objects.create(name='Offer 1', currency=usd)
        offer2 = SubqueryOffer.objects.create(name='Offer 2', currency=usd)
        
        # Create revenue streams
        SubqueryRevenueStream.objects.create(
            offer=offer1,
            financial_account=account_eur,
            amount=Decimal('100.00')
        )
        SubqueryRevenueStream.objects.create(
            offer=offer2,
            financial_account=account_gbp,
            amount=Decimal('200.00')
        )
        
        # Update both offers using Subquery
        result = SubqueryOffer.objects.filter(
            pk__in=[offer1.pk, offer2.pk]
        ).update(
            currency_id=Subquery(
                SubqueryRevenueStream.objects
                .filter(offer_id=OuterRef("pk"))
                .order_by("pk")
                .values("financial_account__currency_id")[:1]
            )
        )
        
        assert result == 2
        
        # Verify both offers were updated correctly
        offer1.refresh_from_db()
        offer2.refresh_from_db()
        assert offer1.currency.code == 'EUR'
        assert offer2.currency.code == 'GBP'
    
    def test_subquery_outerref_with_triggers(self):
        """
        Test that Subquery with OuterRef works correctly with triggers.
        """
        trigger_calls = []
        
        @bulk_trigger(SubqueryOffer, "after_update")
        def track_currency_change(instances, originals, **kwargs):
            """Track when currency changes."""
            for instance, original in zip(instances, originals):
                if instance.currency_id != original.currency_id:
                    trigger_calls.append({
                        'offer': instance.name,
                        'old_currency': original.currency_id,
                        'new_currency': instance.currency_id
                    })
        
        try:
            # Create test data
            usd = SubqueryCurrency.objects.create(code='USD')
            eur = SubqueryCurrency.objects.create(code='EUR')
            
            account_eur = SubqueryFinancialAccount.objects.create(
                currency=eur,
                name='EUR Account'
            )
            
            offer = SubqueryOffer.objects.create(
                name='Test Offer',
                currency=usd
            )
            
            SubqueryRevenueStream.objects.create(
                offer=offer,
                financial_account=account_eur,
                amount=Decimal('100.00')
            )
            
            # Update using Subquery - triggers should fire
            SubqueryOffer.objects.filter(pk=offer.pk).update(
                currency_id=Subquery(
                    SubqueryRevenueStream.objects
                    .filter(offer_id=OuterRef("pk"))
                    .values("financial_account__currency_id")[:1]
                )
            )
            
            # Verify trigger was called
            assert len(trigger_calls) == 1
            assert trigger_calls[0]['offer'] == 'Test Offer'
            assert trigger_calls[0]['old_currency'] == usd.id
            assert trigger_calls[0]['new_currency'] == eur.id
            
            # Verify the update was persisted
            offer.refresh_from_db()
            assert offer.currency.code == 'EUR'
            
        finally:
            # Clean up trigger
            from django_bulk_triggers.registry import _triggers
            if SubqueryOffer in _triggers:
                _triggers[SubqueryOffer].pop("after_update", None)
    
    def test_subquery_outerref_no_match(self):
        """
        Test Subquery with OuterRef when no matching record exists.
        The FK should be set to NULL.
        """
        # Create currency and offer
        usd = SubqueryCurrency.objects.create(code='USD')
        offer = SubqueryOffer.objects.create(
            name='Test Offer',
            currency=usd
        )
        
        # No revenue stream created, so Subquery will return NULL
        
        # Update using Subquery - should set currency to NULL
        result = SubqueryOffer.objects.filter(pk=offer.pk).update(
            currency_id=Subquery(
                SubqueryRevenueStream.objects
                .filter(offer_id=OuterRef("pk"))
                .values("financial_account__currency_id")[:1]
            )
        )
        
        assert result == 1
        
        # Verify currency was set to NULL
        offer.refresh_from_db()
        assert offer.currency is None
    
    def test_subquery_outerref_with_ordering(self):
        """
        Test that Subquery respects ordering when multiple records exist.
        """
        # Create currencies
        usd = SubqueryCurrency.objects.create(code='USD')
        eur = SubqueryCurrency.objects.create(code='EUR')
        gbp = SubqueryCurrency.objects.create(code='GBP')
        
        # Create financial accounts
        account_eur = SubqueryFinancialAccount.objects.create(
            currency=eur,
            name='EUR Account'
        )
        account_gbp = SubqueryFinancialAccount.objects.create(
            currency=gbp,
            name='GBP Account'
        )
        
        # Create offer
        offer = SubqueryOffer.objects.create(name='Test Offer', currency=usd)
        
        # Create multiple revenue streams with different priorities
        SubqueryRevenueStream.objects.create(
            offer=offer,
            financial_account=account_gbp,
            amount=Decimal('200.00'),
            priority=2  # Lower priority
        )
        SubqueryRevenueStream.objects.create(
            offer=offer,
            financial_account=account_eur,
            amount=Decimal('100.00'),
            priority=1  # Higher priority (smaller number = higher priority)
        )
        
        # Update using Subquery with ordering by priority
        SubqueryOffer.objects.filter(pk=offer.pk).update(
            currency_id=Subquery(
                SubqueryRevenueStream.objects
                .filter(offer_id=OuterRef("pk"))
                .order_by("priority")  # Should pick the EUR account (priority=1)
                .values("financial_account__currency_id")[:1]
            )
        )
        
        # Verify the highest priority (priority=1) currency was selected
        offer.refresh_from_db()
        assert offer.currency.code == 'EUR', \
            f"Expected EUR (priority=1), but got {offer.currency.code}"

