"""
Additional tests for context module to increase coverage.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django_bulk_hooks.context import HookContext, get_hook_queue


class TestContextCoverage(TestCase):
    """Test uncovered functionality in context module."""
    
    def test_get_hook_queue_creates_new_queue(self):
        """Test get_hook_queue creates new queue when none exists."""
        # Clear any existing queue
        from django_bulk_hooks.context import _hook_context
        if hasattr(_hook_context, 'queue'):
            delattr(_hook_context, 'queue')
        
        queue = get_hook_queue()
        self.assertIsNotNone(queue)
        
        # Second call should return the same queue
        queue2 = get_hook_queue()
        self.assertIs(queue, queue2)
    

    def test_hook_context_properties(self):
        """Test HookContext property methods."""
        # Mock the hook_vars module
        mock_hook_vars = Mock()
        mock_hook_vars.event = 'BEFORE_CREATE'
        mock_hook_vars.depth = 2
        
        with patch('django_bulk_hooks.context.hook_vars', mock_hook_vars):
            ctx = HookContext(Mock())
            
            # Test is_executing property
            self.assertTrue(ctx.is_executing)
            
            # Test current_event property
            self.assertEqual(ctx.current_event, 'BEFORE_CREATE')
            
            # Test execution_depth property
            self.assertEqual(ctx.execution_depth, 2)
    
    def test_hook_context_properties_without_hook_vars(self):
        """Test HookContext properties when hook_vars attributes don't exist."""
        # Mock hook_vars without the expected attributes
        mock_hook_vars = Mock()
        del mock_hook_vars.event
        del mock_hook_vars.depth
        
        with patch('django_bulk_hooks.context.hook_vars', mock_hook_vars):
            ctx = HookContext(Mock())
            
            # Test is_executing property
            self.assertFalse(ctx.is_executing)
            
            # Test current_event property
            self.assertIsNone(ctx.current_event)
            
            # Test execution_depth property
            self.assertEqual(ctx.execution_depth, 0)
    
    def test_hook_context_bypass_hooks_setting(self):
        """Test HookContext sets bypass_hooks in thread-local storage."""
        from django_bulk_hooks.context import get_bypass_hooks
        
        # Clear any existing bypass_hooks
        from django_bulk_hooks.context import _hook_context
        if hasattr(_hook_context, 'bypass_hooks'):
            delattr(_hook_context, 'bypass_hooks')
        
        # Create context with bypass_hooks=True
        ctx = HookContext(Mock(), bypass_hooks=True)
        
        # Verify it was set in thread-local storage
        self.assertTrue(get_bypass_hooks())
        
        # Create context with bypass_hooks=False
        ctx2 = HookContext(Mock(), bypass_hooks=False)
        
        # Verify it was updated
        self.assertFalse(get_bypass_hooks())
    
    def test_hook_context_model_assignment(self):
        """Test HookContext model assignment."""
        mock_model = Mock()
        ctx = HookContext(mock_model)
        
        self.assertEqual(ctx.model, mock_model)
    
    def test_hook_context_bypass_hooks_assignment(self):
        """Test HookContext bypass_hooks assignment."""
        ctx = HookContext(Mock(), bypass_hooks=True)
        
        self.assertTrue(ctx.bypass_hooks)
        
        ctx2 = HookContext(Mock(), bypass_hooks=False)
        
        self.assertFalse(ctx2.bypass_hooks)
    
    def test_thread_local_storage_isolation(self):
        """Test that thread-local storage is isolated between contexts."""
        from django_bulk_hooks.context import _hook_context
        
        # Clear any existing values
        if hasattr(_hook_context, 'bypass_hooks'):
            delattr(_hook_context, 'bypass_hooks')
        if hasattr(_hook_context, 'bulk_update_value_map'):
            delattr(_hook_context, 'bulk_update_value_map')
        
        # Test initial state
        from django_bulk_hooks.context import get_bypass_hooks, get_bulk_update_value_map
        
        self.assertFalse(get_bypass_hooks())
        self.assertIsNone(get_bulk_update_value_map())
        
        # Set values
        from django_bulk_hooks.context import set_bypass_hooks, set_bulk_update_value_map
        
        set_bypass_hooks(True)
        set_bulk_update_value_map({'test': 'value'})
        
        # Verify they were set
        self.assertTrue(get_bypass_hooks())
        self.assertEqual(get_bulk_update_value_map(), {'test': 'value'})
        
        # Clear values
        set_bypass_hooks(False)
        set_bulk_update_value_map(None)
        
        # Verify they were cleared
        self.assertFalse(get_bypass_hooks())
        self.assertIsNone(get_bulk_update_value_map())
