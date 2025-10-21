"""
ChangeSet and RecordChange classes for Salesforce-style trigger context.

Provides a first-class abstraction for tracking changes in bulk operations,
similar to Salesforce's Trigger.new, Trigger.old, and Trigger.newMap.
"""


class RecordChange:
    """
    Represents a single record change with old/new state.

    Similar to accessing Trigger.newMap.get(id) in Salesforce, but with
    additional conveniences like O(1) field change detection.
    """

    def __init__(self, new_record, old_record=None, changed_fields=None):
        """
        Initialize a RecordChange.

        Args:
            new_record: The new/current state of the record
            old_record: The old/previous state of the record (None for creates)
            changed_fields: Optional pre-computed set of changed field names.
                          If None, will be computed lazily on first access.
        """
        self.new_record = new_record
        self.old_record = old_record
        self._changed_fields = changed_fields
        self._pk = getattr(new_record, "pk", None) if new_record else None

    @property
    def pk(self):
        """Primary key of the record."""
        return self._pk

    @property
    def changed_fields(self):
        """
        Set of field names that have changed.

        Computed lazily on first access and cached for O(1) subsequent checks.
        """
        if self._changed_fields is None:
            self._changed_fields = self._compute_changed_fields()
        return self._changed_fields

    def has_changed(self, field_name):
        """
        O(1) check if a specific field has changed.

        Args:
            field_name: Name of the field to check

        Returns:
            True if the field value changed, False otherwise
        """
        return field_name in self.changed_fields

    def get_old_value(self, field_name):
        """
        Get the old value for a field.

        Args:
            field_name: Name of the field

        Returns:
            The old value, or None if no old record exists
        """
        if self.old_record is None:
            return None
        return getattr(self.old_record, field_name, None)

    def get_new_value(self, field_name):
        """
        Get the new value for a field.

        Args:
            field_name: Name of the field

        Returns:
            The new value
        """
        return getattr(self.new_record, field_name, None)

    def _compute_changed_fields(self):
        """
        Compute which fields have changed between old and new records.

        Uses Django's field.get_prep_value() for proper comparison that
        handles database-level transformations.

        Returns:
            Set of field names that have changed
        """
        if self.old_record is None:
            return set()

        changed = set()
        model_cls = self.new_record.__class__

        for field in model_cls._meta.fields:
            # Skip primary key - it shouldn't change
            if field.primary_key:
                continue

            old_val = getattr(self.old_record, field.name, None)
            new_val = getattr(self.new_record, field.name, None)

            # Use field's get_prep_value for proper comparison
            # This handles database-level transformations (e.g., timezone conversions)
            try:
                old_prep = field.get_prep_value(old_val)
                new_prep = field.get_prep_value(new_val)
                if old_prep != new_prep:
                    changed.add(field.name)
            except Exception:
                # Fallback to direct comparison if get_prep_value fails
                if old_val != new_val:
                    changed.add(field.name)

        return changed


class ChangeSet:
    """
    Collection of RecordChanges for a bulk operation.

    Similar to Salesforce's Trigger context (Trigger.new, Trigger.old, Trigger.newMap),
    but enhanced for Python's bulk operations paradigm with O(1) lookups and
    additional metadata.
    """

    def __init__(self, model_cls, changes, operation_type, operation_meta=None):
        """
        Initialize a ChangeSet.

        Args:
            model_cls: The Django model class
            changes: List of RecordChange instances
            operation_type: Type of operation ('create', 'update', 'delete')
            operation_meta: Optional dict of additional metadata (e.g., update_kwargs)
        """
        self.model_cls = model_cls
        self.changes = changes  # List[RecordChange]
        self.operation_type = operation_type
        self.operation_meta = operation_meta or {}

        # Build PK -> RecordChange map for O(1) lookups (like Trigger.newMap)
        self._pk_to_change = {c.pk: c for c in changes if c.pk is not None}

    @property
    def new_records(self):
        """
        List of new/current record states.

        Similar to Trigger.new in Salesforce.
        """
        return [c.new_record for c in self.changes if c.new_record is not None]

    @property
    def old_records(self):
        """
        List of old/previous record states.

        Similar to Trigger.old in Salesforce.
        Only includes records that have old states (excludes creates).
        """
        return [c.old_record for c in self.changes if c.old_record is not None]

    def has_field_changed(self, pk, field_name):
        """
        O(1) check if a field changed for a specific record.

        Args:
            pk: Primary key of the record
            field_name: Name of the field to check

        Returns:
            True if the field changed, False otherwise
        """
        change = self._pk_to_change.get(pk)
        return change.has_changed(field_name) if change else False

    def get_old_value(self, pk, field_name):
        """
        Get the old value for a specific record and field.

        Args:
            pk: Primary key of the record
            field_name: Name of the field

        Returns:
            The old value, or None if not found
        """
        change = self._pk_to_change.get(pk)
        return change.get_old_value(field_name) if change else None

    def get_new_value(self, pk, field_name):
        """
        Get the new value for a specific record and field.

        Args:
            pk: Primary key of the record
            field_name: Name of the field

        Returns:
            The new value, or None if not found
        """
        change = self._pk_to_change.get(pk)
        return change.get_new_value(field_name) if change else None

    def chunk(self, chunk_size):
        """
        Split ChangeSet into smaller chunks for memory-efficient processing.

        Useful for processing very large bulk operations without loading
        all data into memory at once.

        Args:
            chunk_size: Number of changes per chunk

        Yields:
            ChangeSet instances, each with up to chunk_size changes
        """
        for i in range(0, len(self.changes), chunk_size):
            chunk_changes = self.changes[i : i + chunk_size]
            yield ChangeSet(
                self.model_cls, chunk_changes, self.operation_type, self.operation_meta
            )
