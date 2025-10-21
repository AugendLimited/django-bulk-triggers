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

Usage Pattern 3 - Custom Resolver:
    ```python
    from django_bulk_triggers import configure_trigger_container

    def custom_resolver(container, trigger_cls, provider_name):
        # Custom resolution logic for nested containers
        return container.sub_container.get_provider(provider_name)()

    configure_trigger_container(container, provider_resolver=custom_resolver)
    ```
"""

import logging
import re
import threading
from typing import Any, Callable, Optional, Type

logger = logging.getLogger(__name__)


class TriggerFactory:
    """
    Creates trigger handler instances with dependency injection.

    Resolution order:
    1. Specific factory for trigger class
    2. Container resolver (if configured)
    3. Direct instantiation
    """

    def __init__(self):
        """Initialize an empty factory."""
        self._specific_factories: dict[Type, Callable[[], Any]] = {}
        self._container_resolver: Optional[Callable[[Type], Any]] = None
        self._lock = threading.RLock()

    def register_factory(self, trigger_cls: Type, factory: Callable[[], Any]) -> None:
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
            >>> factory.register_factory(LoanAccountTrigger, create_loan_trigger)
        """
        with self._lock:
            self._specific_factories[trigger_cls] = factory
            name = getattr(trigger_cls, "__name__", str(trigger_cls))
            logger.debug(f"Registered factory for {name}")

    def configure_container(
        self,
        container: Any,
        provider_name_resolver: Optional[Callable[[Type], str]] = None,
        provider_resolver: Optional[Callable[[Any, Type, str], Any]] = None,
        fallback_to_direct: bool = True,
    ) -> None:
        """
        Configure the factory to use a dependency-injector container.

        This is the recommended way to integrate with dependency-injector.
        It automatically resolves triggers from container providers.

        Args:
            container: The dependency-injector container instance
            provider_name_resolver: Optional function to map trigger class to provider name.
                                  Default: converts "LoanAccountTrigger" -> "loan_account_trigger"
            provider_resolver: Optional function to resolve provider from container.
                             Signature: (container, trigger_cls, provider_name) -> instance
                             Useful for nested container structures or custom resolution logic.
            fallback_to_direct: If True, falls back to direct instantiation when
                              provider not found. If False, raises error.

        Example (Standard Container):
            >>> class AppContainer(containers.DeclarativeContainer):
            ...     loan_service = providers.Singleton(LoanService)
            ...     loan_account_trigger = providers.Singleton(
            ...         LoanAccountTrigger,
            ...         loan_service=loan_service,
            ...     )
            >>>
            >>> container = AppContainer()
            >>> factory.configure_container(container)

        Example (Custom Resolver for Nested Containers):
            >>> def resolve_nested(container, trigger_cls, provider_name):
            ...     # Navigate nested structure
            ...     sub_container = container.loan_accounts_container()
            ...     return getattr(sub_container, provider_name)()
            >>>
            >>> factory.configure_container(
            ...     container,
            ...     provider_resolver=resolve_nested
            ... )
        """
        name_resolver = provider_name_resolver or self._default_name_resolver

        def resolver(trigger_cls: Type) -> Any:
            """Resolve trigger instance from the container."""
            provider_name = name_resolver(trigger_cls)
            name = getattr(trigger_cls, "__name__", str(trigger_cls))

            # If custom provider resolver is provided, use it
            if provider_resolver is not None:
                logger.debug(f"Resolving {name} using custom provider resolver")
                try:
                    return provider_resolver(container, trigger_cls, provider_name)
                except Exception as e:
                    if fallback_to_direct:
                        logger.debug(
                            f"Custom provider resolver failed for {name} ({e}), "
                            f"falling back to direct instantiation"
                        )
                        return trigger_cls()
                    raise

            # Default resolution: look for provider directly on container
            if hasattr(container, provider_name):
                provider = getattr(container, provider_name)
                logger.debug(
                    f"Resolving {name} from container provider '{provider_name}'"
                )
                # Call the provider to get the instance
                return provider()

            if fallback_to_direct:
                logger.debug(
                    f"Provider '{provider_name}' not found in container for {name}, "
                    f"falling back to direct instantiation"
                )
                return trigger_cls()

            raise ValueError(
                f"Trigger {name} not found in container. "
                f"Expected provider name: '{provider_name}'. "
                f"Available providers: {[p for p in dir(container) if not p.startswith('_')]}"
            )

        with self._lock:
            self._container_resolver = resolver
            container_name = getattr(
                container.__class__, "__name__", str(container.__class__)
            )
            logger.info(
                f"Configured trigger factory to use container: {container_name}"
            )

    def create(self, trigger_cls: Type) -> Any:
        """
        Create a trigger instance using the configured resolution strategy.

        Resolution order:
        1. Specific factory registered via register_factory()
        2. Container resolver configured via configure_container()
        3. Direct instantiation trigger_cls()

        Args:
            trigger_cls: The trigger class to instantiate

        Returns:
            An instance of the trigger class

        Raises:
            Any exception raised by the factory, container, or constructor
        """
        with self._lock:
            # 1. Check for specific factory
            if trigger_cls in self._specific_factories:
                factory = self._specific_factories[trigger_cls]
                name = getattr(trigger_cls, "__name__", str(trigger_cls))
                logger.debug(f"Using specific factory for {name}")
                return factory()

            # 2. Check for container resolver
            if self._container_resolver is not None:
                name = getattr(trigger_cls, "__name__", str(trigger_cls))
                logger.debug(f"Using container resolver for {name}")
                return self._container_resolver(trigger_cls)

            # 3. Fall back to direct instantiation
            name = getattr(trigger_cls, "__name__", str(trigger_cls))
            logger.debug(f"Using direct instantiation for {name}")
            return trigger_cls()

    def clear(self) -> None:
        """
        Clear all registered factories and container configuration.
        Useful for testing.
        """
        with self._lock:
            self._specific_factories.clear()
            self._container_resolver = None
            logger.debug("Cleared all trigger factories and container configuration")

    def is_container_configured(self) -> bool:
        """
        Check if a container resolver is configured.

        Returns:
            True if configure_container() has been called
        """
        with self._lock:
            return self._container_resolver is not None

    def has_factory(self, trigger_cls: Type) -> bool:
        """
        Check if a trigger class has a registered factory.

        Args:
            trigger_cls: The trigger class to check

        Returns:
            True if a specific factory is registered, False otherwise
        """
        with self._lock:
            return trigger_cls in self._specific_factories

    def get_factory(self, trigger_cls: Type) -> Optional[Callable[[], Any]]:
        """
        Get the registered factory for a specific trigger class.

        Args:
            trigger_cls: The trigger class to look up

        Returns:
            The registered factory function, or None if not registered
        """
        with self._lock:
            return self._specific_factories.get(trigger_cls)

    def list_factories(self) -> dict[Type, Callable]:
        """
        Get a copy of all registered trigger factories.

        Returns:
            A dictionary mapping trigger classes to their factory functions
        """
        with self._lock:
            return self._specific_factories.copy()

    @staticmethod
    def _default_name_resolver(trigger_cls: Type) -> str:
        """
        Default naming convention: LoanAccountTrigger -> loan_account_trigger

        Args:
            trigger_cls: Trigger class to convert

        Returns:
            Snake-case provider name
        """
        name = trigger_cls.__name__
        # Convert CamelCase to snake_case
        snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        return snake_case


