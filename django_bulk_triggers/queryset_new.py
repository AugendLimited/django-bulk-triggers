"""
TriggerQuerySet - Clean service-based implementation.

This module provides a QuerySet with trigger support using composition
of service classes instead of mixin inheritance.
"""

import logging
from django.db import models, transaction

from django_bulk_triggers.operations import (
    BulkValidator,
    MTIHandler,
    FieldTracker,
    BulkExecutor,
    TriggerExecutor,
)

logger = logging.getLogger(__name__)


class TriggerQuerySet(models.QuerySet):
    """
    QuerySet with trigger support.
    
    This is a THIN COORDINATOR that delegates all logic to service classes.
    Services are created lazily and have explicit dependencies.
    
    No mixin inheritance - just clean single inheritance + composition.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._services = None
    
    def _get_services(self):
        """
        Lazy service initialization with explicit dependency graph.
        
        Returns:
            dict: Services keyed by name
        """
        if self._services is None:
            # Build services with explicit dependencies
            validator = BulkValidator(self.model)
            mti_handler = MTIHandler(self.model)
            field_tracker = FieldTracker(self.model)
            
            # Bulk executor depends on all other services
            bulk_executor = BulkExecutor(
                queryset=self,
                validator=validator,
                mti_handler=mti_handler,
                field_tracker=field_tracker,
            )
            
            # Trigger executor handles trigger lifecycle
            trigger_executor = TriggerExecutor(self.model)
            
            self._services = {
                'validator': validator,
                'mti': mti_handler,
                'tracker': field_tracker,
                'bulk': bulk_executor,
                'triggers': trigger_executor,
            }
        
        return self._services
    
    @transaction.atomic
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                   update_conflicts=False, update_fields=None, unique_fields=None,
                   bypass_triggers=False, bypass_validation=False):
        """
        Bulk create with triggers.
        
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
        
        services = self._get_services()
        
        # Execute create with trigger lifecycle
        return services['triggers'].execute_create_with_triggers(
            objs=objs,
            bulk_executor=services['bulk'],
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )
    
    @transaction.atomic
    def bulk_update(self, objs, fields, batch_size=None, bypass_triggers=False):
        """
        Bulk update with triggers.
        
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
        
        services = self._get_services()
        
        # Validate
        services['validator'].validate_for_update(objs)
        
        # Build update kwargs from fields
        update_kwargs = {field: None for field in fields}  # Placeholder
        
        # Get old records for comparison
        old_records_map = None
        if not bypass_triggers:
            old_records_map = services['bulk'].fetch_old_records(objs)
        
        # Execute with triggers
        from django_bulk_triggers.changeset import ChangeSet, RecordChange
        
        changes = [
            RecordChange(
                new_record=obj,
                old_record=old_records_map.get(obj.pk) if old_records_map else None,
                changed_fields=fields
            )
            for obj in objs
        ]
        
        changeset = ChangeSet(
            self.model,
            changes,
            'update',
            {'update_kwargs': update_kwargs, 'fields': fields}
        )
        
        # VALIDATE
        if not bypass_triggers:
            services['triggers'].dispatcher.dispatch(changeset, 'validate_update')
        
        # BEFORE
        if not bypass_triggers:
            services['triggers'].dispatcher.dispatch(changeset, 'before_update')
        
        # Execute
        result = services['bulk'].bulk_update(objs, fields, batch_size)
        
        # AFTER
        if not bypass_triggers:
            services['triggers'].dispatcher.dispatch(changeset, 'after_update')
        
        return result
    
    @transaction.atomic
    def update(self, **kwargs):
        """
        Update QuerySet with triggers.
        
        This method handles QuerySet updates (not bulk_update).
        """
        if not kwargs:
            return 0
        
        services = self._get_services()
        
        # Get FK fields for select_related optimization
        fk_fields = [
            field.name for field in self.model._meta.concrete_fields
            if field.is_relation and not field.many_to_many
        ]
        
        # Apply select_related to prevent N+1
        queryset = self
        if fk_fields:
            queryset = queryset.select_related(*fk_fields)
        
        # Get instances
        instances = list(queryset)
        if not instances:
            return 0
        
        # Execute update with triggers
        count = services['triggers'].execute_update_with_triggers(
            instances=instances,
            update_kwargs=kwargs,
            bulk_executor=services['bulk'],
            bypass_triggers=False,
        )
        
        # Execute the actual DB update
        return super().update(**kwargs)
    
    @transaction.atomic
    def delete(self):
        """
        Delete QuerySet with triggers.
        
        Returns:
            Tuple of (count, details dict)
        """
        services = self._get_services()
        
        # Get FK fields for select_related optimization
        fk_fields = [
            field.name for field in self.model._meta.concrete_fields
            if field.is_relation and not field.many_to_many
        ]
        
        # Apply select_related
        queryset = self
        if fk_fields:
            queryset = queryset.select_related(*fk_fields)
        
        # Get objects
        objs = list(queryset)
        if not objs:
            return 0, {}
        
        # Execute delete with triggers
        return services['triggers'].execute_delete_with_triggers(
            objs=objs,
            delete_operation=lambda: super(TriggerQuerySet, self).delete(),
            bypass_triggers=False,
        )


# Keep old name for backward compatibility
class TriggerQuerySetMixin(TriggerQuerySet):
    """
    DEPRECATED: Use TriggerQuerySet instead.
    
    This alias is kept for backward compatibility only.
    """
    pass

