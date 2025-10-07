"""
Tests for nested container support in django-bulk-triggers.

This test suite validates that the framework properly supports
hierarchical/nested container structures.
"""

import pytest

# Skip all tests if dependency-injector is not installed
dependency_injector = pytest.importorskip("dependency_injector")
containers = dependency_injector.containers
providers = dependency_injector.providers

from django_bulk_triggers import (
    configure_nested_container,
    configure_trigger_container,
    clear_trigger_factories,
    create_trigger_instance,
)
from django_bulk_triggers.handler import Trigger
from django_bulk_triggers.decorators import trigger
from django_bulk_triggers.constants import BEFORE_CREATE
from tests.models import Account


# Mock Services
class AccountService:
    def __init__(self):
        self.processed = []
    
    def process(self, account):
        self.processed.append(account)


class AccountValidator:
    def __init__(self):
        self.validated = []
    
    def validate(self, account):
        self.validated.append(account)


# Trigger Class
class AccountTrigger(Trigger):
    def __init__(self, account_service: AccountService, account_validator: AccountValidator):
        self.service = account_service
        self.validator = account_validator
    
    @trigger(BEFORE_CREATE, model=Account)
    def validate_on_create(self, new_records, old_records=None):
        for account in new_records:
            self.validator.validate(account)