# Global singleton factory
_factory: Optional[TriggerFactory] = None
_factory_lock = threading.Lock()


def get_factory() -> TriggerFactory:
    """
    Get the global trigger factory instance.

    Creates the factory on first access (singleton pattern).
    Thread-safe initialization.

    Returns:
        TriggerFactory singleton instance
    """
    global _factory

    if _factory is None:
        with _factory_lock:
            # Double-checked locking
            if _factory is None:
                _factory = TriggerFactory()

    return _factory


# Backward-compatible module-level functions
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
    trigger_factory = get_factory()
    trigger_factory.register_factory(trigger_cls, factory)


def set_default_trigger_factory(factory: Callable[[Type], Any]) -> None:
    """
    DEPRECATED: Use configure_trigger_container with provider_resolver instead.

    This function is kept for backward compatibility but is no longer recommended.
    Use configure_trigger_container with a custom provider_resolver for similar functionality.

    Args:
        factory: A callable that takes a class and returns an instance
    """
    import warnings

    warnings.warn(
        "set_default_trigger_factory is deprecated. "
        "Use configure_trigger_container with provider_resolver instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Convert to container-style resolver
    def container_resolver(trigger_cls):
        return factory(trigger_cls)

    trigger_factory = get_factory()
    trigger_factory._container_resolver = container_resolver


def configure_trigger_container(
    container: Any,
    provider_name_resolver: Optional[Callable[[Type], str]] = None,
    provider_resolver: Optional[Callable[[Any, Type, str], Any]] = None,
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
        provider_resolver: Optional function to resolve provider from container.
                         Signature: (container, trigger_cls, provider_name) -> instance
                         Useful for nested container structures.
        fallback_to_direct: If True, falls back to direct instantiation when
                          provider not found. If False, raises error.

    Example:
        >>> container = AppContainer()
        >>> configure_trigger_container(container)
    """
    trigger_factory = get_factory()
    trigger_factory.configure_container(
        container,
        provider_name_resolver=provider_name_resolver,
        provider_resolver=provider_resolver,
        fallback_to_direct=fallback_to_direct,
    )


def configure_nested_container(
    container: Any,
    container_path: str,
    provider_name_resolver: Optional[Callable[[Type], str]] = None,
    fallback_to_direct: bool = True,
) -> None:
    """
    DEPRECATED: Use configure_trigger_container with provider_resolver instead.

    Configure the trigger system for nested/hierarchical container structures.
    This is now handled better by passing a custom provider_resolver to
    configure_trigger_container.

    Args:
        container: The root dependency-injector container
        container_path: Dot-separated path to sub-container (e.g., "loan_accounts_container")
        provider_name_resolver: Optional function to map trigger class to provider name
        fallback_to_direct: If True, falls back to direct instantiation when provider not found

    Example:
        >>> # Instead of this:
        >>> configure_nested_container(app_container, "loan_accounts_container")
        >>>
        >>> # Use this:
        >>> def resolve_nested(container, trigger_cls, provider_name):
        ...     sub = container.loan_accounts_container()
        ...     return getattr(sub, provider_name)()
        >>> configure_trigger_container(app_container, provider_resolver=resolve_nested)
    """
    import warnings

    warnings.warn(
        "configure_nested_container is deprecated. "
        "Use configure_trigger_container with provider_resolver instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    def nested_resolver(container_obj, trigger_cls, provider_name):
        """Navigate to sub-container and get provider."""
        # Navigate to sub-container
        current = container_obj
        for part in container_path.split("."):
            if not hasattr(current, part):
                raise ValueError(
                    f"Container path '{container_path}' not found. Missing: {part}"
                )
            provider = getattr(current, part)
            # Call provider to get next level
            current = provider()

        # Get the trigger provider from sub-container
        if not hasattr(current, provider_name):
            raise ValueError(
                f"Provider '{provider_name}' not found in sub-container. "
                f"Available: {[p for p in dir(current) if not p.startswith('_')]}"
            )

        trigger_provider = getattr(current, provider_name)
        logger.debug(
            f"Resolved {trigger_cls.__name__} from {container_path}.{provider_name}"
        )
        return trigger_provider()

    configure_trigger_container(
        container,
        provider_name_resolver=provider_name_resolver,
        provider_resolver=nested_resolver,
        fallback_to_direct=fallback_to_direct,
    )


def clear_trigger_factories() -> None:
    """
    Clear all registered trigger factories and container configuration.
    Useful for testing.
    """
    trigger_factory = get_factory()
    trigger_factory.clear()


def create_trigger_instance(trigger_cls: Type) -> Any:
    """
    Create a trigger instance using the configured resolution strategy.

    Resolution order:
    1. Specific factory registered via set_trigger_factory()
    2. Container resolver configured via configure_trigger_container()
    3. Direct instantiation trigger_cls()

    Args:
        trigger_cls: The trigger class to instantiate

    Returns:
        An instance of the trigger class

    Raises:
        Any exception raised by the factory, container, or constructor
    """
    trigger_factory = get_factory()
    return trigger_factory.create(trigger_cls)


def get_trigger_factory(trigger_cls: Type) -> Optional[Callable[[], Any]]:
    """
    Get the registered factory for a specific trigger class.

    Args:
        trigger_cls: The trigger class to look up

    Returns:
        The registered factory function, or None if not registered
    """
    trigger_factory = get_factory()
    return trigger_factory.get_factory(trigger_cls)


def has_trigger_factory(trigger_cls: Type) -> bool:
    """
    Check if a trigger class has a registered factory.

    Args:
        trigger_cls: The trigger class to check

    Returns:
        True if a specific factory is registered, False otherwise
    """
    trigger_factory = get_factory()
    return trigger_factory.has_factory(trigger_cls)


def is_container_configured() -> bool:
    """
    Check if a container resolver is configured.

    Returns:
        True if configure_trigger_container() has been called
    """
    trigger_factory = get_factory()
    return trigger_factory.is_container_configured()


def list_registered_factories() -> dict[Type, Callable]:
    """
    Get a copy of all registered trigger factories.

    Returns:
        A dictionary mapping trigger classes to their factory functions
    """
    trigger_factory = get_factory()
    return trigger_factory.list_factories()
