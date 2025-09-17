"""
Django signals for bulk operations.

This module defines the signal types that fire before and after bulk operations,
providing Salesforce-style trigger behavior using Django's signal framework.
"""

from django.dispatch import Signal

# Bulk operation signals - Salesforce-style trigger events
bulk_pre_create = Signal()
bulk_post_create = Signal()

bulk_pre_update = Signal()
bulk_post_update = Signal()

bulk_pre_delete = Signal()
bulk_post_delete = Signal()

# Signal documentation
bulk_pre_create.__doc__ = """
Signal sent before bulk_create operation.

Arguments:
    sender: The model class
    instances: List of model instances being created
    **kwargs: Additional arguments passed to bulk_create
"""

bulk_post_create.__doc__ = """
Signal sent after bulk_create operation.

Arguments:
    sender: The model class
    instances: List of created model instances (with PKs assigned)
    **kwargs: Additional arguments passed to bulk_create
"""

bulk_pre_update.__doc__ = """
Signal sent before bulk_update operation.

Arguments:
    sender: The model class
    instances: List of model instances being updated
    originals: List of original model instances (for comparison)
    fields: List of field names being updated
    **kwargs: Additional arguments passed to bulk_update
"""

bulk_post_update.__doc__ = """
Signal sent after bulk_update operation.

Arguments:
    sender: The model class
    instances: List of updated model instances
    originals: List of original model instances (for comparison)
    fields: List of field names that were updated
    **kwargs: Additional arguments passed to bulk_update
"""

bulk_pre_delete.__doc__ = """
Signal sent before bulk_delete operation.

Arguments:
    sender: The model class
    instances: List of model instances being deleted
    **kwargs: Additional arguments passed to bulk_delete
"""

bulk_post_delete.__doc__ = """
Signal sent after bulk_delete operation.

Arguments:
    sender: The model class
    instances: List of deleted model instances
    **kwargs: Additional arguments passed to bulk_delete
"""
