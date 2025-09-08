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


@pytest.fixture
def test_user():
    """Create a test user for testing."""
    import uuid
    from django.db import connection
    from django.utils import timezone

    # Use raw SQL to avoid RETURNING clause issues completely
    # Generate unique values to avoid conflicts
    unique_id = str(uuid.uuid4())[:8]
    username = f"testuser_{unique_id}"
    email = f"test_{unique_id}@example.com"

    with connection.cursor() as cursor:
        created_at = timezone.now()
        cursor.execute(
            'INSERT INTO "tests_usermodel" ("username", "email", "is_active", "created_at") VALUES (?, ?, ?, ?)',
            [username, email, True, created_at]
        )
        user_id = cursor.lastrowid

    # Get the created user
    from tests.models import UserModel
    user = UserModel.objects.get(id=user_id)
    yield user
    user.delete()


@pytest.fixture
def test_category():
    """Create a test category for testing."""
    import uuid
    from django.db import connection

    # Use raw SQL to avoid RETURNING clause issues completely
    # Generate unique values to avoid conflicts
    unique_id = str(uuid.uuid4())[:8]
    name = f"Test Category {unique_id}"

    with connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO "tests_category" ("name", "description", "is_active") VALUES (?, ?, ?)',
            [name, "Test category description", True]
        )
        category_id = cursor.lastrowid

    # Get the created category
    from tests.models import Category
    category = Category.objects.get(id=category_id)
    yield category
    category.delete()


@pytest.fixture
def test_hook_instances(test_user, test_category):
    """Create test hook model instances for testing."""
    from tests.models import HookModel

    instances = []
    for i in range(3):
        instance = HookModel.objects.create(
            name=f"Test Instance {i}",
            value=i * 10,
            category=test_category,
            created_by=test_user
        )
        instances.append(instance)

    yield instances

    # Clean up
    for instance in instances:
        instance.delete()


@pytest.fixture
def hook_tracker():
    """Create a hook tracker for testing hook calls."""
    from tests.utils import HookTracker

    tracker = HookTracker()
    yield tracker