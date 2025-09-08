"""
Additional tests for manager module to increase coverage.
"""

from unittest.mock import Mock, patch
from django.test import TestCase
from django_bulk_triggers.manager import BulkTriggerManager
from tests.models import TriggerModel


class TestManagerCoverage(TestCase):
    """Test uncovered functionality in manager module."""
    
    def setUp(self):
        self.manager = BulkTriggerManager()
        self.manager.model = TriggerModel
    
    def test_get_queryset_with_existing_trigger_queryset(self):
        """Test get_queryset when base queryset already has trigger functionality."""
        # Mock the base queryset that will be returned by super().get_queryset()
        mock_base_qs = Mock()
        mock_base_qs.model = TriggerModel

        # Mock the super().get_queryset() call to return our mock queryset
        with patch('django_bulk_triggers.manager.super') as mock_super:
            mock_super_instance = Mock()
            mock_super_instance.get_queryset.return_value = mock_base_qs
            mock_super.return_value = mock_super_instance

            # Mock isinstance to return True for our mock queryset
            with patch('django_bulk_triggers.manager.isinstance', return_value=True) as mock_isinstance:
                result = self.manager.get_queryset()

                # Should return the base queryset as-is when isinstance returns True
                self.assertEqual(result, mock_base_qs)
                mock_isinstance.assert_called_once()
    
    def test_save_with_existing_pk(self):
        """Test save method with existing object."""
        # Create a mock object with existing PK and _meta.fields
        mock_obj = Mock()
        mock_obj.pk = 1

        # Mock _meta.fields to simulate Django model fields
        mock_field1 = Mock()
        mock_field1.name = 'name'
        mock_field2 = Mock()
        mock_field2.name = 'id'
        mock_field3 = Mock()
        mock_field3.name = 'value'

        mock_obj._meta.fields = [mock_field1, mock_field2, mock_field3]

        # Mock the bulk_update method
        with patch.object(self.manager, 'bulk_update') as mock_bulk_update:
            mock_bulk_update.return_value = 1

            result = self.manager.save(mock_obj)

            # Should call bulk_update (fields are auto-detected)
            mock_bulk_update.assert_called_once_with([mock_obj])
            self.assertEqual(result, mock_obj)
    
    def test_save_with_new_object(self):
        """Test save method with new object."""
        # Create a mock object without PK
        mock_obj = Mock()
        mock_obj.pk = None

        # Mock the bulk_create method
        with patch.object(self.manager, 'bulk_create') as mock_bulk_create:
            mock_bulk_create.return_value = [mock_obj]

            result = self.manager.save(mock_obj)

            # Should call bulk_create
            mock_bulk_create.assert_called_once()
            # save method returns the object itself, not a count
            self.assertEqual(result, mock_obj)
    
    def test_save_with_error_handling(self):
        """Test save method error handling."""
        # Create a mock object
        mock_obj = Mock()
        mock_obj.pk = None
        
        # Mock bulk_create to raise an exception
        with patch.object(self.manager, 'bulk_create', side_effect=Exception("Save failed")):
            with self.assertRaises(Exception):
                self.manager.save(mock_obj)
    
    def test_bulk_create_delegation(self):
        """Test bulk_create delegates to queryset."""
        objs = [Mock(), Mock()]
        
        with patch.object(self.manager, 'get_queryset') as mock_get_qs:
            mock_qs = Mock()
            mock_qs.bulk_create.return_value = objs
            mock_get_qs.return_value = mock_qs
            
            result = self.manager.bulk_create(objs, batch_size=100)
            
            # Should delegate to queryset
            mock_qs.bulk_create.assert_called_once()
            self.assertEqual(result, objs)
    
    def test_bulk_update_delegation(self):
        """Test bulk_update delegates to queryset."""
        objs = [Mock(), Mock()]
        fields = ['name', 'value']
        
        with patch.object(self.manager, 'get_queryset') as mock_get_qs:
            mock_qs = Mock()
            mock_qs.bulk_update.return_value = 2
            mock_get_qs.return_value = mock_qs
            
            result = self.manager.bulk_update(objs, fields)
            
            # Should delegate to queryset
            mock_qs.bulk_update.assert_called_once()
            self.assertEqual(result, 2)
    
    def test_bulk_delete_delegation(self):
        """Test bulk_delete delegates to queryset."""
        objs = [Mock(), Mock()]
        
        with patch.object(self.manager, 'get_queryset') as mock_get_qs:
            mock_qs = Mock()
            mock_qs.bulk_delete.return_value = 2
            mock_get_qs.return_value = mock_qs
            
            result = self.manager.bulk_delete(objs)
            
            # Should delegate to queryset
            mock_qs.bulk_delete.assert_called_once()
            self.assertEqual(result, 2)
    
    def test_delete_delegation(self):
        """Test delete delegates to queryset."""
        with patch.object(self.manager, 'get_queryset') as mock_get_qs:
            mock_qs = Mock()
            mock_qs.delete.return_value = (2, {'tests.TriggerModel': 2})
            mock_get_qs.return_value = mock_qs
            
            result = self.manager.delete()
            
            # Should delegate to queryset
            mock_qs.delete.assert_called_once()
            self.assertEqual(result, (2, {'tests.TriggerModel': 2}))
    
    def test_update_delegation(self):
        """Test update delegates to queryset."""
        with patch.object(self.manager, 'get_queryset') as mock_get_qs:
            mock_qs = Mock()
            mock_qs.update.return_value = 2
            mock_get_qs.return_value = mock_qs
            
            result = self.manager.update(name="Updated")
            
            # Should delegate to queryset
            mock_qs.update.assert_called_once_with(name="Updated")
            self.assertEqual(result, 2)
