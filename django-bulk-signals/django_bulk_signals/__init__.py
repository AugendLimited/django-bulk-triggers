"""
Django Bulk Signals - Simple, Zero-Coupling Implementation

This is the simplified version that eliminates all coupling issues.
Each component has a single responsibility and zero dependencies on other components.

Usage:
    from django_bulk_signals import BulkSignalManager
    from django_bulk_signals.decorators_simple import before_create, after_update
    from django_bulk_signals.conditions_simple import HasChanged

    class Account(models.Model):
        name = models.CharField(max_length=100)
        status = models.CharField(max_length=20, default='active')

        objects = BulkSignalManager()

    @before_create(Account)
    def validate_account(sender, instances, **kwargs):
        for account in instances:
            if not account.name:
                raise ValueError("Account name is required")

    @after_update(Account, condition=HasChanged('status'))
    def handle_status_change(sender, instances, originals, **kwargs):
        for account, original in zip(instances, originals):
            if account.status != original.status:
                # Handle status change
                pass
"""

from django_bulk_signals.core import BulkSignalManager, BulkSignalQuerySet

# Export the main components
__all__ = [
    "BulkSignalManager",
    "BulkSignalQuerySet",
]
