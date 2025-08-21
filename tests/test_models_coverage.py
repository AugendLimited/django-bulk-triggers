"""
Additional tests for models module to increase coverage.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django_bulk_hooks.models import HookModelMixin
from django_bulk_hooks.constants import (
    VALIDATE_CREATE, VALIDATE_UPDATE, VALIDATE_DELETE,
    BEFORE_CREATE, BEFORE_UPDATE, BEFORE_DELETE,
    AFTER_CREATE, AFTER_UPDATE, AFTER_DELETE
)
from tests.models import HookModel


class TestModelsCoverage(TestCase):
    """Test uncovered functionality in models module."""
    
    def setUp(self):
        # Create a test model that inherits from HookModelMixin
        class TestModel(HookModelMixin):
            class Meta:
                abstract = True
        
        self.model_cls = TestModel
        self.instance = TestModel()
    
    def test_clean_with_bypass_hooks(self):
        """Test clean method with bypass_hooks=True."""
        # Mock the super().clean() method
        with patch.object(HookModelMixin, 'clean') as mock_super_clean:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                self.instance.clean(bypass_hooks=True)
                
                # Should call super().clean() but not run hooks
                mock_super_clean.assert_called_once()
                mock_run.assert_not_called()
    
    def test_clean_without_bypass_hooks_create(self):
        """Test clean method without bypass_hooks for create operation."""
        # Mock the super().clean() method
        with patch.object(HookModelMixin, 'clean') as mock_super_clean:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Set pk to None to simulate create operation
                self.instance.pk = None
                
                self.instance.clean(bypass_hooks=False)
                
                # Should call super().clean() and run VALIDATE_CREATE hooks
                mock_super_clean.assert_called_once()
                mock_run.assert_called_once_with(
                    self.instance.__class__, 
                    VALIDATE_CREATE, 
                    [self.instance], 
                    ctx=mock_run.call_args[1]['ctx']
                )
    
    def test_clean_without_bypass_hooks_update(self):
        """Test clean method without bypass_hooks for update operation."""
        # Mock the super().clean() method
        with patch.object(HookModelMixin, 'clean') as mock_super_clean:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Mock _base_manager.get to return an old instance
                mock_old_instance = Mock()
                with patch.object(self.instance.__class__, '_base_manager') as mock_base_manager:
                    mock_base_manager.get.return_value = mock_old_instance
                    
                    # Set pk to simulate update operation
                    self.instance.pk = 1
                    
                    self.instance.clean(bypass_hooks=False)
                    
                    # Should call super().clean() and run VALIDATE_UPDATE hooks
                    mock_super_clean.assert_called_once()
                    mock_run.assert_called_once_with(
                        self.instance.__class__, 
                        VALIDATE_UPDATE, 
                        [self.instance], 
                        [mock_old_instance],
                        ctx=mock_run.call_args[1]['ctx']
                    )
    
    def test_clean_without_bypass_hooks_update_does_not_exist(self):
        """Test clean method without bypass_hooks for update when old instance doesn't exist."""
        # Mock the super().clean() method
        with patch.object(HookModelMixin, 'clean') as mock_super_clean:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Mock _base_manager.get to raise DoesNotExist
                from django.core.exceptions import ObjectDoesNotExist
                with patch.object(self.instance.__class__, '_base_manager') as mock_base_manager:
                    mock_base_manager.get.side_effect = ObjectDoesNotExist("Instance not found")
                    
                    # Set pk to simulate update operation
                    self.instance.pk = 1
                    
                    self.instance.clean(bypass_hooks=False)
                    
                    # Should call super().clean() and run VALIDATE_CREATE hooks (treat as create)
                    mock_super_clean.assert_called_once()
                    mock_run.assert_called_once_with(
                        self.instance.__class__, 
                        VALIDATE_CREATE, 
                        [self.instance], 
                        ctx=mock_run.call_args[1]['ctx']
                    )
    
    def test_save_with_bypass_hooks(self):
        """Test save method with bypass_hooks=True."""
        # Mock the super().save() method
        with patch.object(HookModelMixin, 'save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Mock _base_manager.save
                with patch.object(self.instance.__class__, '_base_manager') as mock_base_manager:
                    mock_base_manager.save.return_value = self.instance
                    
                    result = self.instance.save(bypass_hooks=True)
                    
                    # Should call _base_manager.save but not run hooks
                    mock_base_manager.save.assert_called_once_with(self.instance)
                    mock_run.assert_not_called()
                    self.assertEqual(result, self.instance)
    
    def test_save_without_bypass_hooks_create(self):
        """Test save method without bypass_hooks for create operation."""
        # Mock the super().save() method
        with patch.object(HookModelMixin, 'save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Set pk to None to simulate create operation
                self.instance.pk = None
                
                result = self.instance.save(bypass_hooks=False)
                
                # Should call super().save() and run BEFORE_CREATE and AFTER_CREATE hooks
                mock_super_save.assert_called_once()
                self.assertEqual(mock_run.call_count, 2)  # BEFORE_CREATE and AFTER_CREATE
                self.assertEqual(result, self.instance)
    
    def test_save_without_bypass_hooks_update(self):
        """Test save method without bypass_hooks for update operation."""
        # Mock the super().save() method
        with patch.object(HookModelMixin, 'save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Mock _base_manager.get to return an old instance
                mock_old_instance = Mock()
                with patch.object(self.instance.__class__, '_base_manager') as mock_base_manager:
                    mock_base_manager.get.return_value = mock_old_instance
                    
                    # Set pk to simulate update operation
                    self.instance.pk = 1
                    
                    result = self.instance.save(bypass_hooks=False)
                    
                    # Should call super().save() and run BEFORE_UPDATE and AFTER_UPDATE hooks
                    mock_super_save.assert_called_once()
                    self.assertEqual(mock_run.call_count, 2)  # BEFORE_UPDATE and AFTER_UPDATE
                    self.assertEqual(result, self.instance)
    
    def test_save_without_bypass_hooks_update_does_not_exist(self):
        """Test save method without bypass_hooks for update when old instance doesn't exist."""
        # Mock the super().save() method
        with patch.object(HookModelMixin, 'save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Mock _base_manager.get to raise DoesNotExist
                from django.core.exceptions import ObjectDoesNotExist
                with patch.object(self.instance.__class__, '_base_manager') as mock_base_manager:
                    mock_base_manager.get.side_effect = ObjectDoesNotExist("Instance not found")
                    
                    # Set pk to simulate update operation
                    self.instance.pk = 1
                    
                    result = self.instance.save(bypass_hooks=False)
                    
                    # Should call super().save() and run BEFORE_CREATE and AFTER_CREATE hooks (treat as create)
                    mock_super_save.assert_called_once()
                    self.assertEqual(mock_run.call_count, 2)  # BEFORE_CREATE and AFTER_CREATE
                    self.assertEqual(result, self.instance)
    
    def test_delete_with_bypass_hooks(self):
        """Test delete method with bypass_hooks=True."""
        # Mock the super().delete() method
        with patch.object(HookModelMixin, 'delete') as mock_super_delete:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Mock _base_manager.delete
                with patch.object(self.instance.__class__, '_base_manager') as mock_base_manager:
                    mock_base_manager.delete.return_value = (1, {'tests.TestModel': 1})
                    
                    result = self.instance.delete(bypass_hooks=True)
                    
                    # Should call _base_manager.delete but not run hooks
                    mock_base_manager.delete.assert_called_once_with(self.instance)
                    mock_run.assert_not_called()
                    self.assertEqual(result, (1, {'tests.TestModel': 1}))
    
    def test_delete_without_bypass_hooks(self):
        """Test delete method without bypass_hooks."""
        # Mock the super().delete() method
        with patch.object(HookModelMixin, 'delete') as mock_super_delete:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                result = self.instance.delete(bypass_hooks=False)
                
                # Should call super().delete() and run all delete hooks
                mock_super_delete.assert_called_once()
                self.assertEqual(mock_run.call_count, 3)  # VALIDATE_DELETE, BEFORE_DELETE, AFTER_DELETE
                self.assertEqual(result, mock_super_delete.return_value)
    
    def test_save_with_args_and_kwargs(self):
        """Test save method passes through args and kwargs."""
        # Mock the super().save() method
        with patch.object(HookModelMixin, 'save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                # Set pk to None to simulate create operation
                self.instance.pk = None
                
                result = self.instance.save(force_insert=True, using='other_db', bypass_hooks=False)
                
                # Should call super().save() with the same args and kwargs
                mock_super_save.assert_called_once_with(force_insert=True, using='other_db')
                self.assertEqual(result, self.instance)
    
    def test_delete_with_args_and_kwargs(self):
        """Test delete method passes through args and kwargs."""
        # Mock the super().delete() method
        with patch.object(HookModelMixin, 'delete') as mock_super_delete:
            # Mock the run function
            with patch('django_bulk_hooks.models.run') as mock_run:
                result = self.instance.delete(using='other_db', bypass_hooks=False)
                
                # Should call super().delete() with the same args and kwargs
                mock_super_delete.assert_called_once_with(using='other_db')
                self.assertEqual(result, mock_super_delete.return_value)
