"""
Additional tests for context module to increase coverage.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django_bulk_triggers.context import TriggerContext, get_trigger_queue


class TestContextCoverage(TestCase):
    """Test uncovered functionality in context module."""
    
    def test_get_trigger_queue_creates_new_queue(self):
        """Test get_trigger_queue creates new queue when none exists."""
        # Clear any existing queue
        from django_bulk_triggers.context import _trigger_context
        if hasattr(_trigger_context, 'queue'):
            delattr(_trigger_context, 'queue')
        
        queue = get_trigger_queue()
        self.assertIsNotNone(queue)
        
        # Second call should return the same queue
        queue2 = get_trigger_queue()
        self.assertIs(queue, queue2)
    

    def test_trigger_context_properties(self):
        """Test TriggerContext property methods."""
        # Mock the trigger_vars module
        mock_trigger_vars = Mock()
        mock_trigger_vars.event = 'BEFORE_CREATE'
        mock_trigger_vars.depth = 2
        
        with patch('django_bulk_triggers.context.trigger_vars', mock_trigger_vars):
            ctx = TriggerContext(Mock())
            
            # Test is_executing property
            self.assertTrue(ctx.is_executing)
            
            # Test current_event property
            self.assertEqual(ctx.current_event, 'BEFORE_CREATE')
            
            # Test execution_depth property
            self.assertEqual(ctx.execution_depth, 2)
    
    def test_trigger_context_properties_without_trigger_vars(self):
        """Test TriggerContext properties when trigger_vars attributes don't exist."""
        # Mock trigger_vars without the expected attributes
        mock_trigger_vars = Mock()
        del mock_trigger_vars.event
        del mock_trigger_vars.depth
        
        with patch('django_bulk_triggers.context.trigger_vars', mock_trigger_vars):
            ctx = TriggerContext(Mock())
            
            # Test is_executing property
            self.assertFalse(ctx.is_executing)
            
            # Test current_event property
            self.assertIsNone(ctx.current_event)
            
            # Test execution_depth property
            self.assertEqual(ctx.execution_depth, 0)
    
    def test_trigger_context_bypass_triggers_setting(self):
        """Test TriggerContext sets bypass_triggers in thread-local storage."""
        from django_bulk_triggers.context import get_bypass_triggers
        
        # Clear any existing bypass_triggers
        from django_bulk_triggers.context import _trigger_context
        if hasattr(_trigger_context, 'bypass_triggers'):
            delattr(_trigger_context, 'bypass_triggers')
        
        # Create context with bypass_triggers=True
        ctx = TriggerContext(Mock(), bypass_triggers=True)
        
        # Verify it was set in thread-local storage
        self.assertTrue(get_bypass_triggers())
        
        # Create context with bypass_triggers=False
        ctx2 = TriggerContext(Mock(), bypass_triggers=False)
        
        # Verify it was updated
        self.assertFalse(get_bypass_triggers())
    
    def test_trigger_context_model_assignment(self):
        """Test TriggerContext model assignment."""
        mock_model = Mock()
        ctx = TriggerContext(mock_model)
        
        self.assertEqual(ctx.model, mock_model)
    
    def test_trigger_context_bypass_triggers_assignment(self):
        """Test TriggerContext bypass_triggers assignment."""
        ctx = TriggerContext(Mock(), bypass_triggers=True)
        
        self.assertTrue(ctx.bypass_triggers)
        
        ctx2 = TriggerContext(Mock(), bypass_triggers=False)
        
        self.assertFalse(ctx2.bypass_triggers)
    
    def test_thread_local_storage_isolation(self):
        """Test that thread-local storage is isolated between contexts."""
        from django_bulk_triggers.context import _trigger_context
        
        # Clear any existing values
        if hasattr(_trigger_context, 'bypass_triggers'):
            delattr(_trigger_context, 'bypass_triggers')
        if hasattr(_trigger_context, 'bulk_update_value_map'):
            delattr(_trigger_context, 'bulk_update_value_map')
        
        # Test initial state
        from django_bulk_triggers.context import get_bypass_triggers, get_bulk_update_value_map
        
        self.assertFalse(get_bypass_triggers())
        self.assertIsNone(get_bulk_update_value_map())
        
        # Set values
        from django_bulk_triggers.context import set_bypass_triggers, set_bulk_update_value_map
        
        set_bypass_triggers(True)
        set_bulk_update_value_map({'test': 'value'})
        
        # Verify they were set
        self.assertTrue(get_bypass_triggers())
        self.assertEqual(get_bulk_update_value_map(), {'test': 'value'})
        
        # Clear values
        set_bypass_triggers(False)
        set_bulk_update_value_map(None)
        
        # Verify they were cleared
        self.assertFalse(get_bypass_triggers())
        self.assertIsNone(get_bulk_update_value_map())
