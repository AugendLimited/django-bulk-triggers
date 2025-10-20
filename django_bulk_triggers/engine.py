"""
DEPRECATED: This module is deprecated in favor of dispatcher.py.

The dispatcher is now the single source of truth for trigger execution.
This module is kept for backward compatibility only.
"""
import warnings
import logging

logger = logging.getLogger(__name__)


def run(model_cls, event, new_records, old_records=None, ctx=None):
    """
    DEPRECATED: Use dispatcher.get_dispatcher().dispatch() instead.
    
    This function forwards to the dispatcher for backward compatibility.
    
    Args:
        model_cls: The Django model class
        event: The event name (e.g., 'after_update')
        new_records: List of new/current record states
        old_records: List of old/previous record states (optional)
        ctx: Context object (optional, for bypass_triggers flag)
    """
    warnings.warn(
        "engine.run() is deprecated. Use dispatcher.get_dispatcher().dispatch() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    if not new_records:
        return
    
    from django_bulk_triggers.dispatcher import get_dispatcher
    from django_bulk_triggers.changeset import ChangeSet, RecordChange
    
    # Build ChangeSet from old API
    if old_records is None:
        old_records = [None] * len(new_records)
    
    changes = [
        RecordChange(new, old) 
        for new, old in zip(new_records, old_records)
    ]
    
    # Infer operation type from event
    if 'create' in event:
        op_type = 'create'
    elif 'update' in event:
        op_type = 'update'
    elif 'delete' in event:
        op_type = 'delete'
    else:
        op_type = 'unknown'
    
    changeset = ChangeSet(model_cls, changes, op_type, {})
    
    # Get bypass flag from context
    bypass = False
    if ctx and hasattr(ctx, 'bypass_triggers'):
        bypass = ctx.bypass_triggers
    
    # Delegate to dispatcher
    dispatcher = get_dispatcher()
    dispatcher.dispatch(changeset, event, bypass_triggers=bypass)
