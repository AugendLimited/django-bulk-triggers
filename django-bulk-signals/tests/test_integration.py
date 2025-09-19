"""
Integration tests for django-bulk-signals.

These tests demonstrate real-world usage patterns and verify that the package
works correctly when used as intended by end users.
"""

from django.db import models
from django.dispatch import receiver
from django.test import TestCase
from django.utils import timezone
from django_bulk_signals.models import BulkSignalModel
from django_bulk_signals.signals import (
    bulk_post_create,
    bulk_post_delete,
    bulk_post_update,
    bulk_pre_create,
    bulk_pre_delete,
    bulk_pre_update,
)
