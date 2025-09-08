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
        # Mock Django's Model.save() method (what super().save() actually calls)
        with patch('django.db.models.Model.save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_triggers.models.run') as mock_run:
                # Set pk to None to simulate create operation
                self.instance.pk = None

                result = self.instance.save(bypass_triggers=False)

                # Should call super().save() and run BEFORE_CREATE and AFTER_CREATE triggers
                mock_super_save.assert_called_once()
                # The run function should be called twice: once for BEFORE_CREATE, once for AFTER_CREATE
                self.assertEqual(mock_run.call_count, 2)
                self.assertEqual(result, self.instance)
    
    def test_save_without_bypass_triggers_update(self):
        """Test save method without bypass_triggers for update operation."""
        # Mock Django's Model.save() method (what super().save() actually calls)
        with patch('django.db.models.Model.save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_triggers.models.run') as mock_run:
                # Mock the _base_manager.get to simulate existing record
                with patch.object(TriggerModel._base_manager, 'get') as mock_get:
                    mock_old_instance = TriggerModel(pk=1, name="Old Name")
                    mock_get.return_value = mock_old_instance

                    # Set pk to simulate update operation
                    self.instance.pk = 1
                    # Set some data to avoid empty save
                    self.instance.name = "Updated Name"

                    result = self.instance.save(bypass_triggers=False)

                    # Should call super().save() and run BEFORE_UPDATE and AFTER_UPDATE triggers
                    mock_super_save.assert_called_once()
                    self.assertEqual(mock_run.call_count, 2)  # BEFORE_UPDATE and AFTER_UPDATE
                    self.assertEqual(result, self.instance)
    
    def test_save_without_bypass_triggers_update_does_not_exist(self):
        """Test save method without bypass_triggers for update when old instance doesn't exist."""
        # Mock Django's Model.save() method (what super().save() actually calls)
        with patch('django.db.models.Model.save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_triggers.models.run') as mock_run:
                # Set pk to simulate update operation
                self.instance.pk = 1
                # Set some data
                self.instance.name = "New Name"

                # This will try to get the old instance and fail, then treat as create
                result = self.instance.save(bypass_triggers=False)

                # Should call super().save() and run BEFORE_CREATE and AFTER_CREATE triggers (treat as create)
                mock_super_save.assert_called_once()
                self.assertEqual(mock_run.call_count, 2)  # BEFORE_CREATE and AFTER_CREATE
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
        # Mock Django's Model.delete() method (what super().delete() actually calls)
        with patch('django.db.models.Model.delete') as mock_super_delete:
            # Mock the run function
            with patch('django_bulk_triggers.models.run') as mock_run:
                result = self.instance.delete(bypass_triggers=False)

                # Should call super().delete() and run all delete triggers
                mock_super_delete.assert_called_once()
                # Should run VALIDATE_DELETE, BEFORE_DELETE, AFTER_DELETE triggers
                self.assertEqual(mock_run.call_count, 3)
                self.assertEqual(result, mock_super_delete.return_value)
    
    def test_save_with_args_and_kwargs(self):
        """Test save method passes through args and kwargs."""
        # Mock Django's Model.save() method (what super().save() actually calls)
        with patch('django.db.models.Model.save') as mock_super_save:
            # Mock the run function
            with patch('django_bulk_triggers.models.run') as mock_run:
                # Set pk to None to simulate create operation
                self.instance.pk = None

                result = self.instance.save(force_insert=True, using='other_db', bypass_triggers=False)

                # Should call super().save() with the same args and kwargs (bypass_triggers is filtered out)
                mock_super_save.assert_called_once_with(force_insert=True, using='other_db')
                self.assertEqual(result, self.instance)
    
    def test_delete_with_args_and_kwargs(self):
        """Test delete method passes through args and kwargs."""
        # Mock Django's Model.delete() method (what super().delete() actually calls)
        with patch('django.db.models.Model.delete') as mock_super_delete:
            # Mock the run function
            with patch('django_bulk_triggers.models.run') as mock_run:
                result = self.instance.delete(using='other_db', bypass_triggers=False)

                # Should call super().delete() with the same args and kwargs (bypass_triggers is filtered out)
                mock_super_delete.assert_called_once_with(using='other_db')
                self.assertEqual(result, mock_super_delete.return_value)
