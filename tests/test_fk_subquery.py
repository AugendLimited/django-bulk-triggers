"""
Test to reproduce the bug with Subquery containing OuterRef("pk") in update operations.
"""

import os
import sys
import django

# Setup Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from django.db import models
from django.db.models import OuterRef, Subquery
from django_bulk_triggers.manager import BulkTriggerManager


# Define test models
class Currency(models.Model):
    code = models.CharField(max_length=3)
    
    class Meta:
        app_label = 'test_fk_subquery'


class FinancialAccount(models.Model):
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    
    class Meta:
        app_label = 'test_fk_subquery'


class Offer(models.Model):
    name = models.CharField(max_length=100)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, null=True, blank=True)
    
    objects = BulkTriggerManager()
    
    class Meta:
        app_label = 'test_fk_subquery'


class RevenueStream(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    financial_account = models.ForeignKey(FinancialAccount, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        app_label = 'test_fk_subquery'


# Create tables
from django.db import connection
with connection.schema_editor() as schema_editor:
    for model in [Currency, FinancialAccount, Offer, RevenueStream]:
        try:
            schema_editor.delete_model(model)
        except:
            pass
        schema_editor.create_model(model)

# Create test data
print("Creating test data...")
usd = Currency.objects.create(code='USD')
eur = Currency.objects.create(code='EUR')

account_usd = FinancialAccount.objects.create(currency=usd, name='USD Account')
account_eur = FinancialAccount.objects.create(currency=eur, name='EUR Account')

offer = Offer.objects.create(name='Test Offer', currency=usd)
revenue_stream = RevenueStream.objects.create(
    offer=offer,
    financial_account=account_eur,  # Using EUR account
    amount=100.00
)

print(f"\nInitial state:")
print(f"Offer ID: {offer.id}")
print(f"Offer Currency: {offer.currency.code}")
print(f"RevenueStream Financial Account Currency: {revenue_stream.financial_account.currency.code}")

# Test the bug: Update using Subquery with OuterRef("pk")
print("\n" + "="*80)
print("Testing Subquery with OuterRef('pk')...")
print("="*80)

try:
    # This should update the offer's currency to match the revenue stream's financial account currency
    result = Offer.objects.filter(id__in=[offer.id]).update(
        currency_id=Subquery(
            RevenueStream.objects.filter(offer_id=OuterRef("pk"))
            .order_by("pk")
            .values("financial_account__currency_id")[:1]
        )
    )
    print(f"\n[OK] Update succeeded! Updated {result} row(s)")
    
    # Refresh and check the result
    offer.refresh_from_db()
    print(f"Offer Currency after update: {offer.currency.code}")
    
    if offer.currency.code == 'EUR':
        print("\n[SUCCESS] Currency was correctly updated to EUR!")
    else:
        print(f"\n[FAILURE] Currency should be EUR but is {offer.currency.code}")
        
except Exception as e:
    print(f"\n[ERROR] Update FAILED with error: {e}")
    import traceback
    traceback.print_exc()

# Test with bypass to confirm it works
print("\n" + "="*80)
print("Testing with bypass_triggers (should work)...")
print("="*80)

# Reset to USD
offer.currency = usd
offer.save()
print(f"Reset offer currency to: {offer.currency.code}")

try:
    from django_bulk_triggers.decorators import no_triggers
    
    with no_triggers():
        result = Offer.objects.filter(id__in=[offer.id]).update(
            currency_id=Subquery(
                RevenueStream.objects.filter(offer_id=OuterRef("pk"))
                .order_by("pk")
                .values("financial_account__currency_id")[:1]
            )
        )
    print(f"\n[OK] Update with bypass succeeded! Updated {result} row(s)")
    
    offer.refresh_from_db()
    print(f"Offer Currency after update: {offer.currency.code}")
    
    if offer.currency.code == 'EUR':
        print("\n[SUCCESS] Currency was correctly updated to EUR with bypass!")
    else:
        print(f"\n[FAILURE] Currency should be EUR but is {offer.currency.code}")
        
except Exception as e:
    print(f"\n[ERROR] Update with bypass FAILED with error: {e}")
    import traceback
    traceback.print_exc()
