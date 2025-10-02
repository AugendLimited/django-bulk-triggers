"""
Trigger factory system for dependency injection.

This module provides seamless integration with dependency-injector containers,
allowing triggers to be managed as container providers with full DI support.

Usage Pattern 1 - Container Integration (Recommended):
    ```python
    from dependency_injector import containers, providers
    from django_bulk_triggers import configure_trigger_container
    
    class LoanAccountContainer(containers.DeclarativeContainer):
        loan_account_repository = providers.Singleton(LoanAccountRepository)
        loan_account_service = providers.Singleton(LoanAccountService)
        loan_account_validator = providers.Singleton(LoanAccountValidator)
        
        # Define trigger as a provider
        loan_account_trigger = providers.Singleton(
            LoanAccountTrigger,
            daily_loan_summary_service=Provide["daily_loan_summary_service"],
            loan_account_service=loan_account_service,
            loan_account_validator=loan_account_validator,
        )
    
    # Configure the trigger system to use your container
    container = LoanAccountContainer()
    configure_trigger_container(container)
    ```

Usage Pattern 2 - Explicit Factory Registration:
    ```python
    from django_bulk_triggers import set_trigger_factory
    
    def create_loan_trigger():
        return container.loan_account_trigger()
    
    set_trigger_factory(LoanAccountTrigger, create_loan_trigger)
    ```

Usage Pattern 3 - Global Resolver:
    ```python
    from django_bulk_triggers import set_default_trigger_factory
    
    def resolve_from_container(trigger_cls):
        # Custom resolution logic
        provider_name = trigger_cls.__name__.lower().replace('trigger', '_trigger')
        return getattr(container, provider_name)()
    
    set_default_trigger_factory(resolve_from_container)
    ```
"""

import logging
import threading
from typing import Any, Callable, Optional, Type

logger = logging.getLogger(__name__)

# Thread-safe storage for trigger factories
_trigger_factories: dict[Type, Callable[[], Any]] = {}
_default_factory: Optional[Callable[[Type], Any]] = None
_container_resolver: Optional[Callable[[Type], Any]] = None
_factory_lock = threading.RLock()


def set_trigger_factory(trigger_cls: Type, factory: Callable[[], Any]) -> None:
    """
    Register a factory function for a specific trigger class.
    
    The factory function should accept no arguments and return an instance
    of the trigger class with all dependencies injected.
    
    Args:
        trigger_cls: The trigger class to register a factory for
        factory: A callable that returns an instance of trigger_cls
        
    Example:
        >>> def create_loan_trigger():
        ...     return container.loan_account_trigger()
        >>> 
        >>> set_trigger_factory(LoanAccountTrigger, create_loan_trigger)
    """
    with _factory_lock:
        _trigger_factories[trigger_cls] = factory
        logger.debug(f"Registered factory for {trigger_cls.__name__}")


def set_default_trigger_factory(factory: Callable[[Type], Any]) -> None:
    """
    Set a default factory function for all triggers without a specific factory.
    
    The factory function should accept a trigger class and return an instance.
    This is useful for DI containers that can resolve any class dynamically.
    
    Args:
        factory: A callable that takes a class and returns an instance
        
    Example:
        >>> def resolve_trigger(trigger_cls):
        ...     return container.resolve(trigger_cls)
        >>> 
        >>> set_default_trigger_factory(resolve_trigger)
    """
    global _default_factory
    with _factory_lock:
        _default_factory = factory
        logger.debug("Registered default trigger factory")


def configure_trigger_container(
    container: Any,
    provider_name_resolver: Optional[Callable[[Type], str]] = None,
    fallback_to_direct: bool = True,
) -> None:
    """
    Configure the trigger system to use a dependency-injector container.
    
    This is the recommended way to integrate with dependency-injector.
    It automatically resolves triggers from container providers.
    
    Args:
        container: The dependency-injector container instance
        provider_name_resolver: Optional function to map trigger class to provider name.
                              Default: converts "LoanAccountTrigger" -> "loan_account_trigger"
        fallback_to_direct: If True, falls back to direct instantiation when
                          provider not found. If False, raises error.
    
    Example:
        >>> from dependency_injector import containers, providers
        >>> 
        >>> class AppContainer(containers.DeclarativeContainer):
        ...     loan_service = providers.Singleton(LoanService)
        ...     loan_account_trigger = providers.Singleton(
        ...         LoanAccountTrigger,
        ...         loan_service=loan_service,
        ...     )
        >>> 
        >>> container = AppContainer()
        >>> configure_trigger_container(container)
    """
    global _container_resolver
    
    def default_provider_name_resolver(trigger_cls: Type) -> str:
        """
        Default naming convention: LoanAccountTrigger -> loan_account_trigger
        """
        name = trigger_cls.__name__
        # Convert CamelCase to snake_case
        import re
        snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
        return snake_case
    
    resolver = provider_name_resolver or default_provider_name_resolver
    
    def resolve_from_container(trigger_cls: Type) -> Any:
        """
        Resolve trigger instance from the container.
        """
        provider_name = resolver(trigger_cls)
        
        # Try to get the provider from the container
        if hasattr(container, provider_name):
            provider = getattr(container, provider_name)
            logger.debug(
                f"Resolving {trigger_cls.__name__} from container provider '{provider_name}'"
            )
            # Call the provider to get the instance
            return provider()
        
        if fallback_to_direct:
            logger.debug(
                f"Provider '{provider_name}' not found in container for {trigger_cls.__name__}, "
                f"falling back to direct instantiation"
            )
            return trigger_cls()
        
        raise ValueError(
            f"Trigger {trigger_cls.__name__} not found in container. "
            f"Expected provider name: '{provider_name}'. "
            f"Available providers: {[p for p in dir(container) if not p.startswith('_')]}"
        )
    
    with _factory_lock:
        _container_resolver = resolve_from_container
        logger.info(f"Configured trigger system to use container: {container.__class__.__name__}")


def clear_trigger_factories() -> None:
    """
    Clear all registered trigger factories and container configuration.
    Useful for testing.
    """
    global _default_factory, _container_resolver
    with _factory_lock:
        _trigger_factories.clear()
        _default_factory = None
        _container_resolver = None
        logger.debug("Cleared all trigger factories and container configuration")


def create_trigger_instance(trigger_cls: Type) -> Any:
    """
    Create a trigger instance using the configured resolution strategy.
    
    Resolution order:
    1. Specific factory registered via set_trigger_factory()
    2. Container resolver configured via configure_trigger_container()
    3. Default factory registered via set_default_trigger_factory()
    4. Direct instantiation trigger_cls()
    
    Args:
        trigger_cls: The trigger class to instantiate
        
    Returns:
        An instance of the trigger class
        
    Raises:
        Any exception raised by the factory, container, or constructor
    """
    with _factory_lock:
        # 1. Check for specific factory
        if trigger_cls in _trigger_factories:
            factory = _trigger_factories[trigger_cls]
            logger.debug(f"Using specific factory for {trigger_cls.__name__}")
            return factory()
        
        # 2. Check for container resolver
        if _container_resolver is not None:
            logger.debug(f"Using container resolver for {trigger_cls.__name__}")
            return _container_resolver(trigger_cls)
        
        # 3. Check for default factory
        if _default_factory is not None:
            logger.debug(f"Using default factory for {trigger_cls.__name__}")
            return _default_factory(trigger_cls)
        
        # 4. Fall back to direct instantiation
        logger.debug(f"Using direct instantiation for {trigger_cls.__name__}")
        return trigger_cls()


def get_trigger_factory(trigger_cls: Type) -> Optional[Callable[[], Any]]:
    """
    Get the registered factory for a specific trigger class.
    
    Args:
        trigger_cls: The trigger class to look up
        
    Returns:
        The registered factory function, or None if not registered
    """
    with _factory_lock:
        return _trigger_factories.get(trigger_cls)


def has_trigger_factory(trigger_cls: Type) -> bool:
    """
    Check if a trigger class has a registered factory.
    
    Args:
        trigger_cls: The trigger class to check
        
    Returns:
        True if a specific factory is registered, False otherwise
    """
    with _factory_lock:
        return trigger_cls in _trigger_factories


def is_container_configured() -> bool:
    """
    Check if a container resolver is configured.
    
    Returns:
        True if configure_trigger_container() has been called
    """
    with _factory_lock:
        return _container_resolver is not None


def list_registered_factories() -> dict[Type, Callable]:
    """
    Get a copy of all registered trigger factories.
    
    Returns:
        A dictionary mapping trigger classes to their factory functions
    """
    with _factory_lock:
        return _trigger_factories.copy()

