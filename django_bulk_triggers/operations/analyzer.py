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
    
    # ========== Data Fetching Methods ==========
    
    def fetch_old_records_map(self, instances):
        """
        Fetch old records for instances in a single bulk query.
        
        This is the SINGLE point of truth for fetching old records.
        All other methods should delegate to this.
        
        Args:
            instances: List of model instances
            
        Returns:
            Dict[pk, instance] for O(1) lookups
        """
        pks = [obj.pk for obj in instances if obj.pk is not None]
        if not pks:
            return {}
        
        return {
            obj.pk: obj 
            for obj in self.model_cls._base_manager.filter(pk__in=pks)
        }
    
    # ========== Field Introspection Methods ==========
    
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
    
    def detect_changed_fields(self, objs):
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
        
        # Fetch old records using the single source of truth
        old_records_map = self.fetch_old_records_map(objs)
        if not old_records_map:
            return []
        
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
            for field in self.model_cls._meta.fields:
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

