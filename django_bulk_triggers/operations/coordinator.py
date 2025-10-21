"""
Bulk operation coordinator - Single entry point for all bulk operations.

This facade hides the complexity of wiring up multiple services and provides
a clean, simple API for the QuerySet to use.
"""

import logging
from django.db import transaction
from django.db.models import QuerySet as BaseQuerySet

from django_bulk_triggers.helpers import (
    build_changeset_for_create,
    build_changeset_for_update,
    build_changeset_for_delete,
)

logger = logging.getLogger(__name__)


class BulkOperationCoordinator:
    """
    Single entry point for coordinating bulk operations.
    
    This coordinator manages all services and provides a clean facade
    for the QuerySet. It wires up services and coordinates the trigger
    lifecycle for each operation type.
    
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
    
    # ==================== PUBLIC API ====================
    
    @transaction.atomic
    def create(self, objs, batch_size=None, ignore_conflicts=False,
              update_conflicts=False, update_fields=None, unique_fields=None,
              bypass_triggers=False, bypass_validation=False):
        """
        Execute bulk create with triggers.
        
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
        
        # Validate
        self.analyzer.validate_for_create(objs)
        
        # Build initial changeset
        changeset = build_changeset_for_create(
            self.model_cls, 
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )
        
        # Execute with trigger lifecycle
        def operation():
            return self.executor.bulk_create(
                objs,
                batch_size=batch_size,
                ignore_conflicts=ignore_conflicts,
                update_conflicts=update_conflicts,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )
        
        return self.dispatcher.execute_operation_with_triggers(
            changeset=changeset,
            operation=operation,
            event_prefix='create',
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
    
    @transaction.atomic
    def update(self, objs, fields, batch_size=None, bypass_triggers=False, bypass_validation=False):
        """
        Execute bulk update with triggers.
        
        Args:
            objs: List of model instances to update
            fields: List of field names to update
            batch_size: Number of objects per batch
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            Number of objects updated
        """
        if not objs:
            return 0
        
        # Validate
        self.analyzer.validate_for_update(objs)
        
        # Fetch old records using analyzer (single source of truth)
        old_records_map = self.analyzer.fetch_old_records_map(objs)
        
        # Build changeset
        from django_bulk_triggers.changeset import ChangeSet, RecordChange
        changes = [
            RecordChange(
                new_record=obj,
                old_record=old_records_map.get(obj.pk),
                changed_fields=fields
            )
            for obj in objs
        ]
        changeset = ChangeSet(self.model_cls, changes, 'update', {'fields': fields})
        
        # Execute with trigger lifecycle
        def operation():
            return self.executor.bulk_update(objs, fields, batch_size=batch_size)
        
        return self.dispatcher.execute_operation_with_triggers(
            changeset=changeset,
            operation=operation,
            event_prefix='update',
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
    
    @transaction.atomic
    def update_queryset(self, update_kwargs, bypass_triggers=False, bypass_validation=False):
        """
        Execute queryset update with triggers.
        
        Args:
            update_kwargs: Dict of fields to update
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            Number of objects updated
        """
        # Get instances
        instances = list(self.queryset)
        if not instances:
            return 0
        
        # Fetch old records using analyzer (single source of truth)
        old_records_map = self.analyzer.fetch_old_records_map(instances)
        
        # Build changeset
        changeset = build_changeset_for_update(
            self.model_cls,
            instances,
            update_kwargs,
            old_records_map=old_records_map,
        )
        
        # Execute with trigger lifecycle
        def operation():
            # Call base Django QuerySet.update() to avoid recursion
            return BaseQuerySet.update(self.queryset, **update_kwargs)
        
        return self.dispatcher.execute_operation_with_triggers(
            changeset=changeset,
            operation=operation,
            event_prefix='update',
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
    
    @transaction.atomic
    def delete(self, bypass_triggers=False, bypass_validation=False):
        """
        Execute delete with triggers.
        
        Args:
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            Tuple of (count, details dict)
        """
        # Get objects
        objs = list(self.queryset)
        if not objs:
            return 0, {}
        
        # Validate
        self.analyzer.validate_for_delete(objs)
        
        # Build changeset
        changeset = build_changeset_for_delete(self.model_cls, objs)
        
        # Execute with trigger lifecycle
        def operation():
            # Call base Django QuerySet.delete() to avoid recursion
            return BaseQuerySet.delete(self.queryset)
        
        return self.dispatcher.execute_operation_with_triggers(
            changeset=changeset,
            operation=operation,
            event_prefix='delete',
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
