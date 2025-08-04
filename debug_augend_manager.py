from django_bulk_hooks.manager import BulkHookManager
from queryable_properties.managers import QueryablePropertiesManager


class AugendManager(BulkHookManager, QueryablePropertiesManager):
    def get_queryset(self):
        print(f"DEBUG: AugendManager.get_queryset() called for {self.model}")
        
        # Check the MRO
        print(f"DEBUG: MRO: {AugendManager.__mro__}")
        
        # Try different ways to call the parent
        print(f"DEBUG: Calling BulkHookManager.get_queryset directly")
        qs = BulkHookManager.get_queryset(self)
        print(f"DEBUG: Base QuerySet type: {type(qs)}")
        
        # Apply queryable properties to the existing QuerySet
        for field_name in getattr(self.model, "_queryable_properties", []):
            if hasattr(self.model, field_name):
                property_obj = getattr(self.model, field_name)
                if hasattr(property_obj, "get_queryset"):
                    print(f"DEBUG: Applying queryable property: {field_name}")
                    qs = property_obj.get_queryset(qs)
                    print(f"DEBUG: QuerySet type after {field_name}: {type(qs)}")
        
        print(f"DEBUG: Final QuerySet type: {type(qs)}")
        return qs 