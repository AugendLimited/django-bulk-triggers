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


@pytest.fixture(scope="function", autouse=True)
def clear_sql_compiler_cache():
    """Clear Django's SQL compiler cache to prevent model registry corruption."""
    from django.db import connection

    # Clear any cached SQL compilers
    if hasattr(connection, 'cursor'):
        # Force Django to clear its internal caches
        from django.apps import apps
        from django.db.models.sql.compiler import SQLCompiler

        # Clear any cached compilers
        if hasattr(SQLCompiler, '_cache'):
            SQLCompiler._cache.clear()

        # Force recreation of model metadata by clearing apps cache
        for app_config in apps.get_app_configs():
            if hasattr(app_config, 'models') and hasattr(app_config.models, '_cache'):
                app_config.models._cache.clear()

    yield

    # Clear again after test
    if hasattr(connection, 'cursor'):
        if hasattr(SQLCompiler, '_cache'):
            SQLCompiler._cache.clear()