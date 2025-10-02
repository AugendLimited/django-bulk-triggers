import logging

from django_bulk_triggers.handler import Trigger as TriggerClass
from django_bulk_triggers.manager import BulkTriggerManager
from django_bulk_triggers.factory import (
    set_trigger_factory,
    set_default_trigger_factory,
    configure_trigger_container,
    clear_trigger_factories,
    create_trigger_instance,
    is_container_configured,
)

# Add NullHandler to prevent logging messages if the application doesn't configure logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "BulkTriggerManager",
    "TriggerClass",
    "set_trigger_factory",
    "set_default_trigger_factory",
    "configure_trigger_container",
    "clear_trigger_factories",
    "create_trigger_instance",
    "is_container_configured",
]
