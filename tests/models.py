"""
Test models for django-bulk-hooks testing.
"""

from django.db import models
from django.contrib.auth.models import User

from django_bulk_hooks.manager import BulkHookManager
from django_bulk_hooks.models import HookModelMixin


class TestUser(models.Model):
    """Test user model for foreign key testing."""

    username = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username


class Category(models.Model):
    """Test category model for foreign key testing."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class HookModel(HookModelMixin):
    """Main test model for bulk operations testing."""

    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="pending")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, null=True, blank=True
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True
    )
    computed_value = models.IntegerField(default=0)

    objects = BulkHookManager()

    def __str__(self):
        return f"{self.name} (id: {self.pk})"


class RelatedModel(models.Model):
    """Related model for testing relationships."""

    hook_model = models.ForeignKey(
        HookModel, on_delete=models.CASCADE, related_name="related_items"
    )
    amount = models.IntegerField()
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hook_model.name} - {self.amount}"


class SimpleModel(HookModelMixin):
    """Simple model for basic testing."""

    name = models.CharField(max_length=100)
    value = models.IntegerField(default=0)

    objects = BulkHookManager()

    def __str__(self):
        return self.name


class ComplexModel(HookModelMixin):
    """Complex model with various field types for comprehensive testing."""

    char_field = models.CharField(max_length=100)
    text_field = models.TextField()
    integer_field = models.IntegerField()
    decimal_field = models.DecimalField(max_digits=10, decimal_places=2)
    boolean_field = models.BooleanField(default=False)
    date_field = models.DateField(null=True, blank=True)
    datetime_field = models.DateTimeField(null=True, blank=True)
    email_field = models.EmailField()
    url_field = models.URLField()
    file_field = models.FileField(upload_to="test_files/", null=True, blank=True)
    image_field = models.ImageField(upload_to="test_images/", null=True, blank=True)
    json_field = models.JSONField(default=dict)

    objects = BulkHookManager()

    def __str__(self):
        return self.char_field
