# Production Setup Guide for Django Bulk Signals

This guide shows how to properly configure Django Bulk Signals for production use with enterprise-grade dependency injection.

## 1. Django Settings Configuration

Add to your `settings.py`:

```python
# Basic configuration
BULK_SIGNALS_EXECUTOR_CLASS = "django_bulk_signals.executors.SyncTriggerExecutor"
BULK_SIGNALS_EXECUTOR_KWARGS = {}

# Performance configuration
BULK_SIGNALS_BATCH_SIZE = 1000
BULK_SIGNALS_ENABLE_CACHING = True
BULK_SIGNALS_CACHE_TTL = 300

# Circuit breaker configuration for resilience
BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER = True
BULK_SIGNALS_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
BULK_SIGNALS_CIRCUIT_BREAKER_TIMEOUT = 60

# Metrics configuration
BULK_SIGNALS_ENABLE_METRICS = True
BULK_SIGNALS_METRICS_BACKEND = "prometheus"

# Logging configuration
BULK_SIGNALS_LOG_LEVEL = "INFO"
BULK_SIGNALS_LOG_EXECUTION_TIME = True
BULK_SIGNALS_LOG_INSTANCE_COUNTS = True

# Error handling configuration
BULK_SIGNALS_FAIL_FAST = True
BULK_SIGNALS_MAX_RETRIES = 3
BULK_SIGNALS_RETRY_DELAY = 1.0
```

## 2. Django App Configuration

Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... other apps
    'django_bulk_signals',
]
```

The app will automatically initialize services when Django starts.

## 3. Manual Service Initialization (Advanced)

For custom initialization:

```python
from django_bulk_signals.initialization import initialize_bulk_signals
from django_bulk_signals.executors import BatchedTriggerExecutor, MetricsTriggerExecutor

# Create custom executor
custom_executor = BatchedTriggerExecutor(
    batch_size=500,
    executor=MetricsTriggerExecutor()
)

# Initialize service
service = initialize_bulk_signals(
    environment="production",
    custom_executor=custom_executor,
    service_name="custom"
)
```

## 4. Using Services in Your Code

### Basic Usage (Automatic)
```python
from django_bulk_signals import BulkSignalModelMixin

class MyModel(BulkSignalModelMixin):
    name = models.CharField(max_length=100)
    
    # Services are automatically injected
```

### Advanced Usage (Manual Injection)
```python
from django_bulk_signals.services import get_service, register_service
from django_bulk_signals.executors import BatchedTriggerExecutor

# Get default service
service = get_service()

# Register custom service
custom_service = TriggerService(
    config=TriggerServiceConfig(
        executor=BatchedTriggerExecutor(batch_size=500)
    )
)
register_service(custom_service, "high_performance")

# Use custom service
service = get_service("high_performance")
```

## 5. Environment-Specific Configuration

### Production
```python
if os.environ.get("ENVIRONMENT") == "production":
    BULK_SIGNALS_ENABLE_METRICS = True
    BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER = True
    BULK_SIGNALS_BATCH_SIZE = 2000
    BULK_SIGNALS_LOG_LEVEL = "WARNING"
```

### Development
```python
else:
    BULK_SIGNALS_ENABLE_METRICS = False
    BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER = False
    BULK_SIGNALS_BATCH_SIZE = 100
    BULK_SIGNALS_LOG_LEVEL = "DEBUG"
```

## 6. Custom Executors

### Async Executor
```python
from django_bulk_signals.executors import TriggerExecutor
import asyncio

class AsyncTriggerExecutor(TriggerExecutor):
    def execute(self, signal, sender, instances, originals=None, **kwargs):
        # Async implementation
        asyncio.create_task(self._async_execute(signal, sender, instances, originals, **kwargs))
    
    async def _async_execute(self, signal, sender, instances, originals, **kwargs):
        # Your async logic here
        pass
```

### Celery Executor
```python
from django_bulk_signals.executors import TriggerExecutor
from celery import shared_task

class CeleryTriggerExecutor(TriggerExecutor):
    def execute(self, signal, sender, instances, originals=None, **kwargs):
        # Queue for Celery processing
        process_triggers.delay(signal, sender, instances, originals, **kwargs)

@shared_task
def process_triggers(signal, sender, instances, originals, **kwargs):
    # Process triggers in Celery worker
    pass
```

## 7. Testing

### Unit Testing
```python
from django_bulk_signals.services import register_service, clear_services
from django_bulk_signals.executors import SyncTriggerExecutor

class TestBulkSignals(TestCase):
    def setUp(self):
        # Clear services for clean test
        clear_services()
        
        # Register test service
        test_service = TriggerService(
            config=TriggerServiceConfig(executor=SyncTriggerExecutor())
        )
        register_service(test_service, "test")
    
    def tearDown(self):
        clear_services()
```

### Integration Testing
```python
from django_bulk_signals.initialization import initialize_bulk_signals

class TestIntegration(TestCase):
    def setUp(self):
        self.service = initialize_bulk_signals(
            environment="development",
            service_name="test"
        )
```

## 8. Monitoring and Metrics

### Prometheus Integration
```python
BULK_SIGNALS_ENABLE_METRICS = True
BULK_SIGNALS_METRICS_BACKEND = "prometheus"
```

### Custom Metrics
```python
from django_bulk_signals.executors import MetricsTriggerExecutor

# Metrics are automatically collected
executor = MetricsTriggerExecutor()
metrics = executor.get_metrics()
print(metrics)
```

## 9. Error Handling and Resilience

### Circuit Breaker
```python
BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER = True
BULK_SIGNALS_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
BULK_SIGNALS_CIRCUIT_BREAKER_TIMEOUT = 60
```

### Retry Logic
```python
BULK_SIGNALS_MAX_RETRIES = 3
BULK_SIGNALS_RETRY_DELAY = 1.0
```

## 10. Performance Optimization

### Batching
```python
BULK_SIGNALS_BATCH_SIZE = 1000
```

### Caching
```python
BULK_SIGNALS_ENABLE_CACHING = True
BULK_SIGNALS_CACHE_TTL = 300
```

## 11. Deployment Checklist

- [ ] Configure Django settings for your environment
- [ ] Set up monitoring and metrics collection
- [ ] Configure circuit breakers for resilience
- [ ] Set appropriate batch sizes for your workload
- [ ] Enable logging at appropriate levels
- [ ] Test with your specific data volumes
- [ ] Set up alerting for failures
- [ ] Document your custom configurations

## 12. Troubleshooting

### Common Issues

1. **Service not initialized**: Ensure `django_bulk_signals` is in `INSTALLED_APPS`
2. **Performance issues**: Adjust `BULK_SIGNALS_BATCH_SIZE`
3. **Memory issues**: Enable caching with `BULK_SIGNALS_ENABLE_CACHING`
4. **Cascading failures**: Enable circuit breaker with `BULK_SIGNALS_ENABLE_CIRCUIT_BREAKER`

### Debug Mode
```python
BULK_SIGNALS_LOG_LEVEL = "DEBUG"
BULK_SIGNALS_LOG_EXECUTION_TIME = True
BULK_SIGNALS_LOG_INSTANCE_COUNTS = True
```

This setup provides enterprise-grade dependency injection and configuration management for production use.
