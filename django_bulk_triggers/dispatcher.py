"""
TriggerDispatcher: Single execution path for all triggers.

Provides deterministic, priority-ordered trigger execution with reentrancy
detection, similar to Salesforce's trigger framework.
"""
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RecursionGuard:
    """
    Thread-safe recursion detection for triggers.
    
    Prevents infinite loops by tracking:
    1. Call stack (detects cycles like A:AFTER → B:BEFORE → A:AFTER)
    2. Depth per (model, event) pair (prevents deep recursion)
    
    Similar to Salesforce's trigger recursion limits.
    """
    
    _thread_local = threading.local()
    MAX_DEPTH_PER_EVENT = 10
    
    @classmethod
    def enter(cls, model_cls, event):
        """
        Track entering a dispatch context with cycle detection.
        
        Args:
            model_cls: The Django model class
            event: The event name (e.g., 'after_update')
            
        Returns:
            Current depth for this (model, event) pair
            
        Raises:
            RuntimeError: If a cycle is detected or max depth exceeded
        """
        if not hasattr(cls._thread_local, 'stack'):
            cls._thread_local.stack = []
        if not hasattr(cls._thread_local, 'depth'):
            cls._thread_local.depth = {}
        
        key = (model_cls, event)
        
        # Check for cycles in the call stack
        if key in cls._thread_local.stack:
            cycle_path = ' → '.join(
                f"{m.__name__}:{e}" for m, e in cls._thread_local.stack
            )
            cycle_path += f" → {model_cls.__name__}:{event}"
            raise RuntimeError(
                f"Trigger recursion cycle detected: {cycle_path}. "
                f"This indicates an infinite loop in your trigger chain."
            )
        
        # Check depth threshold
        cls._thread_local.depth[key] = cls._thread_local.depth.get(key, 0) + 1
        depth = cls._thread_local.depth[key]
        
        if depth > cls.MAX_DEPTH_PER_EVENT:
            raise RuntimeError(
                f"Maximum trigger depth ({cls.MAX_DEPTH_PER_EVENT}) exceeded "
                f"for {model_cls.__name__}.{event}. "
                f"This likely indicates infinite recursion in your triggers."
            )
        
        # Add to call stack
        cls._thread_local.stack.append(key)
        
        return depth
    
    @classmethod
    def exit(cls, model_cls, event):
        """
        Track exiting a dispatch context.
        
        Args:
            model_cls: The Django model class
            event: The event name
        """
        key = (model_cls, event)
        
        # Remove from call stack
        if hasattr(cls._thread_local, 'stack') and cls._thread_local.stack:
            if cls._thread_local.stack[-1] == key:
                cls._thread_local.stack.pop()
        
        # Decrement depth
        if hasattr(cls._thread_local, 'depth') and key in cls._thread_local.depth:
            cls._thread_local.depth[key] -= 1
    
    @classmethod
    def get_current_depth(cls, model_cls, event):
        """
        Get current recursion depth for a (model, event) pair.
        
        Args:
            model_cls: The Django model class
            event: The event name
            
        Returns:
            Current depth (0 if not in any dispatch)
        """
        if not hasattr(cls._thread_local, 'depth'):
            return 0
        key = (model_cls, event)
        return cls._thread_local.depth.get(key, 0)
    
    @classmethod
    def get_call_stack(cls):
        """
        Get current call stack for debugging.
        
        Returns:
            List of (model_cls, event) tuples in call order
        """
        if not hasattr(cls._thread_local, 'stack'):
            return []
        return list(cls._thread_local.stack)


