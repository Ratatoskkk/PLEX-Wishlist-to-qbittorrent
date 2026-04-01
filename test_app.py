import sys
import os
import unittest
import base64
import json
from unittest.mock import MagicMock, patch

# Stub external dependencies before importing app
sys.modules['dotenv'] = MagicMock()
sys.modules['plexapi'] = MagicMock()
sys.modules['plexapi.myplex'] = MagicMock()
sys.modules['plexapi.server'] = MagicMock()
sys.modules['requests'] = MagicMock()
sys.modules['qbittorrentapi'] = MagicMock()
sys.modules['apscheduler'] = MagicMock()
sys.modules['apscheduler.schedulers'] = MagicMock()
sys.modules['apscheduler.schedulers.background'] = MagicMock()
sys.modules['waitress'] = MagicMock()
sys.modules['pystray'] = MagicMock()
sys.modules['PIL'] = MagicMock()

# Setup mandatory environment variables to pass validation check
os.environ['PLEX_URL'] = 'http://mock'
os.environ['PLEX_TOKEN'] = 'mock'
os.environ['AITHER_API_KEY'] = 'mock'
os.environ['QBITTORRENT_URL'] = 'http://mock'
os.environ['QBITTORRENT_USERNAME'] = 'mock'
os.environ['QBITTORRENT_PASSWORD'] = 'mock'
os.environ['WEB_PASSWORD'] = 'mockpassword'
os.environ['WEB_USERNAME'] = 'admin'

sys.modules['socket'] = MagicMock()

import app
import database

class TestApp(unittest.TestCase):
    def setUp(self):
        self.app = app.app.test_client()
        self.app.testing = True

        # Helper for generating auth headers
        auth_string = 'admin:mockpassword'
        self.valid_auth = {'Authorization': 'Basic ' + base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')}
        self.invalid_auth = {'Authorization': 'Basic ' + base64.b64encode(b'admin:wrongpass').decode('utf-8')}

    def test_require_auth_missing(self):
        response = self.app.get('/api/state')
        self.assertEqual(response.status_code, 401)
        self.assertIn('WWW-Authenticate', response.headers)

    def test_require_auth_invalid(self):
        response = self.app.get('/api/state', headers=self.invalid_auth)
        self.assertEqual(response.status_code, 401)
        self.assertIn('WWW-Authenticate', response.headers)

    @patch('database.get_all_downloads')
    @patch('database.get_system_status')
    def test_get_state_success(self, mock_get_system_status, mock_get_all_downloads):
        mock_get_all_downloads.return_value = [
            {'id': 1, 'title': 'Test Movie 1080p', 'status': 'completed'},
            {'id': 2, 'title': 'Test Show (Season 1) 1080p', 'status': 'pending_approval'}
        ]
        mock_get_system_status.return_value = {
            'last_checked': '2023-10-27T10:00:00',
            'last_error': None
        }

        response = self.app.get('/api/state', headers=self.valid_auth)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        self.assertEqual(len(data['downloads']), 2)
        self.assertEqual(data['pending_count'], 1)
        self.assertIn('Test Show', data['pending_groups'])
        self.assertEqual(len(data['pending_groups']['Test Show']), 1)
        self.assertEqual(data['last_check'], '2023-10-27 10:00:00')
        self.assertIsNone(data['last_error'])

    @patch('database.get_download')
    @patch('database.update_download_status')
    def test_approve_success(self, mock_update_status, mock_get_download):
        mock_get_download.return_value = {'id': 1, 'status': 'pending_approval'}

        response = self.app.post('/api/approve/1', headers=self.valid_auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), {"success": True})
        mock_update_status.assert_called_once_with(1, 'queued')

    @patch('database.get_download')
    @patch('database.update_download_status')
    def test_approve_not_found(self, mock_update_status, mock_get_download):
        mock_get_download.return_value = None

        response = self.app.post('/api/approve/999', headers=self.valid_auth)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.data), {"success": False, "error": "Download not found or not pending"})
        mock_update_status.assert_not_called()

    @patch('database.get_download')
    @patch('database.update_download_status')
    def test_deny_success(self, mock_update_status, mock_get_download):
        mock_get_download.return_value = {'id': 1, 'status': 'pending_approval'}

        response = self.app.post('/api/deny/1', headers=self.valid_auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), {"success": True})
        mock_update_status.assert_called_once_with(1, 'denied')

    @patch('database.get_download')
    @patch('database.update_download_status')
    def test_deny_wrong_status(self, mock_update_status, mock_get_download):
        mock_get_download.return_value = {'id': 1, 'status': 'completed'}

        response = self.app.post('/api/deny/1', headers=self.valid_auth)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.data), {"success": False, "error": "Download not found or not pending"})
        mock_update_status.assert_not_called()

    @patch('database.get_db')
    def test_approve_group_success(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        title = "Test Show"
        response = self.app.post(f'/api/approve_group/{title}', headers=self.valid_auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), {"success": True})
        mock_db.execute.assert_called_once_with(
            "UPDATE downloads SET status = 'queued' WHERE status = 'pending_approval' AND title LIKE ?",
            (f"{title} (%",)
        )
        mock_db.commit.assert_called_once()

    @patch('database.get_db')
    def test_deny_group_success(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        title = "Test Show"
        response = self.app.post(f'/api/deny_group/{title}', headers=self.valid_auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), {"success": True})
        mock_db.execute.assert_called_once_with(
            "UPDATE downloads SET status = 'denied' WHERE status = 'pending_approval' AND title LIKE ?",
            (f"{title} (%",)
        )
        mock_db.commit.assert_called_once()

    @patch('database.get_db')
    def test_clear_history_success(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        response = self.app.post('/api/clear', headers=self.valid_auth)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.data), {"success": True})
        mock_db.execute.assert_called_once_with(
            "DELETE FROM downloads WHERE status NOT IN ('pending_approval', 'downloading', 'queued')"
        )
        mock_db.commit.assert_called_once()

    def test_serve_spa_api_not_found(self):
        response = self.app.get('/api/invalid_endpoint', headers=self.valid_auth)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.data), {"error": "API route not found"})

if __name__ == '__main__':
    unittest.main()
