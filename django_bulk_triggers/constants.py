BEFORE_CREATE = "before_create"
AFTER_CREATE = "after_create"
BEFORE_UPDATE = "before_update"
AFTER_UPDATE = "after_update"
BEFORE_DELETE = "before_delete"
AFTER_DELETE = "after_delete"
VALIDATE_CREATE = "validate_create"
VALIDATE_UPDATE = "validate_update"
VALIDATE_DELETE = "validate_delete"

# Default batch size for bulk_update operations to prevent massive SQL statements
# This prevents PostgreSQL from crashing when updating large datasets with triggers
DEFAULT_BULK_UPDATE_BATCH_SIZE = 1000