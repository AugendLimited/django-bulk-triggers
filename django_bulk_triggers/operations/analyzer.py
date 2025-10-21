"""
Model analyzer service - Combines validation and field tracking.

This service handles all model analysis needs:
- Input validation
- Field change detection
- Field comparison
"""

import logging

logger = logging.getLogger(__name__)


class ModelAnalyzer:
    """
    Analyzes models and validates operations.
    
    This service combines the responsibilities of validation and field tracking
    since they're closely related and often used together.
    """
    
    def __init__(self, model_cls):
        """
        Initialize analyzer for a specific model.
        
        Args:
            model_cls: The Django model class
        """
        self.model_cls = model_cls
    
    # ========== Validation Methods ==========
    
    def validate_for_create(self, objs):
        """
        Validate objects for bulk_create operation.
        
        Args:
            objs: List of model instances
            
        Raises:
            TypeError: If objects are not instances of model_cls
        """
        self._check_types(objs, operation="bulk_create")
        return True
    
    def validate_for_update(self, objs):
        """
        Validate objects for bulk_update operation.
        
        Args:
            objs: List of model instances
            
        Raises:
            TypeError: If objects are not instances of model_cls
            ValueError: If objects don't have primary keys
        """
        self._check_types(objs, operation="bulk_update")
        self._check_has_pks(objs, operation="bulk_update")
        return True
    
    def validate_for_delete(self, objs):
        """
        Validate objects for delete operation.
        
        Args:
            objs: List of model instances
            
        Raises:
            TypeError: If objects are not instances of model_cls
        """
        self._check_types(objs, operation="delete")
        return True
    
    def _check_types(self, objs, operation="operation"):
        """Check that all objects are instances of the model class"""
        if not objs:
            return
        
        invalid_types = {
            type(obj).__name__ 
            for obj in objs 
            if not isinstance(obj, self.model_cls)
        }
        
        if invalid_types:
            raise TypeError(
                f"{operation} expected instances of {self.model_cls.__name__}, "
                f"but got {invalid_types}"
            )
    
    def _check_has_pks(self, objs, operation="operation"):
        """Check that all objects have primary keys"""
        missing_pks = [obj for obj in objs if obj.pk is None]
        
        if missing_pks:
            raise ValueError(
                f"{operation} cannot operate on unsaved {self.model_cls.__name__} instances. "
                f"{len(missing_pks)} object(s) have no primary key."
            )
    
    # ========== Field Introspection Methods ==========
    # Note: Field change detection is handled by RecordChange in changeset.py
    # to maintain a single source of truth for change tracking.
    
    def get_auto_now_fields(self):
        """
        Get fields that have auto_now or auto_now_add set.
        
        Returns:
            list: Field names with auto_now behavior
        """
        auto_now_fields = []
        for field in self.model_cls._meta.fields:
            if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
                auto_now_fields.append(field.name)
        return auto_now_fields
    
    def get_fk_fields(self):
        """
        Get all foreign key fields for the model.
        
        Returns:
            list: FK field names
        """
        return [
            field.name for field in self.model_cls._meta.concrete_fields
            if field.is_relation and not field.many_to_many
        ]

