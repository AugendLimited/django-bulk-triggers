"""
Bulk operation coordinator - Single entry point for all bulk operations.

This facade hides the complexity of wiring up multiple services and provides
a clean, simple API for the QuerySet to use.
"""

import logging
from django.db import transaction

logger = logging.getLogger(__name__)


class BulkOperationCoordinator:
    """
    Single entry point for coordinating bulk operations.
    
    This coordinator manages all services and provides a clean facade
    for the QuerySet. It hides the complexity of service wiring and
    coordination.
    
    Services are created lazily and cached.
    """
    
    def __init__(self, queryset):
        """
        Initialize coordinator for a queryset.
        
        Args:
            queryset: Django QuerySet instance
        """
        self.queryset = queryset
        self.model_cls = queryset.model
        
        # Lazy initialization
        self._analyzer = None
        self._mti_handler = None
        self._executor = None
        self._dispatcher = None
    
    @property
    def analyzer(self):
        """Get or create ModelAnalyzer"""
        if self._analyzer is None:
            from django_bulk_triggers.operations.analyzer import ModelAnalyzer
            self._analyzer = ModelAnalyzer(self.model_cls)
        return self._analyzer
    
    @property
    def mti_handler(self):
        """Get or create MTIHandler"""
        if self._mti_handler is None:
            from django_bulk_triggers.operations.mti_handler import MTIHandler
            self._mti_handler = MTIHandler(self.model_cls)
        return self._mti_handler
    
    @property
    def executor(self):
        """Get or create BulkExecutor"""
        if self._executor is None:
            from django_bulk_triggers.operations.bulk_executor import BulkExecutor
            self._executor = BulkExecutor(
                queryset=self.queryset,
                analyzer=self.analyzer,
                mti_handler=self.mti_handler,
            )
        return self._executor
    
    @property
    def dispatcher(self):
        """Get or create Dispatcher"""
        if self._dispatcher is None:
            from django_bulk_triggers.dispatcher import get_dispatcher
            self._dispatcher = get_dispatcher()
        return self._dispatcher
    
    @transaction.atomic
    def create(self, objs, batch_size=None, ignore_conflicts=False,
              update_conflicts=False, update_fields=None, unique_fields=None,
              bypass_triggers=False, bypass_validation=False):
        """
        Execute bulk create with triggers.
        
        This is the single entry point for all bulk create operations.
        It handles the entire lifecycle: validation, triggers, and execution.
        
        Args:
            objs: List of model instances to create
            batch_size: Number of objects per batch
            ignore_conflicts: Ignore conflicts if True
            update_conflicts: Update on conflict if True
            update_fields: Fields to update on conflict
            unique_fields: Fields to check for conflicts
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            List of created objects
        """
        if not objs:
            return objs
        
        from django_bulk_triggers.operations.strategies import BulkCreateStrategy
        
        strategy = BulkCreateStrategy(self.model_cls)
        
        return self._execute_with_lifecycle(
            strategy=strategy,
            objs=objs,
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )
    
    @transaction.atomic
    def update(self, objs, fields, batch_size=None, bypass_triggers=False):
        """
        Execute bulk update with triggers.
        
        Args:
            objs: List of model instances to update
            fields: List of field names to update
            batch_size: Number of objects per batch
            bypass_triggers: Skip all triggers if True
            
        Returns:
            Number of objects updated
        """
        if not objs:
            return 0
        
        from django_bulk_triggers.operations.strategies import BulkUpdateStrategy
        
        strategy = BulkUpdateStrategy(self.model_cls)
        
        return self._execute_with_lifecycle(
            strategy=strategy,
            objs=objs,
            fields=fields,
            batch_size=batch_size,
            bypass_triggers=bypass_triggers,
        )
    
    @transaction.atomic
    def update_queryset(self, update_kwargs, bypass_triggers=False):
        """
        Execute queryset update with triggers.
        
        Args:
            update_kwargs: Dict of fields to update
            bypass_triggers: Skip all triggers if True
            
        Returns:
            Number of objects updated
        """
        from django_bulk_triggers.operations.strategies import QuerySetUpdateStrategy
        
        strategy = QuerySetUpdateStrategy(self.model_cls)
        
        # Get instances
        instances = list(self.queryset)
        if not instances:
            return 0
        
        return self._execute_with_lifecycle(
            strategy=strategy,
            instances=instances,
            update_kwargs=update_kwargs,
            queryset=self.queryset,  # Pass queryset for actual update
            bypass_triggers=bypass_triggers,
        )
    
    @transaction.atomic
    def delete(self, bypass_triggers=False):
        """
        Execute delete with triggers.
        
        Args:
            bypass_triggers: Skip all triggers if True
            
        Returns:
            Tuple of (count, details dict)
        """
        from django_bulk_triggers.operations.strategies import DeleteStrategy
        
        strategy = DeleteStrategy(self.model_cls)
        
        # Get objects
        objs = list(self.queryset)
        if not objs:
            return 0, {}
        
        return self._execute_with_lifecycle(
            strategy=strategy,
            objs=objs,
            bypass_triggers=bypass_triggers,
        )
    
    def _execute_with_lifecycle(self, strategy, bypass_triggers=False, 
                                bypass_validation=False, **kwargs):
        """
        Execute operation with full trigger lifecycle.
        
        This is the core coordination logic that all operations use.
        
        Args:
            strategy: Operation strategy
            bypass_triggers: Skip all triggers
            bypass_validation: Skip validation triggers
            **kwargs: Operation-specific arguments
            
        Returns:
            Operation result
        """
        # Build changeset
        changeset = strategy.build_changeset(
            executor=self.executor,
            analyzer=self.analyzer,
            **kwargs
        )
        
        # Execute with lifecycle
        return self.dispatcher.execute_operation_with_triggers(
            changeset=changeset,
            operation=lambda: strategy.execute_operation(
                executor=self.executor,
                analyzer=self.analyzer,
                **kwargs
            ),
            event_prefix=strategy.event_prefix(),
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )

