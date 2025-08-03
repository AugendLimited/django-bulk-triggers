from django.db import models, transaction
from django.db.models import AutoField


class MultiTableBulkCreateManager(models.Manager):
    """
    Custom manager that supports bulk_create for multi-table inheritance models.
    """
    
    def bulk_create(self, objs, **kwargs):
        """
        Enhanced bulk_create that handles multi-table inheritance.
        Falls back to Django's standard bulk_create for single-table models.
        """
        if not objs:
            return objs
        
        inheritance_chain = self._get_inheritance_chain()
        
        if len(inheritance_chain) <= 1:
            # Single table - use Django's standard bulk_create
            return super().bulk_create(objs, **kwargs)
        
        # Multi-table inheritance - use our workaround
        return self._multi_table_bulk_create(objs, inheritance_chain, **kwargs)
    
    def _get_inheritance_chain(self):
        """
        Get the complete inheritance chain from root parent to current model.
        Returns list of model classes in order: [RootParent, Parent, Child]
        """
        chain = []
        current_model = self.model
        
        # Build chain from child to parent
        while current_model:
            if not current_model._meta.proxy:
                chain.append(current_model)
            
            # Find concrete parent
            parents = [
                parent for parent in current_model._meta.parents.keys()
                if not parent._meta.proxy
            ]
            current_model = parents[0] if parents else None
        
        # Reverse to get parent-to-child order
        chain.reverse()
        return chain
    
    def _multi_table_bulk_create(self, objs, inheritance_chain, **kwargs):
        """
        Implement workaround #2: Individual saves for parents, bulk create for child.
        """
        batch_size = kwargs.get('batch_size') or len(objs)
        created_objects = []
        
        with transaction.atomic(using=self.db, savepoint=False):
            # Process in batches
            for i in range(0, len(objs), batch_size):
                batch = objs[i:i + batch_size]
                batch_result = self._process_batch(batch, inheritance_chain, **kwargs)
                created_objects.extend(batch_result)
        
        return created_objects
    
    def _process_batch(self, batch, inheritance_chain, **kwargs):
        """
        Process a single batch of objects through the inheritance chain.
        """
        # Extract parameters for _batched_insert
        ignore_conflicts = kwargs.get('ignore_conflicts', False)
        update_conflicts = kwargs.get('update_conflicts', False)
        update_fields = kwargs.get('update_fields')
        unique_fields = kwargs.get('unique_fields')
        
        # Step 1: Handle parent tables with individual saves (still needed for PKs)
        parent_objects_map = {}  # Maps original obj to its parent instances
        
        for obj in batch:
            parent_instances = {}
            current_parent = None
            
            # Create and save parent instances individually
            for model_class in inheritance_chain[:-1]:  # All except the final child
                parent_obj = self._create_parent_instance(obj, model_class, current_parent)
                
                # Individual save to get the auto-generated PK
                parent_obj.save()
                
                parent_instances[model_class] = parent_obj
                current_parent = parent_obj
            
            parent_objects_map[id(obj)] = parent_instances
        
        # Step 2: Use _batched_insert for child objects (the bulk part)
        child_model = inheritance_chain[-1]
        child_objects = []
        
        for obj in batch:
            child_obj = self._create_child_instance(
                obj, child_model, parent_objects_map.get(id(obj), {})
            )
            child_objects.append(child_obj)
        
        # Prepare parameters similar to Django's bulk_create
        child_opts = child_model._meta
        if unique_fields:
            unique_fields = [
                child_model._meta.get_field(child_opts.pk.name if name == "pk" else name)
                for name in unique_fields
            ]
        if update_fields:
            update_fields = [child_model._meta.get_field(name) for name in update_fields]
        
        on_conflict = child_model.objects._check_bulk_create_options(
            ignore_conflicts, update_conflicts, update_fields, unique_fields
        )
        
        # Get fields for the child table
        fields = [f for f in child_opts.concrete_fields if not f.generated]
        
        # Prepare objects (split those with/without PKs)
        child_manager = child_model.objects
        child_manager._for_write = True
        objs_with_pk, objs_without_pk = child_manager._prepare_for_bulk_create(child_objects)
        
        # Use Django's _batched_insert directly
        returned_columns = []
        if objs_with_pk:
            returned_columns.extend(child_manager._batched_insert(
                objs_with_pk,
                fields,
                len(objs_with_pk),  # Use full batch size for child
                on_conflict=on_conflict,
                update_fields=update_fields,
                unique_fields=unique_fields,
            ))
            # Handle returned columns for objects with PK
            for obj_with_pk, results in zip(objs_with_pk, returned_columns[:len(objs_with_pk)]):
                for result, field in zip(results, child_opts.db_returning_fields):
                    if field != child_opts.pk:
                        setattr(obj_with_pk, field.attname, result)
        
        if objs_without_pk:
            fields_without_pk = [f for f in fields if not isinstance(f, AutoField)]
            returned_cols = child_manager._batched_insert(
                objs_without_pk,
                fields_without_pk,
                len(objs_without_pk),
                on_conflict=on_conflict,
                update_fields=update_fields,
                unique_fields=unique_fields,
            )
            returned_columns.extend(returned_cols)
            
            # Handle returned columns for objects without PK
            from django.db import connections
            connection = connections[child_manager.db]
            if (connection.features.can_return_rows_from_bulk_insert and on_conflict is None):
                offset = len(objs_with_pk) if objs_with_pk else 0
                for obj_without_pk, results in zip(objs_without_pk, returned_columns[offset:]):
                    for result, field in zip(results, child_opts.db_returning_fields):
                        setattr(obj_without_pk, field.attname, result)
        
        # Step 3: Update original objects with generated PKs and state
        for orig_obj, child_obj in zip(batch, child_objects):
            orig_obj.pk = child_obj.pk
            orig_obj._state.adding = False
            orig_obj._state.db = self.db
        
        return batch
    
    def _create_parent_instance(self, source_obj, parent_model, current_parent):
        """
        Create a parent model instance with fields from the source object.
        """
        parent_obj = parent_model()
        
        # Copy local fields that belong to this parent model
        for field in parent_model._meta.local_fields:
            if hasattr(source_obj, field.name):
                value = getattr(source_obj, field.name)
                setattr(parent_obj, field.name, value)
        
        # Set parent pointer if this isn't the root parent
        if current_parent is not None:
            # Find the parent link field
            for field in parent_model._meta.local_fields:
                if (hasattr(field, 'remote_field') and 
                    field.remote_field and 
                    field.remote_field.model == current_parent.__class__):
                    setattr(parent_obj, field.name, current_parent)
                    break
        
        return parent_obj
    
    def _create_child_instance(self, source_obj, child_model, parent_instances):
        """
        Create a child model instance with fields from source and parent links.
        """
        child_obj = child_model()
        
        # Copy local fields from the source object
        for field in child_model._meta.local_fields:
            if isinstance(field, AutoField):
                continue  # Skip auto fields
                
            if hasattr(source_obj, field.name):
                value = getattr(source_obj, field.name)
                setattr(child_obj, field.name, value)
        
        # Set parent pointers
        for parent_model, parent_instance in parent_instances.items():
            # Find the parent link field for this parent
            parent_link = child_model._meta.get_ancestor_link(parent_model)
            if parent_link:
                setattr(child_obj, parent_link.name, parent_instance)
        
        return child_obj


# Usage example:

class BaseModel(models.Model):
    """Base model with common fields."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = False  # This creates a database table


class Person(BaseModel):
    """Person model inheriting from BaseModel."""
    name = models.CharField(max_length=100)
    email = models.EmailField()
    
    # Use our custom manager
    objects = MultiTableBulkCreateManager()


class Employee(Person):
    """Employee model inheriting from Person."""
    employee_id = models.CharField(max_length=20)
    department = models.CharField(max_length=50)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Use our custom manager
    objects = MultiTableBulkCreateManager()


# Example usage:
def example_usage():
    """
    Example of how to use the multi-table bulk create.
    """
    from datetime import datetime
    from decimal import Decimal
    
    # Create a list of Employee objects
    employees = [
        Employee(
            name=f"Employee {i}",
            email=f"employee{i}@company.com",
            employee_id=f"EMP{i:04d}",
            department="Engineering" if i % 2 == 0 else "Marketing",
            salary=Decimal("50000.00") + (i * 1000)
        )
        for i in range(1, 101)  # 100 employees
    ]
    
    # This will now work with multi-table inheritance!
    # It will:
    # 1. Individual saves for BaseModel records (to get PKs)
    # 2. Individual saves for Person records (to get PKs) 
    # 3. Bulk insert for Employee records
    created_employees = Employee.objects.bulk_create(employees, batch_size=50)
    
    print(f"Created {len(created_employees)} employees")
    
    # For single-table models, it still uses Django's standard bulk_create
    simple_objects = [
        Person(name=f"Person {i}", email=f"person{i}@example.com")
        for i in range(1, 11)
    ]
    
    # This uses standard Django bulk_create since Person only inherits from BaseModel
    Person.objects.bulk_create(simple_objects)