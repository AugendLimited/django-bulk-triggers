"""
Helper functions for building ChangeSets from operation contexts.

These functions eliminate duplication across queryset.py, bulk_operations.py,
and models.py by providing reusable ChangeSet builders.

NOTE: These helpers are pure changeset builders - they don't fetch data.
Data fetching is the responsibility of ModelAnalyzer.
"""

from django_bulk_triggers.changeset import ChangeSet, RecordChange


def build_changeset_for_update(
    model_cls, instances, update_kwargs, old_records_map=None, **meta
):
    """
    Build ChangeSet for update operations.

    Args:
        model_cls: Django model class
        instances: List of instances being updated
        update_kwargs: Dict of fields being updated
        old_records_map: Optional dict of {pk: old_instance}. If None, no old records.
        **meta: Additional metadata (e.g., has_subquery=True, lock_records=False)

    Returns:
        ChangeSet instance ready for dispatcher
    """
    if old_records_map is None:
        old_records_map = {}

    changes = [
        RecordChange(
            new, old_records_map.get(new.pk), changed_fields=list(update_kwargs.keys())
        )
        for new in instances
    ]

    operation_meta = {"update_kwargs": update_kwargs}
    operation_meta.update(meta)

    return ChangeSet(model_cls, changes, "update", operation_meta)


def build_changeset_for_create(model_cls, instances, **meta):
    """
    Build ChangeSet for create operations.

    Args:
        model_cls: Django model class
        instances: List of instances being created
        **meta: Additional metadata (e.g., batch_size=1000)

    Returns:
        ChangeSet instance ready for dispatcher
    """
    changes = [RecordChange(new, None) for new in instances]
    return ChangeSet(model_cls, changes, "create", meta)


def build_changeset_for_delete(model_cls, instances, **meta):
    """
    Build ChangeSet for delete operations.

    For delete, the "new_record" is the object being deleted (current state),
    and old_record is also the same (or None). This matches Salesforce behavior
    where Trigger.new contains the records being deleted.

    Args:
        model_cls: Django model class
        instances: List of instances being deleted
        **meta: Additional metadata

    Returns:
        ChangeSet instance ready for dispatcher
    """
    changes = [
        RecordChange(obj, obj)  # new_record and old_record are the same for delete
        for obj in instances
    ]
    return ChangeSet(model_cls, changes, "delete", meta)


def dispatch_triggers_for_operation(changeset, event, bypass_triggers=False):
    """
    Dispatch triggers for an operation using the dispatcher.

    This is a convenience function that wraps the dispatcher call.

    Args:
        changeset: ChangeSet instance
        event: Event name (e.g., 'before_update', 'after_create')
        bypass_triggers: If True, skip trigger execution
    """
    from django_bulk_triggers.dispatcher import get_dispatcher

    dispatcher = get_dispatcher()
    dispatcher.dispatch(changeset, event, bypass_triggers=bypass_triggers)
