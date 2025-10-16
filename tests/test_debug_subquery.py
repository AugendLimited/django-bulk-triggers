"""
Debug test to see what SQL is generated for Subquery updates.
"""

import os
import sys
import django
import logging

# Setup Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('django_bulk_triggers')
logger.setLevel(logging.DEBUG)

from django.db import models, connection
from django.db.models import OuterRef, Subquery
from django_bulk_triggers.manager import BulkTriggerManager


# Define test models
class Currency(models.Model):
    code = models.CharField(max_length=3)
    
    class Meta:
        app_label = 'test_debug_subquery'


class FinancialAccount(models.Model):
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    
    class Meta:
        app_label = 'test_debug_subquery'


class Offer(models.Model):
    name = models.CharField(max_length=100)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, null=True, blank=True)
    
    objects = BulkTriggerManager()
    
    class Meta:
        app_label = 'test_debug_subquery'


class RevenueStream(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    financial_account = models.ForeignKey(FinancialAccount, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        app_label = 'test_debug_subquery'


# Create tables
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
account_eur = FinancialAccount.objects.create(currency=eur, name='EUR Account')
offer = Offer.objects.create(name='Test Offer', currency=usd)
revenue_stream = RevenueStream.objects.create(offer=offer, financial_account=account_eur, amount=100.00)

print(f"\nBefore update: Offer currency = {offer.currency.code}")

# Reset queries
connection.queries_log.clear()

# Test the update with debug logging
print("\n" + "="*80)
print("Testing with framework...")
print("="*80)

subquery = Subquery(
    RevenueStream.objects.filter(offer_id=OuterRef("pk"))
    .order_by("pk")
    .values("financial_account__currency_id")[:1]
)

print(f"\nSubquery type: {type(subquery)}")
print(f"Subquery has output_field: {hasattr(subquery, 'output_field')}")
try:
    print(f"Subquery output_field: {subquery.output_field}")
except Exception as e:
    print(f"Subquery output_field error: {e}")

result = Offer.objects.filter(id__in=[offer.id]).update(currency_id=subquery)

print(f"\nUpdate result: {result}")
print(f"\nSQL queries executed:")
for i, query in enumerate(connection.queries):
    print(f"\nQuery {i+1}:")
    print(f"  SQL: {query['sql']}")

offer.refresh_from_db()
print(f"\nAfter update: Offer currency = {offer.currency.code}")
print(f"Expected: EUR, Got: {offer.currency.code}")

if offer.currency.code == 'EUR':
    print("\n[SUCCESS]")
else:
    print("\n[FAILURE] - Currency not updated!")

# Now test with native Django (bypassing framework)
print("\n" + "="*80)
print("Testing with native Django (no framework)...")
print("="*80)

# Reset to USD
Offer.objects.filter(id=offer.id).update(currency_id=usd.id)
offer.refresh_from_db()
print(f"Reset to: {offer.currency.code}")

connection.queries_log.clear()

# Use native Django queryset (bypass framework)
from django.db.models import QuerySet
result = QuerySet(model=Offer).filter(id__in=[offer.id]).update(
    currency_id=Subquery(
        RevenueStream.objects.filter(offer_id=OuterRef("pk"))
        .order_by("pk")
        .values("financial_account__currency_id")[:1]
    )
)

print(f"\nUpdate result: {result}")
print(f"\nSQL queries executed:")
for i, query in enumerate(connection.queries):
    print(f"\nQuery {i+1}:")
    print(f"  SQL: {query['sql']}")

offer.refresh_from_db()
print(f"\nAfter native update: Offer currency = {offer.currency.code}")
print(f"Expected: EUR, Got: {offer.currency.code}")

if offer.currency.code == 'EUR':
    print("\n[SUCCESS]")
else:
    print("\n[FAILURE] - Currency not updated!")