# Nested Container Structure
class AccountsContainer(containers.DeclarativeContainer):
    """Sub-container for account-related dependencies."""
    
    account_service = providers.Singleton(AccountService)
    account_validator = providers.Singleton(AccountValidator)
    
    account_trigger = providers.Singleton(
        AccountTrigger,
        account_service=account_service,
        account_validator=account_validator,
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """Root application container with nested sub-containers."""
    
    accounts_container = providers.Singleton(AccountsContainer)


@pytest.fixture(autouse=True)
def cleanup():
    """Clean up trigger factories after each test."""
    yield
    clear_trigger_factories()


class TestNestedContainerSupport:
    """Test suite for nested container support."""
    
    def test_configure_nested_container_simple(self):
        """Test basic nested container configuration."""
        container = ApplicationContainer()
        
        configure_nested_container(
            container,
            container_path="accounts_container"
        )
        
        # Should be able to create trigger with dependencies
        trigger_instance = create_trigger_instance(AccountTrigger)
        
        assert isinstance(trigger_instance, AccountTrigger)
        assert isinstance(trigger_instance.service, AccountService)
        assert isinstance(trigger_instance.validator, AccountValidator)
    
    def test_nested_container_provides_singletons(self):
        """Test that nested container provides singleton instances."""
        container = ApplicationContainer()
        
        configure_nested_container(
            container,
            container_path="accounts_container"
        )
        
        instance1 = create_trigger_instance(AccountTrigger)
        instance2 = create_trigger_instance(AccountTrigger)
        
        # Should be same singleton
        assert instance1 is instance2
        assert instance1.service is instance2.service
    
    def test_nested_container_functional_dependencies(self):
        """Test that dependencies from nested container work correctly."""
        container = ApplicationContainer()
        
        configure_nested_container(
            container,
            container_path="accounts_container"
        )
        
        trigger_instance = create_trigger_instance(AccountTrigger)
        
        # Test dependencies are functional
        class MockAccount:
            pk = 1
        
        account = MockAccount()
        trigger_instance.validator.validate(account)
        
        assert account in trigger_instance.validator.validated
    
    def test_custom_provider_resolver(self):
        """Test custom provider resolver for complex nested structures."""
        container = ApplicationContainer()
        
        def custom_resolver(root_container, trigger_cls, provider_name):
            # Custom logic to navigate container structure
            accounts_container = root_container.accounts_container()
            return accounts_container.account_trigger()
        
        configure_trigger_container(
            container,
            provider_resolver=custom_resolver
        )
        
        trigger_instance = create_trigger_instance(AccountTrigger)
        assert isinstance(trigger_instance, AccountTrigger)
    
    def test_deeply_nested_containers(self):
        """Test support for deeply nested container structures."""
        
        class Level3Container(containers.DeclarativeContainer):
            account_trigger = providers.Singleton(
                AccountTrigger,
                account_service=providers.Singleton(AccountService),
                account_validator=providers.Singleton(AccountValidator),
            )
        
        class Level2Container(containers.DeclarativeContainer):
            level3 = providers.Singleton(Level3Container)
        
        class Level1Container(containers.DeclarativeContainer):
            level2 = providers.Singleton(Level2Container)
        
        container = Level1Container()
        
        configure_nested_container(
            container,
            container_path="level2.level3"
        )
        
        trigger_instance = create_trigger_instance(AccountTrigger)
        assert isinstance(trigger_instance, AccountTrigger)
    
    def test_fallback_when_provider_not_found(self):
        """Test fallback behavior when provider not found in nested container."""
        
        class EmptyContainer(containers.DeclarativeContainer):
            pass
        
        class RootContainer(containers.DeclarativeContainer):
            empty = providers.Singleton(EmptyContainer)
        
        container = RootContainer()
        
        # This should fail because account_trigger doesn't exist
        with pytest.raises(ValueError, match="Provider 'account_trigger' not found"):
            configure_nested_container(
                container,
                container_path="empty",
                fallback_to_direct=False
            )
            create_trigger_instance(AccountTrigger)
    
    def test_invalid_container_path(self):
        """Test error handling for invalid container path."""
        container = ApplicationContainer()
        
        with pytest.raises(ValueError, match="Container path.*not found"):
            configure_nested_container(
                container,
                container_path="nonexistent_container"
            )
            create_trigger_instance(AccountTrigger)
    
    def test_multiple_nested_containers_different_apps(self):
        """Test multiple nested containers for different app modules."""
        
        class AnotherTrigger(Trigger):
            def __init__(self, service: AccountService):
                self.service = service
        
        class ModuleAContainer(containers.DeclarativeContainer):
            account_trigger = providers.Singleton(
                AccountTrigger,
                account_service=providers.Singleton(AccountService),
                account_validator=providers.Singleton(AccountValidator),
            )
        
        class ModuleBContainer(containers.DeclarativeContainer):
            another_trigger = providers.Singleton(
                AnotherTrigger,
                service=providers.Singleton(AccountService),
            )
        
        class AppContainer(containers.DeclarativeContainer):
            module_a = providers.Singleton(ModuleAContainer)
            module_b = providers.Singleton(ModuleBContainer)
        
        container = AppContainer()
        
        # Configure for module A
        configure_nested_container(
            container,
            container_path="module_a"
        )
        
        trigger_a = create_trigger_instance(AccountTrigger)
        assert isinstance(trigger_a, AccountTrigger)
        
        # Reconfigure for module B
        def resolve_module_b(root, trigger_cls, provider_name):
            if trigger_cls == AnotherTrigger:
                module_b = root.module_b()
                return module_b.another_trigger()
            raise ValueError("Unknown trigger")
        
        configure_trigger_container(
            container,
            provider_resolver=resolve_module_b
        )
        
        trigger_b = create_trigger_instance(AnotherTrigger)
        assert isinstance(trigger_b, AnotherTrigger)


@pytest.mark.django_db
class TestNestedContainerIntegration:
    """Integration tests with Django models."""
    
    def test_nested_container_with_model_operations(self):
        """Test nested container configuration with actual model operations."""
        container = ApplicationContainer()
        
        configure_nested_container(
            container,
            container_path="accounts_container"
        )
        
        trigger_instance = create_trigger_instance(AccountTrigger)
        
        # Create account
        account = Account(name="Test Account", balance=100)
        
        # Manually trigger validation
        trigger_instance.validate_on_create(new_records=[account])
        
        # Verify validator was called
        assert account in trigger_instance.validator.validated

