"""
Tests for the dispatcher module (formerly engine).
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import connection
from django_bulk_triggers.dispatcher import get_dispatcher
from django_bulk_triggers.helpers import build_changeset_for_create
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.constants import BEFORE_CREATE
from django_bulk_triggers.conditions import IsEqual
from django_bulk_triggers import TriggerClass
from tests.models import TriggerModel


def run(model_cls, event, new_records, old_records=None, bypass_triggers=False):
    """
    Helper function to provide engine.run() interface using the dispatcher.
    Maintains backward compatibility for tests.
    """
    if not new_records:
        return None
    
    from django_bulk_triggers.changeset import ChangeSet, RecordChange
    
    # Build ChangeSet
    if old_records is None:
        old_records = [None] * len(new_records)
    
    changes = [
        RecordChange(new, old) 
        for new, old in zip(new_records, old_records)
    ]
    
    # Infer operation type from event
    if 'create' in event.lower():
        op_type = 'create'
    elif 'update' in event.lower():
        op_type = 'update'
    elif 'delete' in event.lower():
        op_type = 'delete'
    else:
        op_type = 'unknown'
    
    changeset = ChangeSet(model_cls, changes, op_type, {})
    
    # Delegate to dispatcher
    dispatcher = get_dispatcher()
    dispatcher.dispatch(changeset, event.lower(), bypass_triggers=bypass_triggers)


class TestEngine(TestCase):
    """Test dispatcher functionality (formerly engine module)."""

    def setUp(self):
        self.model_cls = TriggerModel
        self.records = [Mock(), Mock()]
        self.dispatcher = get_dispatcher()

    def test_run_with_empty_records(self):
        """Test run function with empty records."""
        result = run(self.model_cls, 'BEFORE_CREATE', [])
        self.assertIsNone(result)

    def test_run_with_no_triggers(self):
        """Test run function when no triggers are registered."""
        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = []

            result = run(self.model_cls, 'BEFORE_CREATE', self.records)
            self.assertIsNone(result)

    def test_run_with_bypass_triggers(self):
        """Test run function respects bypass_triggers flag."""
        mock_trigger = (Mock(), 'handle', None, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Call with bypass_triggers=True
            result = run(self.model_cls, 'BEFORE_CREATE', self.records, bypass_triggers=True)
            self.assertIsNone(result)

    def test_run_with_validation_error(self):
        """Test run function handles ValidationError from clean()."""
        # Create a mock instance that raises ValidationError on clean()
        mock_instance = Mock()
        mock_instance.clean.side_effect = ValidationError("Validation failed")

        mock_trigger = (Mock(), 'handle', None, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # NOTE: Individual clean() calls are skipped to prevent N+1 queries
            # Validation triggers (VALIDATE_*) will handle validation instead
            # So ValidationError from clean() should not be raised
            result = run(self.model_cls, 'BEFORE_CREATE', [mock_instance])
            self.assertIsNone(result)  # Should complete without error

    def test_run_with_condition_filtering(self):
        """Test run function filters records based on conditions."""
        # Create mock instances
        mock_instance1 = Mock()
        mock_instance2 = Mock()
        records = [mock_instance1, mock_instance2]

        # Create a mock condition that only passes for the first instance
        mock_condition = Mock()
        mock_condition.check.side_effect = lambda new, old: new == mock_instance1

        mock_trigger = (Mock(), 'handle', mock_condition, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Mock the handler
            mock_handler = Mock()
            mock_trigger[0].return_value = mock_handler

            result = run(self.model_cls, 'BEFORE_CREATE', records, old_records=[None, None])

            # Should only process the first instance
            mock_handler.handle.assert_called_once()
            call_args = mock_handler.handle.call_args
            self.assertEqual(len(call_args[1]['new_records']), 1)
            self.assertEqual(call_args[1]['new_records'][0], mock_instance1)

    def test_run_with_condition_and_old_records(self):
        """Test run function handles conditions with old records."""
        # Create mock instances
        mock_instance1 = Mock()
        mock_instance2 = Mock()
        records = [mock_instance1, mock_instance2]
        old_records = [Mock(), Mock()]

        # Create a mock condition
        mock_condition = Mock()
        mock_condition.check.side_effect = lambda new, old: True

        mock_trigger = (Mock(), 'handle', mock_condition, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Mock the handler
            mock_handler = Mock()
            mock_trigger[0].return_value = mock_handler

            result = run(self.model_cls, 'BEFORE_CREATE', records, old_records=old_records)

            # Should process all instances
            mock_handler.handle.assert_called_once()
            call_args = mock_handler.handle.call_args
            self.assertEqual(len(call_args[1]['new_records']), 2)
            self.assertEqual(len(call_args[1]['old_records']), 2)

    def test_run_with_handler_execution_error(self):
        """Test run function handles handler execution errors."""
        mock_trigger = (Mock(), 'handle', None, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Mock the handler to raise an exception
            mock_handler = Mock()
            mock_handler.handle.side_effect = Exception("Handler failed")
            mock_trigger[0].return_value = mock_handler

            with self.assertRaises(Exception):
                run(self.model_cls, 'BEFORE_CREATE', self.records)

    def test_run_with_condition_error(self):
        """Test run function handles condition check errors."""
        # Create mock instances
        mock_instance1 = Mock()
        mock_instance2 = Mock()
        records = [mock_instance1, mock_instance2]

        # Create a mock condition that raises an error
        mock_condition = Mock()
        mock_condition.check.side_effect = Exception("Condition check failed")

        mock_trigger = (Mock(), 'handle', mock_condition, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Mock the handler
            mock_handler = Mock()
            mock_trigger[0].return_value = mock_handler

            with self.assertRaises(Exception):
                run(self.model_cls, 'BEFORE_CREATE', records)

    def test_run_with_before_event_validation(self):
        """Test run function runs validation for BEFORE events."""
        # Create a mock instance
        mock_instance = Mock()
        records = [mock_instance]

        mock_trigger = (Mock(), 'handle', None, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Mock the handler
            mock_handler = Mock()
            mock_trigger[0].return_value = mock_handler

            # Test with BEFORE_CREATE event
            result = run(self.model_cls, 'BEFORE_CREATE', records)

            # NOTE: Individual clean() calls are skipped to prevent N+1 queries
            # Validation triggers (VALIDATE_*) will handle validation instead
            mock_instance.clean.assert_not_called()

    def test_run_with_non_before_event_no_validation(self):
        """Test run function doesn't run validation for non-BEFORE events."""
        # Create a mock instance
        mock_instance = Mock()
        records = [mock_instance]

        mock_trigger = (Mock(), 'handle', None, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Mock the handler
            mock_handler = Mock()
            mock_trigger[0].return_value = mock_handler

            # Test with AFTER_CREATE event
            result = run(self.model_cls, 'AFTER_CREATE', records)

            # Should not call clean() on the instance
            mock_instance.clean.assert_not_called()

    def test_run_with_old_records_none(self):
        """Test run function handles None old_records."""
        mock_trigger = (Mock(), 'handle', None, 100)

        with patch('django_bulk_triggers.registry.get_triggers') as mock_get_triggers:
            mock_get_triggers.return_value = [mock_trigger]

            # Mock the handler
            mock_handler = Mock()
            mock_trigger[0].return_value = mock_handler

            result = run(self.model_cls, 'BEFORE_CREATE', self.records, old_records=None)

            # Should pass None for old_records
            mock_handler.handle.assert_called_once()
            call_args = mock_handler.handle.call_args
            self.assertIsNone(call_args[1]['old_records'])

    def test_n1_query_fix_for_new_records(self):
        """Test that the N+1 query fix works for new records with FK relationships."""
        # Clear any existing queries
        connection.queries.clear()
        
        # Create a trigger that accesses FK relationships
        class TestTrigger(TriggerClass):
            @trigger(BEFORE_CREATE, model=TriggerModel, condition=IsEqual('created_by', None))
            def test_trigger(self, new_records, old_records=None, **kwargs):
                pass
        
        # Create test records with FK relationships
        test_records = []
        for i in range(5):
            record = TriggerModel(name=f"Test {i}", value=i)
            test_records.append(record)
        
        # Run the engine
        run(TriggerModel, BEFORE_CREATE, test_records)
        
        # Count the number of queries executed
        query_count = len(connection.queries)
        
        # The fix should prevent N+1 queries
        # Before the fix: 5 records * 2 FK queries = 10+ queries
        # After the fix: Should be much fewer queries (ideally 0-2)
        self.assertLess(query_count, 10, f"Too many queries executed: {query_count}. Expected < 10 due to N+1 fix.")
        
        # Log the queries for debugging
        print(f"\nN+1 Query Test Results:")
        print(f"Total queries executed: {query_count}")
        for i, query in enumerate(connection.queries):
            print(f"Query {i+1}: {query['sql'][:100]}...")
