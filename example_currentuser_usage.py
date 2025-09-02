"""
Example usage of CurrentUserField with django-bulk-hooks

This example shows how to use CurrentUserField from django-currentuser
with bulk operations in django-bulk-hooks.
"""

from django.db import models
from django_currentuser.db.models import CurrentUserField
from django_bulk_hooks.manager import BulkHookManager


class AuditableModel(models.Model):
    """Example model with CurrentUserField for auditing."""
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = CurrentUserField(related_name="created_%(class)ss", on_update=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = CurrentUserField(related_name="updated_%(class)ss", on_update=True)

    objects = BulkHookManager()

    class Meta:
        app_label = 'example'


def bulk_create_with_user():
    """Example of bulk creating objects with current user context."""
    from django.contrib.auth import get_user_model
    from django_currentuser.middleware import get_current_authenticated_user

    User = get_user_model()

    # Get current user (this would normally come from request.user)
    current_user = get_current_authenticated_user() or User.objects.first()

    # Create objects
    objects_to_create = [
        AuditableModel(name="Object 1"),
        AuditableModel(name="Object 2"),
        AuditableModel(name="Object 3"),
    ]

    # Bulk create with current user context
    # This ensures CurrentUserField gets the correct user
    created_objects = AuditableModel.objects.bulk_create(
        objects_to_create,
        current_user=current_user
    )

    print(f"Created {len(created_objects)} objects with user: {current_user}")
    return created_objects


def bulk_update_with_user():
    """Example of bulk updating objects with current user context."""
    from django.contrib.auth import get_user_model
    from django_currentuser.middleware import get_current_authenticated_user

    User = get_user_model()

    # Get current user
    current_user = get_current_authenticated_user() or User.objects.first()

    # Get existing objects to update
    objects_to_update = list(AuditableModel.objects.all()[:3])

    # Modify the objects
    for obj in objects_to_update:
        obj.name = f"Updated {obj.name}"

    # Bulk update with current user context
    # This ensures updated_by field gets set to the current user
    updated_count = AuditableModel.objects.bulk_update(
        objects_to_update,
        fields=['name'],
        current_user=current_user
    )

    print(f"Updated {updated_count} objects with user: {current_user}")
    return updated_count


# Usage in views or other code:

def my_view(request):
    """Example view showing how to use bulk operations with current user."""
    # Your view logic here...

    # For bulk create
    objects = [
        AuditableModel(name="New Object 1"),
        AuditableModel(name="New Object 2"),
    ]

    AuditableModel.objects.bulk_create(objects, current_user=request.user)

    # For bulk update
    existing_objects = AuditableModel.objects.filter(some_condition=True)
    for obj in existing_objects:
        obj.some_field = new_value

    AuditableModel.objects.bulk_update(
        list(existing_objects),
        fields=['some_field'],
        current_user=request.user
    )

    return response
