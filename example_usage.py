#!/usr/bin/env python
"""
Example usage of django-bulk-hooks

This module demonstrates how to use django-bulk-hooks to add custom logic
to Django model operations, with a focus on safely handling related objects.
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

import logging

from django.db import models

from django_bulk_hooks import HookHandler, hook
from django_bulk_hooks.constants import (
    AFTER_CREATE,
    AFTER_DELETE,
    AFTER_UPDATE,
    BEFORE_CREATE,
    BEFORE_DELETE,
    BEFORE_UPDATE,
)
from django_bulk_hooks.models import HookModelMixin
from django_bulk_hooks.conditions import safe_get_related_attr, IsEqual, HasChanged


# Configure logging to see all messages
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


"""
Example usage of django-bulk-hooks

This module demonstrates how to use django-bulk-hooks to add custom logic
to Django model operations, with a focus on safely handling related objects.
"""


class Status(models.Model):
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)


class Category(models.Model):
    name = models.CharField(max_length=100)
    status = models.ForeignKey(Status, on_delete=models.CASCADE)


class Product(HookModelMixin, models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    status = models.ForeignKey(Status, on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProductHandler:
    """
    Handler class for Product model hooks.
    
    This demonstrates best practices for handling related objects safely
    in hooks, especially during bulk operations.
    """
    
    @hook(Product, "before_create")
    def set_default_status(self, old_records=None, new_records=None):
        """Set default status for new products."""
        default_status = Status.objects.filter(name="Draft").first()
        for product in new_records:
            if product.status is None:
                product.status = default_status
    
    @hook(Product, "after_create")
    def log_product_creation(self, old_records=None, new_records=None):
        """Log when products are created."""
        for product in new_records:
            print(f"Created product: {product.name}")
    
    @hook(Product, "before_update")
    def validate_price_changes(self, old_records=None, new_records=None):
        """Validate price changes."""
        for new_product, old_product in zip(new_records, old_records):
            if new_product.price < 0:
                raise ValueError("Price cannot be negative")
    
    @hook(Product, "after_update", condition=HasChanged("status"))
    def notify_status_change(self, old_records=None, new_records=None):
        """Notify when product status changes."""
        for new_product, old_product in zip(new_records, old_records):
            print(f"Product {new_product.name} status changed from {old_product.status} to {new_product.status}")
    
    @hook(Product, "before_delete")
    def prevent_active_deletion(self, old_records=None, new_records=None):
        """Prevent deletion of active products."""
        for product in new_records:
            if product.is_active:
                raise ValueError(f"Cannot delete active product: {product.name}")


class TransactionHandler:
    """
    Example handler demonstrating safe handling of related objects.
    
    This shows how to avoid RelatedObjectDoesNotExist errors when
    accessing related fields in hooks.
    """
    
    @hook(Product, "after_create")
    def process_transactions(self, new_records, old_records=None):
        """Process transactions for new products."""
        for product in new_records:
            # ❌ DANGEROUS: This can raise RelatedObjectDoesNotExist
            # if product.status is None or the related object doesn't exist
            # status_name = product.status.name
            
            # ✅ SAFE: Use safe_get_related_attr to handle None values
            status_name = safe_get_related_attr(product, 'status', 'name')
            
            if status_name == "Active":
                print(f"Processing active product: {product.name}")
            elif status_name is None:
                print(f"Product {product.name} has no status set")
            
            # ✅ SAFE: Check for related object existence
            category = safe_get_related_attr(product, 'category')
            if category:
                print(f"Product {product.name} belongs to category: {category.name}")
            else:
                print(f"Product {product.name} has no category")


class BulkOperationHandler:
    """
    Handler for bulk operations with proper error handling.
    """
    
    @hook(Product, "before_create")
    def prepare_bulk_creation(self, new_records, old_records=None):
        """Prepare products for bulk creation."""
        # Get default status once to avoid multiple queries
        default_status = Status.objects.filter(name="Draft").first()
        
        for product in new_records:
            # Set default values for related fields
            if product.status is None:
                product.status = default_status
            
            # Ensure required fields are set
            if not product.name:
                product.name = f"Product-{product.id or 'NEW'}"
    
    @hook(Product, "after_create")
    def post_bulk_creation(self, new_records, old_records=None):
        """Handle post-creation logic for bulk operations."""
        # Group products by status for efficient processing
        products_by_status = {}
        
        for product in new_records:
            status_name = safe_get_related_attr(product, 'status', 'name')
            if status_name not in products_by_status:
                products_by_status[status_name] = []
            products_by_status[status_name].append(product)
        
        # Process each group
        for status_name, products in products_by_status.items():
            if status_name == "Active":
                self._activate_products(products)
            elif status_name == "Draft":
                self._notify_draft_products(products)
    
    def _activate_products(self, products):
        """Activate a list of products."""
        print(f"Activating {len(products)} products")
        # Add activation logic here
    
    def _notify_draft_products(self, products):
        """Notify about draft products."""
        print(f"Created {len(products)} draft products")
        # Add notification logic here


# Example usage in your Django project:

def example_usage():
    """Example of how to use the hooks in practice."""
    
    # Create some test data
    active_status = Status.objects.create(name="Active")
    draft_status = Status.objects.create(name="Draft")
    category = Category.objects.create(name="Electronics", status=active_status)
    
    # Single product creation (triggers hooks)
    product = Product.objects.create(
        name="Test Product",
        price=99.99,
        category=category,
        status=draft_status
    )
    
    # Bulk creation (triggers hooks for each product)
    products = [
        Product(name="Product 1", price=10.00, category=category),
        Product(name="Product 2", price=20.00, category=category),
        Product(name="Product 3", price=30.00, category=category),
    ]
    
    # This will trigger BEFORE_CREATE and AFTER_CREATE hooks for each product
    created_products = Product.objects.bulk_create(products)
    
    # Update products (triggers hooks)
    for product in created_products:
        product.price *= 1.1  # 10% price increase
    
    # This will trigger BEFORE_UPDATE and AFTER_UPDATE hooks
    Product.objects.bulk_update(created_products, fields=['price'])
    
    # Delete products (triggers hooks)
    # This will trigger BEFORE_DELETE and AFTER_DELETE hooks
    Product.objects.bulk_delete(created_products)


if __name__ == "__main__":
    # This would typically be run in a Django management command
    # or as part of your application logic
    example_usage()
