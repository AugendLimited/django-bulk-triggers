"""
Pytest configuration for django-bulk-signals tests.
"""
import pytest
from django.core.management import execute_from_command_line
from django.test.utils import get_runner
from django.conf import settings


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Set up the database for testing."""
    with django_db_blocker.unblock():
        # Create database tables
        from django.core.management import call_command
        call_command('migrate', verbosity=0, interactive=False)
