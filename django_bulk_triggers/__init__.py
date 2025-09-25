import logging

from django_bulk_triggers.handler import Trigger as TriggerClass
from django_bulk_triggers.manager import BulkTriggerManager

# Add NullHandler to prevent logging messages if the application doesn't configure logging
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = ["BulkTriggerManager", "TriggerClass"]
