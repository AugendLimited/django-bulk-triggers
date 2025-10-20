import logging

from django_bulk_triggers.handler import Trigger as TriggerClass
from django_bulk_triggers.manager import BulkTriggerManager
from django_bulk_triggers.factory import (
    set_trigger_factory,
    set_default_trigger_factory,
    configure_trigger_container,
    configure_nested_container,
    clear_trigger_factories,
    create_trigger_instance,
    is_container_configured,
)
from django_bulk_triggers.constants import DEFAULT_BULK_UPDATE_BATCH_SIZE
from django_bulk_triggers.changeset import ChangeSet, RecordChange
from django_bulk_triggers.dispatcher import get_dispatcher, TriggerDispatcher
from django_bulk_triggers.helpers import (
    build_changeset_for_create,
    build_changeset_for_update,
    build_changeset_for_delete,
    dispatch_triggers_for_operation,
)

# Service layer (NEW architecture)
from django_bulk_triggers.operations import (
    BulkOperationCoordinator,
    ModelAnalyzer,
    BulkExecutor,
    MTIHandler,
)

# Add NullHandler to prevent logging messages if the application doesn't configure logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "BulkTriggerManager",
    "TriggerClass",
    "set_trigger_factory",
    "set_default_trigger_factory",
    "configure_trigger_container",
    "configure_nested_container",
    "clear_trigger_factories",
    "create_trigger_instance",
    "is_container_configured",
    "DEFAULT_BULK_UPDATE_BATCH_SIZE",
    # Dispatcher-centric architecture
    "ChangeSet",
    "RecordChange",
    "get_dispatcher",
    "TriggerDispatcher",
    "build_changeset_for_create",
    "build_changeset_for_update",
    "build_changeset_for_delete",
    "dispatch_triggers_for_operation",
    # Service layer (composition-based architecture)
    "BulkOperationCoordinator",
    "ModelAnalyzer",
    "BulkExecutor",
    "MTIHandler",
]
