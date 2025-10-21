"""
TriggerQuerySet - Django QuerySet with trigger support.

This is a thin coordinator that delegates all complex logic to services.
It follows the Facade pattern, providing a simple interface over the
complex coordination required for bulk operations with triggers.
"""

import logging
from django.db import models, transaction

logger = logging.getLogger(__name__)


class TriggerQuerySet(models.QuerySet):
    """
    QuerySet with trigger support.
    
    This is a thin facade over BulkOperationCoordinator. It provides
    backward-compatible API for Django's QuerySet while integrating
    the full trigger lifecycle.
    
    Key design principles:
    - Minimal logic (< 10 lines per method)
    - No business logic (delegate to coordinator)
    - No conditionals (let services handle it)
    - Transaction boundaries only
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._coordinator = None
    
    @property
    def coordinator(self):
        """Lazy initialization of coordinator"""
        if self._coordinator is None:
            from django_bulk_triggers.operations import BulkOperationCoordinator
            self._coordinator = BulkOperationCoordinator(self)
        return self._coordinator
    
    @transaction.atomic
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                    update_conflicts=False, update_fields=None, unique_fields=None,
                    bypass_triggers=False, bypass_validation=False):
        """
        Create multiple objects with trigger support.
        
        This is the public API - delegates to coordinator.
        """
        return self.coordinator.create(
            objs=objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
    
    @transaction.atomic
    def bulk_update(self, objs, fields=None, batch_size=None, bypass_triggers=False, bypass_validation=False, **kwargs):
        """
        Update multiple objects with trigger support.
        
        This is the public API - delegates to coordinator.
        
        Args:
            objs: List of model instances to update
            fields: List of field names to update (optional, will auto-detect if None)
            batch_size: Number of objects per batch
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            Number of objects updated
        """
        # If fields is None, auto-detect changed fields by comparing with database
        if fields is None:
            fields = self._detect_changed_fields(objs)
            if not fields:
                # No fields changed, nothing to update
                logger.debug(f"bulk_update: No fields changed for {len(objs)} {self.model.__name__} objects")
                return 0
        
        return self.coordinator.update(
            objs=objs,
            fields=fields,
            batch_size=batch_size,
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
    
    @transaction.atomic
    def update(self, bypass_triggers=False, bypass_validation=False, **kwargs):
        """
        Update QuerySet with trigger support.
        
        This is the public API - delegates to coordinator.
        
        Args:
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            **kwargs: Fields to update
            
        Returns:
            Number of objects updated
        """
        return self.coordinator.update_queryset(
            update_kwargs=kwargs,
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
    
    @transaction.atomic
    def bulk_delete(self, objs, bypass_triggers=False, bypass_validation=False, **kwargs):
        """
        Delete multiple objects with trigger support.
        
        This is the public API - delegates to coordinator.
        
        Args:
            objs: List of objects to delete
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            Tuple of (count, details dict)
        """
        # Filter queryset to only these objects
        pks = [obj.pk for obj in objs if obj.pk is not None]
        if not pks:
            return 0
        
        # Create a filtered queryset
        filtered_qs = self.filter(pk__in=pks)
        
        # Use coordinator with the filtered queryset
        from django_bulk_triggers.operations import BulkOperationCoordinator
        coordinator = BulkOperationCoordinator(filtered_qs)
        
        count, details = coordinator.delete(
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
        
        # For bulk_delete, return just the count to match Django's behavior
        return count
    
    @transaction.atomic
    def delete(self, bypass_triggers=False, bypass_validation=False):
        """
        Delete QuerySet with trigger support.
        
        This is the public API - delegates to coordinator.
        
        Args:
            bypass_triggers: Skip all triggers if True
            bypass_validation: Skip validation triggers if True
            
        Returns:
            Tuple of (count, details dict)
        """
        return self.coordinator.delete(
            bypass_triggers=bypass_triggers,
            bypass_validation=bypass_validation,
        )
    
    def _detect_changed_fields(self, objs):
        """
        Detect which fields have changed across a set of objects.
        
        This method fetches old records from the database in a SINGLE bulk query
        and compares them with the new objects to determine changed fields.
        
        PERFORMANCE: Uses bulk query (O(1) queries) not N queries.
        
        Args:
            objs: List of model instances to check
            
        Returns:
            List of field names that changed across any object
        """
        if not objs:
            return []
        
        # Get PKs for bulk fetch
        pks = [obj.pk for obj in objs if obj.pk is not None]
        if not pks:
            return []
        
        # Fetch old records in SINGLE query (bulk operation)
        old_records_map = {
            old_obj.pk: old_obj 
            for old_obj in self.model._base_manager.filter(pk__in=pks)
        }
        
        # Track which fields changed across ALL objects
        changed_fields_set = set()
        
        # Compare each object with its database state
        for obj in objs:
            if obj.pk is None:
                continue
            
            old_obj = old_records_map.get(obj.pk)
            if old_obj is None:
                # Object doesn't exist in DB, skip
                continue
            
            # Check each field for changes
            for field in self.model._meta.fields:
                # Skip primary key and auto fields
                if field.primary_key or field.auto_created:
                    continue
                
                old_val = getattr(old_obj, field.name, None)
                new_val = getattr(obj, field.name, None)
                
                # Use field's get_prep_value for proper comparison
                try:
                    old_prep = field.get_prep_value(old_val)
                    new_prep = field.get_prep_value(new_val)
                    if old_prep != new_prep:
                        changed_fields_set.add(field.name)
                except (TypeError, ValueError):
                    # Fallback to direct comparison
                    if old_val != new_val:
                        changed_fields_set.add(field.name)
        
        # Return as sorted list for deterministic behavior
        return sorted(changed_fields_set)