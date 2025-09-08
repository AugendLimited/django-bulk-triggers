# Django Bulk Triggers Test Suite

This directory contains comprehensive unit tests for the django-bulk-triggers package.

## Test Structure

### Core Test Files

- `test_handler.py` - Tests for the handler module (Trigger class, TriggerContextState, etc.)
- `test_decorators.py` - Tests for the decorators module (trigger, select_related)
- `test_conditions.py` - Tests for the conditions module (IsEqual, HasChanged, etc.)
- `test_registry.py` - Tests for the registry module (register_trigger, get_triggers)
- `test_manager.py` - Tests for the manager module (BulkTriggerManager)
- `test_priority_and_enums.py` - Tests for priority and enum modules
- `test_integration.py` - Integration tests for the entire system
- `test_subquery_triggers.py` - Tests for Subquery functionality (existing)

### Test Utilities

- `models.py` - Test models used across all tests
- `utils.py` - Utility functions and test helpers
- `conftest.py` - Pytest configuration and fixtures

## Running Tests

### Using pytest (recommended)

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=django_bulk_triggers --cov-report=html

# Run specific test file
poetry run pytest tests/test_handler.py

# Run specific test class
poetry run pytest tests/test_handler.py::TestTriggerContextState

# Run specific test method
poetry run pytest tests/test_handler.py::TestTriggerContextState::test_is_before_property

# Run only unit tests
poetry run pytest -m unit

# Run only integration tests
poetry run pytest -m integration

# Run tests excluding slow ones
poetry run pytest -m "not slow"
```

### Using Django's test runner

```bash
# Run all tests
poetry run python manage.py test tests

# Run specific test
poetry run python manage.py test tests.test_handler
```

## Test Coverage

The test suite aims to provide comprehensive coverage of:

- **Handler Module**: Trigger class, TriggerContextState, trigger queue management
- **Decorators Module**: trigger decorator, select_related decorator
- **Conditions Module**: All condition classes and their combinations
- **Registry Module**: Trigger registration and retrieval
- **Manager Module**: BulkTriggerManager functionality
- **Priority & Enums**: Priority levels and trigger events
- **Integration**: Full system workflows and real-world scenarios

## Test Models

The test suite uses several Django models:

- `User` - Basic user model for foreign key testing
- `Category` - Category model for foreign key testing
- `TriggerModel` - Main test model with various field types
- `SimpleModel` - Simple model for basic testing
- `ComplexModel` - Model with various field types for comprehensive testing
- `RelatedModel` - Related model for relationship testing

## Test Utilities

### TriggerTracker

A utility class for tracking trigger calls in tests:

```python
tracker = TriggerTracker()
# ... perform operations ...
assert len(tracker.before_create_calls) == 1
assert len(tracker.after_update_calls) == 0
```

### Helper Functions

- `create_test_instances()` - Create test model instances
- `assert_trigger_called()` - Assert trigger was called specific number of times
- `assert_trigger_not_called()` - Assert trigger was not called

## Test Categories

### Unit Tests
- Test individual components in isolation
- Use mocking where appropriate
- Focus on specific functionality

### Integration Tests
- Test components working together
- Use real database operations
- Test complete workflows

### Real-World Scenarios
- Test common usage patterns
- Simulate actual application scenarios
- Test performance with large datasets

## Adding New Tests

When adding new tests:

1. **Follow naming conventions**: `test_*.py` files, `Test*` classes, `test_*` methods
2. **Use appropriate test models**: Import from `tests.models`
3. **Use test utilities**: Leverage `TriggerTracker` and helper functions
4. **Add appropriate markers**: Use `@pytest.mark.unit` or `@pytest.mark.integration`
5. **Write descriptive docstrings**: Explain what each test is testing
6. **Test edge cases**: Include tests for error conditions and edge cases

## Test Configuration

The test suite uses:
- **pytest** as the test runner
- **pytest-django** for Django integration
- **pytest-cov** for coverage reporting
- **SQLite in-memory database** for fast test execution

Configuration is in `pytest.ini` and `tests/conftest.py`.