class TriggerDispatcher:
    """
    Single execution path for all triggers.
    
    Responsibilities:
    - Execute triggers in priority order
    - Detect and prevent infinite recursion
    - Filter records based on conditions
    - Provide ChangeSet context to triggers
    - Fail-fast error propagation
    - Manage complete operation lifecycle (VALIDATE, BEFORE, AFTER)
    """
    
    def __init__(self, registry):
        """
        Initialize the dispatcher.
        
        Args:
            registry: The trigger registry (provides get_triggers method)
        """
        self.registry = registry
        self.guard = RecursionGuard()
    
    def execute_operation_with_triggers(self, changeset, operation, event_prefix,
                                       bypass_triggers=False, bypass_validation=False):
        """
        Execute operation with full trigger lifecycle.
        
        This is the high-level method that coordinates the complete lifecycle:
        1. VALIDATE_{event}
        2. BEFORE_{event}
        3. Actual operation
        4. AFTER_{event}
        
        Args:
            changeset: ChangeSet for the operation
            operation: Callable that performs the actual DB operation
            event_prefix: 'create', 'update', or 'delete'
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            Result of operation
        """
        if bypass_triggers:
            return operation()
        
        # VALIDATE phase
        if not bypass_validation:
            self.dispatch(changeset, f'validate_{event_prefix}', bypass_triggers=False)
        
        # BEFORE phase
        self.dispatch(changeset, f'before_{event_prefix}', bypass_triggers=False)
        
        # Execute the actual operation
        result = operation()
        
        # AFTER phase - use result if operation returns modified data
        if result and isinstance(result, list) and event_prefix == 'create':
            # For create, rebuild changeset with assigned PKs
            from django_bulk_triggers.helpers import build_changeset_for_create
            changeset = build_changeset_for_create(changeset.model_cls, result)
        
        self.dispatch(changeset, f'after_{event_prefix}', bypass_triggers=False)
        
        return result
    
    def dispatch(self, changeset, event, bypass_triggers=False):
        """
        Dispatch triggers for a changeset with deterministic ordering.
        
        This is the single execution path for ALL triggers in the system.
        
        Args:
            changeset: ChangeSet instance with record changes
            event: Event name (e.g., 'after_update', 'before_create')
            bypass_triggers: If True, skip all trigger execution
            
        Raises:
            RuntimeError: If recursion cycle detected or max depth exceeded
            Exception: Any exception raised by a trigger (fails fast)
        """
        if bypass_triggers:
            return
        
        # Get triggers sorted by priority (deterministic order)
        triggers = self.registry.get_triggers(changeset.model_cls, event)
        
        if not triggers:
            return
        
        # Track recursion depth and expose to triggers
        depth = self.guard.enter(changeset.model_cls, event)
        call_stack = self.guard.get_call_stack()
        
        # Augment changeset metadata with recursion information
        changeset.operation_meta['recursion_depth'] = depth
        changeset.operation_meta['call_stack'] = call_stack
        
        try:
            # Execute triggers in priority order
            for handler_cls, method_name, condition, priority in triggers:
                self._execute_trigger(handler_cls, method_name, condition, changeset)
        finally:
            self.guard.exit(changeset.model_cls, event)
    
    def _execute_trigger(self, handler_cls, method_name, condition, changeset):
        """
        Execute a single trigger with condition checking.
        
        Args:
            handler_cls: The trigger handler class
            method_name: Name of the method to call
            condition: Optional condition to filter records
            changeset: ChangeSet with all record changes
        """
        # Filter records based on condition
        if condition:
            filtered_changes = [
                change for change in changeset.changes
                if condition.check(change.new_record, change.old_record)
            ]
            
            if not filtered_changes:
                # No records match condition, skip this trigger
                return
            
            # Create filtered changeset
            from django_bulk_triggers.changeset import ChangeSet
            filtered_changeset = ChangeSet(
                changeset.model_cls,
                filtered_changes,
                changeset.operation_type,
                changeset.operation_meta
            )
        else:
            # No condition, use full changeset
            filtered_changeset = changeset
        
        # Use DI factory to create handler instance
        from django_bulk_triggers.factory import create_trigger_instance
        handler = create_trigger_instance(handler_cls)
        method = getattr(handler, method_name)
        
        # Check if method has @select_related decorator
        preload_func = getattr(method, '_select_related_preload', None)
        if preload_func:
            # Preload relationships to prevent N+1 queries
            try:
                model_cls_override = getattr(handler, 'model_cls', None)
                
                # Preload for new_records
                if filtered_changeset.new_records:
                    logger.debug(
                        f"Preloading relationships for {len(filtered_changeset.new_records)} "
                        f"new_records for {handler_cls.__name__}.{method_name}"
                    )
                    preload_func(filtered_changeset.new_records, model_cls=model_cls_override)
                
                # Also preload for old_records (for conditions that check previous values)
                if filtered_changeset.old_records:
                    logger.debug(
                        f"Preloading relationships for {len(filtered_changeset.old_records)} "
                        f"old_records for {handler_cls.__name__}.{method_name}"
                    )
                    preload_func(filtered_changeset.old_records, model_cls=model_cls_override)
            except Exception:
                logger.debug(
                    "select_related preload failed for %s.%s",
                    handler_cls.__name__,
                    method_name,
                    exc_info=True,
                )
        
        # Execute trigger with ChangeSet
        # Pass both changeset and backward-compatible new_records/old_records
        try:
            method(
                changeset=filtered_changeset,
                new_records=filtered_changeset.new_records,
                old_records=filtered_changeset.old_records,
            )
        except Exception as e:
            # Fail-fast: re-raise to rollback transaction
            logger.error(
                f"Trigger {handler_cls.__name__}.{method_name} failed: {e}",
                exc_info=True
            )
            raise


# Global dispatcher instance
_dispatcher: Optional[TriggerDispatcher] = None


def get_dispatcher():
    """
    Get the global dispatcher instance.
    
    Creates the dispatcher on first access (singleton pattern).
    
    Returns:
        TriggerDispatcher instance
    """
    global _dispatcher
    if _dispatcher is None:
        # Import here to avoid circular dependency
        from django_bulk_triggers import registry
        
        # Create dispatcher with a registry wrapper that has get_triggers method
        class RegistryWrapper:
            @staticmethod
            def get_triggers(model, event):
                return registry.get_triggers(model, event)
        
        _dispatcher = TriggerDispatcher(RegistryWrapper())
    return _dispatcher

