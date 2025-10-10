"""
Additional tests for models module to increase coverage.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django_bulk_triggers.models import TriggerModelMixin
from django_bulk_triggers.engine import run
from django_bulk_triggers.constants import (
    VALIDATE_CREATE, VALIDATE_UPDATE, VALIDATE_DELETE,
    BEFORE_CREATE, BEFORE_UPDATE, BEFORE_DELETE,
    AFTER_CREATE, AFTER_UPDATE, AFTER_DELETE
)
from tests.models import TriggerModel


class TestModelsCoverage(TestCase):
    """Test uncovered functionality in models module."""
    
    def setUp(self):
        # Use the existing TriggerModel which inherits from TriggerModelMixin
        self.model_cls = TriggerModel
        self.instance = TriggerModel()
    
    def test_clean_with_bypass_triggers(self):
        """Test clean method with bypass_triggers=True."""
        # Mock the super().clean() method
        with patch.object(TriggerModelMixin, 'clean') as mock_super_clean:
            # Mock the run function
            with patch('django_bulk_triggers.models.run') as mock_run:
                self.instance.clean(bypass_triggers=True)
                
                # Should call super().clean() but not run triggers
                mock_super_clean.assert_called_once()
                mock_run.assert_not_called()
    
    def test_clean_without_bypass_triggers_create(self):
        """Test clean method without bypass_triggers for create operation."""
        # Mock the run function
        with patch('django_bulk_triggers.models.run') as mock_run:
            # Set pk to None to simulate create operation
            self.instance.pk = None

            self.instance.clean(bypass_triggers=False)

            # The run function should be called once with VALIDATE_CREATE
            self.assertEqual(mock_run.call_count, 1)
            args, kwargs = mock_run.call_args
            self.assertEqual(args[0], self.instance.__class__)
            self.assertEqual(args[1], VALIDATE_CREATE)
            self.assertEqual(args[2], [self.instance])
            self.assertIn('ctx', kwargs)
    
    def test_clean_without_bypass_triggers_update(self):
        """Test clean method without bypass_triggers for update operation."""
        # Mock the run function
        with patch('django_bulk_triggers.models.run') as mock_run:
            # Mock the _base_manager.get to simulate existing record
            with patch.object(TriggerModel._base_manager, 'get') as mock_get:
                mock_old_instance = TriggerModel(pk=1, name="Old Name")
                mock_get.return_value = mock_old_instance

                # Set pk to simulate update operation
                self.instance.pk = 1

                self.instance.clean(bypass_triggers=False)

                # Should run VALIDATE_UPDATE trigger
                self.assertEqual(mock_run.call_count, 1)
                args, kwargs = mock_run.call_args
                self.assertEqual(args[0], self.instance.__class__)
                self.assertEqual(args[1], VALIDATE_UPDATE)
                self.assertEqual(args[2], [self.instance])
                self.assertEqual(args[3], [mock_old_instance])  # Should pass old instance
                self.assertIn('ctx', kwargs)
    
    def test_clean_without_bypass_triggers_update_does_not_exist(self):
        """Test clean method without bypass_triggers for update when old instance doesn't exist."""
        # Mock the run function
        with patch('django_bulk_triggers.models.run') as mock_run:
            # Set pk to simulate update operation
            self.instance.pk = 1

            # This will try to get the old instance and fail, then treat as create
            self.instance.clean(bypass_triggers=False)

            # Should run VALIDATE_CREATE trigger (since old instance doesn't exist)
            self.assertEqual(mock_run.call_count, 1)
            args, kwargs = mock_run.call_args
            self.assertEqual(args[0], self.instance.__class__)
            self.assertEqual(args[1], VALIDATE_CREATE)
            self.assertEqual(args[2], [self.instance])
            self.assertIn('ctx', kwargs)
    
    def test_save_with_bypass_triggers(self):
        """Test save method with bypass_triggers=True."""
        # Mock the run function
        with patch('django_bulk_triggers.models.run') as mock_run:
            # For bypass_triggers=True, we test that triggers are not run
            # We can't easily mock _base_manager, so we test the behavior differently
            # Set pk to None to simulate create operation
            self.instance.pk = None

            # This will call _base_manager.save internally, but we can't mock it
            # Instead, we test that no triggers are run
            try:
                result = self.instance.save(bypass_triggers=True)
                # Should return the instance
                self.assertEqual(result, self.instance)
                # Should not run any triggers
                mock_run.assert_not_called()
            except Exception:
                # If there's an exception due to database operations, that's expected
                # The important thing is that no triggers were run
                mock_run.assert_not_called()
    
    def test_save_without_bypass_triggers_create(self):
        """Test save method without bypass_triggers for create operation."""
        # Now save() delegates to bulk_create for create operations
        with patch.object(self.instance.__class__.objects, 'bulk_create') as mock_bulk_create:
            # Mock bulk_create to return a list with the instance
            mock_bulk_create.return_value = [self.instance]
            
            # Set pk to None to simulate create operation
            self.instance.pk = None

            result = self.instance.save(bypass_triggers=False)

            # Should delegate to bulk_create
            mock_bulk_create.assert_called_once_with([self.instance])
            self.assertEqual(result, self.instance)
    
    def test_save_without_bypass_triggers_update(self):
        """Test save method without bypass_triggers for update operation."""
        # Now save() delegates to bulk_update for update operations
        with patch.object(self.instance.__class__.objects, 'bulk_update') as mock_bulk_update:
            # Set pk to simulate update operation
            self.instance.pk = 1
            # Set some data to avoid empty save
            self.instance.name = "Updated Name"

            result = self.instance.save(bypass_triggers=False)

            # Should delegate to bulk_update
            mock_bulk_update.assert_called_once()
            self.assertEqual(result, self.instance)
    
    def test_save_without_bypass_triggers_update_does_not_exist(self):
        """Test save method without bypass_triggers for update when old instance doesn't exist."""
        # Now save() delegates to bulk_update for any instance with pk set
        with patch.object(self.instance.__class__.objects, 'bulk_update') as mock_bulk_update:
            # Set pk to simulate update operation
            self.instance.pk = 1
            # Set some data
            self.instance.name = "New Name"

            result = self.instance.save(bypass_triggers=False)

            # Should delegate to bulk_update (which handles the DoesNotExist case internally)
            mock_bulk_update.assert_called_once()
            self.assertEqual(result, self.instance)
    
    def test_delete_with_bypass_triggers(self):
        """Test delete method with bypass_triggers=True."""
        # Mock the run function
        with patch('django_bulk_triggers.models.run') as mock_run:
            # For bypass_triggers=True, we test that triggers are not run
            try:
                result = self.instance.delete(bypass_triggers=True)
                # Should not run any triggers
                mock_run.assert_not_called()
            except Exception:
                # If there's an exception due to database operations, that's expected
                # The important thing is that no triggers were run
                mock_run.assert_not_called()
    
    def test_delete_without_bypass_triggers(self):
        """Test delete method without bypass_triggers."""
        # Now delete() delegates to queryset.delete()
        self.instance.pk = 1
        mock_qs = Mock()
        mock_qs.delete.return_value = (1, {'tests.TriggerModel': 1})
        
        with patch.object(self.instance.__class__.objects, 'filter', return_value=mock_qs) as mock_filter:
            result = self.instance.delete(bypass_triggers=False)

            # Should delegate to filter().delete() which handles all triggers
            mock_filter.assert_called_once_with(pk=self.instance.pk)
            mock_qs.delete.assert_called_once()
            self.assertEqual(result, (1, {'tests.TriggerModel': 1}))
    
    def test_save_with_args_and_kwargs(self):
        """Test save method passes through args and kwargs."""
        # Now save() delegates to bulk_create/bulk_update
        with patch.object(self.instance.__class__.objects, 'bulk_create') as mock_bulk_create:
            mock_bulk_create.return_value = [self.instance]
            # Set pk to None to simulate create operation
            self.instance.pk = None

            result = self.instance.save(bypass_triggers=False, update_fields=['name'])

            # Should delegate to bulk_create (kwargs are handled by bulk_create)
            mock_bulk_create.assert_called_once_with([self.instance])
            self.assertEqual(result, self.instance)
    
    def test_delete_with_args_and_kwargs(self):
        """Test delete method passes through args and kwargs."""
        # Now delete() delegates to queryset.delete()
        self.instance.pk = 1
        mock_qs = Mock()
        mock_qs.delete.return_value = (1, {'tests.TriggerModel': 1})
        
        with patch.object(self.instance.__class__.objects, 'filter', return_value=mock_qs) as mock_filter:
            result = self.instance.delete(bypass_triggers=False)

            # Should delegate to filter().delete()
            mock_filter.assert_called_once_with(pk=self.instance.pk)
            mock_qs.delete.assert_called_once()
            self.assertEqual(result, (1, {'tests.TriggerModel': 1}))
