"""
Operation strategies for bulk operations.

Each strategy encapsulates the logic for a specific operation type
(create, update, delete) following the Strategy pattern.
"""

import logging
from django_bulk_triggers.helpers import (
    build_changeset_for_create,
    build_changeset_for_update,
    build_changeset_for_delete,
)

logger = logging.getLogger(__name__)


class OperationStrategy:
    """Base class for operation strategies"""
    
    def __init__(self, model_cls):
        self.model_cls = model_cls
    
    def event_prefix(self):
        """Return the event prefix for this operation ('create', 'update', 'delete')"""
        raise NotImplementedError
    
    def build_changeset(self, **kwargs):
        """Build ChangeSet for this operation"""
        raise NotImplementedError
    
    def execute_operation(self, executor, **kwargs):
        """Execute the actual DB operation"""
        raise NotImplementedError


class BulkCreateStrategy(OperationStrategy):
    """Strategy for bulk_create operations"""
    
    def event_prefix(self):
        return 'create'
    
    def build_changeset(self, objs, executor=None, analyzer=None, **kwargs):
        """Build changeset for bulk create"""
        return build_changeset_for_create(
            self.model_cls,
            objs,
            **{k: v for k, v in kwargs.items() if k not in ['executor', 'analyzer', 'objs']}
        )
    
    def execute_operation(self, executor, objs, batch_size=None, ignore_conflicts=False,
                         update_conflicts=False, update_fields=None, unique_fields=None,
                         analyzer=None, **kwargs):
        """Execute bulk create"""
        # Validate
        if analyzer:
            analyzer.validate_for_create(objs)
        
        # Execute
        return executor.bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


class BulkUpdateStrategy(OperationStrategy):
    """Strategy for bulk_update operations"""
    
    def event_prefix(self):
        return 'update'
    
    def build_changeset(self, objs, fields, executor=None, analyzer=None, **kwargs):
        """Build changeset for bulk update"""
        # Fetch old records
        old_records_map = executor.fetch_old_records(objs) if executor else {}
        
        # Build ChangeSet
        from django_bulk_triggers.changeset import ChangeSet, RecordChange
        
        changes = [
            RecordChange(
                new_record=obj,
                old_record=old_records_map.get(obj.pk),
                changed_fields=fields
            )
            for obj in objs
        ]
        
        return ChangeSet(
            self.model_cls,
            changes,
            'update',
            {'fields': fields}
        )
    
    def execute_operation(self, executor, objs, fields, batch_size=None, analyzer=None, **kwargs):
        """Execute bulk update"""
        # Validate
        if analyzer:
            analyzer.validate_for_update(objs)
        
        # Execute
        return executor.bulk_update(objs, fields, batch_size=batch_size)


class QuerySetUpdateStrategy(OperationStrategy):
    """Strategy for QuerySet.update() operations"""
    
    def event_prefix(self):
        return 'update'
    
    def build_changeset(self, instances, update_kwargs, executor=None, analyzer=None, **kwargs):
        """Build changeset for queryset update"""
        return build_changeset_for_update(
            self.model_cls,
            instances,
            update_kwargs,
            **{k: v for k, v in kwargs.items() if k not in ['executor', 'analyzer', 'instances', 'update_kwargs']}
        )
    
    def execute_operation(self, executor, instances, update_kwargs, queryset=None, analyzer=None, **kwargs):
        """Execute queryset update"""
        # Execute the actual Django update on the queryset
        # We need to call the base Django QuerySet.update() to avoid recursion
        from django.db.models import QuerySet as BaseQuerySet
        
        if queryset is None:
            raise ValueError("QuerySetUpdateStrategy requires 'queryset' parameter")
        
        # Call the base Django update method directly to avoid recursion
        return BaseQuerySet.update(queryset, **update_kwargs)


class DeleteStrategy(OperationStrategy):
    """Strategy for delete operations"""
    
    def event_prefix(self):
        return 'delete'
    
    def build_changeset(self, objs, executor=None, analyzer=None, **kwargs):
        """Build changeset for delete"""
        return build_changeset_for_delete(
            self.model_cls,
            objs,
            **{k: v for k, v in kwargs.items() if k not in ['executor', 'analyzer', 'objs']}
        )
    
    def execute_operation(self, executor, objs, analyzer=None, **kwargs):
        """Execute delete"""
        # Validate
        if analyzer:
            analyzer.validate_for_delete(objs)
        
        # Execute via queryset
        return executor.delete_queryset()

