#!/usr/bin/env python
"""
Example usage of lambda conditions and anonymous functions with django-bulk-hooks

This module demonstrates how to use anonymous functions and custom conditions
in hooks for more flexible and powerful filtering.
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
if not settings.configured:
    settings.configure(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
        ],
        USE_TZ=False,
    )
    django.setup()

from django.db import models
from django_bulk_hooks import HookHandler, hook, LambdaCondition
from django_bulk_hooks.constants import AFTER_CREATE, AFTER_UPDATE, BEFORE_UPDATE
from django_bulk_hooks.models import HookModelMixin
from django_bulk_hooks.conditions import IsEqual, HasChanged, IsGreaterThan


class Product(HookModelMixin, models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    stock_quantity = models.IntegerField(default=0)
    rating = models.FloatField(default=0.0)


class Order(HookModelMixin, models.Model):
    customer_name = models.CharField(max_length=100)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='pending')
    is_urgent = models.BooleanField(default=False)


class LambdaConditionExamples(HookHandler):
    """
    Examples of using lambda conditions and anonymous functions in hooks.
    """
    
    # Example 1: Simple lambda condition
    @hook(Product, "after_create", condition=LambdaCondition(
        lambda instance: instance.price > 100
    ))
    def handle_expensive_products(self, new_records, old_records):
        """Handle products with price > 100"""
        for product in new_records:
            print(f"Expensive product created: {product.name} - ${product.price}")
    
    # Example 2: Lambda with multiple conditions
    @hook(Product, "after_update", condition=LambdaCondition(
        lambda instance: instance.price > 50 and instance.is_active and instance.stock_quantity > 0
    ))
    def handle_available_expensive_products(self, new_records, old_records):
        """Handle active products with price > 50 and stock > 0"""
        for product in new_records:
            print(f"Available expensive product: {product.name}")
    
    # Example 3: Lambda comparing with original instance
    @hook(Product, "after_update", condition=LambdaCondition(
        lambda instance, original: original and instance.price > original.price * 1.5
    ))
    def handle_significant_price_increases(self, new_records, old_records):
        """Handle products with >50% price increase"""
        for new_product, old_product in zip(new_records, old_records):
            if old_product:
                increase = ((new_product.price - old_product.price) / old_product.price) * 100
                print(f"Significant price increase: {new_product.name} +{increase:.1f}%")
    
    # Example 4: Lambda with complex logic
    @hook(Order, "after_create", condition=LambdaCondition(
        lambda instance: (
            instance.total_amount > 1000 or 
            instance.is_urgent or 
            instance.customer_name.lower().startswith('vip')
        )
    ))
    def handle_priority_orders(self, new_records, old_records):
        """Handle high-value, urgent, or VIP orders"""
        for order in new_records:
            print(f"Priority order: {order.customer_name} - ${order.total_amount}")
    
    # Example 5: Lambda with field validation
    @hook(Product, "before_update", condition=LambdaCondition(
        lambda instance: instance.rating < 0 or instance.rating > 5
    ))
    def validate_rating_range(self, new_records, old_records):
        """Validate rating is between 0 and 5"""
        for product in new_records:
            raise ValueError(f"Rating must be between 0 and 5, got {product.rating}")


class CustomConditionExamples(HookHandler):
    """
    Examples of creating custom condition classes for reusable logic.
    """
    
    # Example 6: Custom condition class
    class IsPremiumProduct(HookCondition):
        def check(self, instance, original_instance=None):
            return (
                instance.price > 200 and 
                instance.rating >= 4.0 and 
                instance.is_active
            )
        
        def get_required_fields(self):
            return {'price', 'rating', 'is_active'}
    
    @hook(Product, "after_create", condition=IsPremiumProduct())
    def handle_premium_products(self, new_records, old_records):
        """Handle premium products"""
        for product in new_records:
            print(f"Premium product: {product.name}")
    
    # Example 7: Custom condition with parameters
    class IsInCategory(HookCondition):
        def __init__(self, category):
            self.category = category
        
        def check(self, instance, original_instance=None):
            return instance.category.lower() == self.category.lower()
        
        def get_required_fields(self):
            return {'category'}
    
    @hook(Product, "after_update", condition=IsInCategory("electronics"))
    def handle_electronics_updates(self, new_records, old_records):
        """Handle electronics product updates"""
        for product in new_records:
            print(f"Electronics update: {product.name}")


class CombinedConditionExamples(HookHandler):
    """
    Examples of combining lambda conditions with built-in conditions.
    """
    
    # Example 8: Combining lambda with built-in conditions
    @hook(Product, "after_update", condition=(
        HasChanged("price") & 
        LambdaCondition(lambda instance: instance.price > 100)
    ))
    def handle_expensive_price_changes(self, new_records, old_records):
        """Handle when expensive products have price changes"""
        for new_product, old_product in zip(new_records, old_records):
            print(f"Expensive product price changed: {new_product.name}")
    
    # Example 9: Complex combined conditions
    @hook(Order, "after_update", condition=(
        LambdaCondition(lambda instance: instance.status == 'completed') &
        LambdaCondition(lambda instance, original: original and instance.total_amount > original.total_amount)
    ))
    def handle_completed_orders_with_increased_amount(self, new_records, old_records):
        """Handle completed orders that had amount increases"""
        for new_order, old_order in zip(new_records, old_records):
            if old_order:
                increase = new_order.total_amount - old_order.total_amount
                print(f"Completed order with amount increase: {new_order.customer_name} +${increase}")


# Example usage functions
def demonstrate_lambda_conditions():
    """Demonstrate how to use lambda conditions in practice."""
    
    # Create some test products
    products = [
        Product(name="Cheap Widget", price=25.00, category="tools", is_active=True, stock_quantity=10),
        Product(name="Expensive Gadget", price=500.00, category="electronics", is_active=True, stock_quantity=5),
        Product(name="Premium Tool", price=300.00, category="tools", is_active=True, stock_quantity=0),
    ]
    
    # Create some test orders
    orders = [
        Order(customer_name="John Doe", total_amount=1500.00, status="pending", is_urgent=False),
        Order(customer_name="VIP Customer", total_amount=500.00, status="pending", is_urgent=True),
        Order(customer_name="Regular Joe", total_amount=50.00, status="pending", is_urgent=False),
    ]
    
    print("=== Lambda Condition Examples ===")
    print("Creating products and orders to demonstrate lambda conditions...")
    
    # These would trigger the lambda conditions when saved
    for product in products:
        print(f"Product: {product.name} - ${product.price}")
    
    for order in orders:
        print(f"Order: {order.customer_name} - ${order.total_amount}")


if __name__ == "__main__":
    demonstrate_lambda_conditions() 