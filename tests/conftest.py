"""
Pytest configuration for django-bulk-hooks tests.
"""

import os

import pytest
from django.conf import settings

# Configure Django settings before any imports
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

    # Import Django and configure settings
    import django

    django.setup()


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup):
    """Ensure database is set up for tests."""
    pass


@pytest.fixture
def db_access_without_rollback_and_truncate(django_db_blocker):
    """Allow database access without rollback and truncate."""
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()
