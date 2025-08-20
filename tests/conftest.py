"""
Pytest configuration for django-bulk-hooks tests.
"""

import pytest
from django.conf import settings

# Configure Django settings for testing
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
            "tests",
        ],
        USE_TZ=True,
        TIME_ZONE="UTC",
        SECRET_KEY="test-secret-key",
    )


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
