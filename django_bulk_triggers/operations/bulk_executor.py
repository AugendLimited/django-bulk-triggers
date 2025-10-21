"""
Bulk executor service for database operations.

This service coordinates bulk database operations with validation and MTI handling.
"""

import logging
from django.db import transaction

logger = logging.getLogger(__name__)


class BulkExecutor:
    """
    Executes bulk database operations.
    
    This service coordinates validation, MTI handling, and actual database
    operations. It's the only service that directly calls Django ORM methods.
    
    Dependencies are explicitly injected via constructor.
    """
    
    def __init__(self, queryset, analyzer, mti_handler):
        """
        Initialize bulk executor with explicit dependencies.
        
        Args:
            queryset: Django QuerySet instance
            analyzer: ModelAnalyzer instance (replaces validator + field_tracker)
            mti_handler: MTIHandler instance
        """
        self.queryset = queryset
        self.analyzer = analyzer
        self.mti_handler = mti_handler
        self.model_cls = queryset.model
    
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, 
                   update_conflicts=False, update_fields=None, 
                   unique_fields=None, **kwargs):
        """
        Execute bulk create operation.
        
        Args:
            objs: List of model instances to create
            batch_size: Number of objects to create per batch
            ignore_conflicts: Whether to ignore conflicts
            update_conflicts: Whether to update on conflict
            update_fields: Fields to update on conflict
            unique_fields: Fields to use for conflict detection
            **kwargs: Additional arguments
            
        Returns:
            List of created objects
        """
        if not objs:
            return objs
        
        # Validate input
        self.analyzer.validate_for_create(objs)
        
        # Check for MTI - if MTI, we need special handling
        if self.mti_handler.is_mti_model():
            # MTI bulk create - handled by MTIHandler service
            logger.debug("MTI bulk_create delegating to MTIHandler")
        
        # Standard bulk create
        return self._execute_bulk_create(objs, batch_size, ignore_conflicts, 
                                        update_conflicts, update_fields, 
                                        unique_fields, **kwargs)
    
    def _execute_bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                            update_conflicts=False, update_fields=None,
                            unique_fields=None, **kwargs):
        """
        Execute the actual Django bulk_create.
        
        This is the only method that directly calls Django ORM.
        We must call the base Django QuerySet to avoid recursion.
        """
        from django.db.models import QuerySet
        
        # Create a base Django queryset (not our TriggerQuerySet)
        base_qs = QuerySet(model=self.model_cls, using=self.queryset.db)
        
        return base_qs.bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )
    
    def bulk_update(self, objs, fields, batch_size=None):
        """
        Execute bulk update operation.
        
        Args:
            objs: List of model instances to update
            fields: List of field names to update
            batch_size: Number of objects to update per batch
            
        Returns:
            Number of objects updated
        """
        if not objs:
            return 0
        
        # Validate input
        self.analyzer.validate_for_update(objs)
        
        # Execute bulk update - use base Django QuerySet to avoid recursion
        from django.db.models import QuerySet
        base_qs = QuerySet(model=self.model_cls, using=self.queryset.db)
        return base_qs.bulk_update(objs, fields, batch_size=batch_size)
    
    def delete_queryset(self):
        """
        Execute delete on the queryset.
        
        Returns:
            Tuple of (count, details dict)
        """
        # Get objects before delete (for triggers)
        objs = list(self.queryset)
        
        if not objs:
            return 0, {}
        
        # Validate
        self.analyzer.validate_for_delete(objs)
        
        # Execute delete via QuerySet
        # Use __class__.__bases__[0] to call Django's original delete
        from django.db.models import QuerySet
        return QuerySet.delete(self.queryset)
    
    def fetch_old_records(self, instances):
        """
        Fetch old records for comparison.
        
        Args:
            instances: List of instances with PKs
            
        Returns:
            List of old instances (from database)
        """
        pks = [obj.pk for obj in instances if obj.pk is not None]
        if not pks:
            return []
        
        # Fetch using base manager to avoid recursion
        old_records = list(
            self.model_cls._base_manager.filter(pk__in=pks)
        )
        
        # Return as dict for O(1) lookup
        return {obj.pk: obj for obj in old_records}

