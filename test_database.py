import unittest
import tempfile
import os
import sqlite3
from datetime import datetime

import database

class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Create a temporary file for the database
        self.db_fd, self.db_path = tempfile.mkstemp()
        # Close the file descriptor so sqlite can use it
        os.close(self.db_fd)
        database.DB_PATH = self.db_path

        # Initialize the database schema
        database.init_db()

    def tearDown(self):
        # Attempt to unlink the temporary file, but don't fail if it's still locked (Windows issue)
        try:
            if os.path.exists(self.db_path):
                os.unlink(self.db_path)
        except PermissionError:
            pass

    def test_get_db(self):
        conn = database.get_db()
        self.assertIsInstance(conn, sqlite3.Connection)
        # Check row factory is set
        self.assertEqual(conn.row_factory, sqlite3.Row)
        conn.close()

    def test_init_db(self):
        # init_db is called in setUp, let's verify tables exist
        conn = database.get_db()
        try:
            # Check downloads table
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='downloads'")
            self.assertIsNotNone(cursor.fetchone())

            # Check system_status table
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_status'")
            self.assertIsNotNone(cursor.fetchone())

            # Check initial system_status row
            cursor = conn.execute("SELECT * FROM system_status WHERE id=1")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertIsNone(row['last_checked'])
        finally:
            conn.close()

    def test_record_download(self):
        params = {
            'title': 'Test Movie',
            'tmdb_id': '12345',
            'file_size_bytes': 1000.0,
            'status': 'queued',
            'aither_torrent_id': '98765',
            'download_link': 'http://example.com/download',
            'resolution': '1080p'
        }

        download_id = database.record_download(params)
        self.assertIsNotNone(download_id)

        # Verify inserted row
        conn = database.get_db()
        try:
            row = conn.execute("SELECT * FROM downloads WHERE id=?", (download_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['title'], 'Test Movie')
            self.assertEqual(row['tmdb_id'], '12345')
            self.assertEqual(row['file_size_bytes'], 1000.0)
            self.assertEqual(row['status'], 'queued')
            self.assertEqual(row['aither_torrent_id'], '98765')
            self.assertEqual(row['download_link'], 'http://example.com/download')
            self.assertEqual(row['resolution'], '1080p')
            self.assertEqual(row['progress'], 0.0)
            self.assertEqual(row['eta_seconds'], -1)
        finally:
            conn.close()

    def test_update_download_status(self):
        params = {
            'title': 'Test Movie',
            'tmdb_id': '12345',
            'file_size_bytes': 1000.0,
            'status': 'queued',
            'aither_torrent_id': '98765',
            'download_link': 'http://example.com/download',
            'resolution': '1080p'
        }
        download_id = database.record_download(params)

        database.update_download_status(download_id, 'downloading')

        conn = database.get_db()
        try:
            row = conn.execute("SELECT status FROM downloads WHERE id=?", (download_id,)).fetchone()
            self.assertEqual(row['status'], 'downloading')
        finally:
            conn.close()

    def test_update_download_progress(self):
        params = {
            'title': 'Test Movie',
            'tmdb_id': '12345',
            'file_size_bytes': 1000.0,
            'status': 'downloading',
            'aither_torrent_id': '98765',
            'download_link': 'http://example.com/download',
            'resolution': '1080p'
        }
        download_id = database.record_download(params)

        database.update_download_progress(download_id, 50.5, 3600)

        conn = database.get_db()
        try:
            row = conn.execute("SELECT progress, eta_seconds FROM downloads WHERE id=?", (download_id,)).fetchone()
            self.assertEqual(row['progress'], 50.5)
            self.assertEqual(row['eta_seconds'], 3600)
        finally:
            conn.close()

    def test_get_all_downloads(self):
        params1 = {
            'title': 'Movie 1',
            'file_size_bytes': 1000.0,
            'status': 'completed',
            'aither_torrent_id': '1'
        }
        params2 = {
            'title': 'Movie 2',
            'file_size_bytes': 2000.0,
            'status': 'denied',
            'aither_torrent_id': '2'
        }
        database.record_download(params1)
        database.record_download(params2)

        downloads = database.get_all_downloads()
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0]['title'], 'Movie 1')

    def test_get_pending_approvals(self):
        params1 = {
            'title': 'Movie 1',
            'file_size_bytes': 1000.0,
            'status': 'pending_approval',
            'aither_torrent_id': '1'
        }
        params2 = {
            'title': 'Movie 2',
            'file_size_bytes': 2000.0,
            'status': 'queued',
            'aither_torrent_id': '2'
        }
        database.record_download(params1)
        database.record_download(params2)

        pending = database.get_pending_approvals()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['title'], 'Movie 1')

    def test_get_next_queued_item(self):
        params1 = {
            'title': 'Movie 1',
            'file_size_bytes': 1000.0,
            'status': 'queued',
            'aither_torrent_id': '1'
        }
        params2 = {
            'title': 'Movie 2',
            'file_size_bytes': 2000.0,
            'status': 'queued',
            'aither_torrent_id': '2'
        }

        database.record_download(params1)
        database.record_download(params2)

        next_item = database.get_next_queued_item()
        self.assertIsNotNone(next_item)
        self.assertEqual(next_item['title'], 'Movie 1')

    def test_get_active_downloads(self):
        params1 = {
            'title': 'Movie 1',
            'file_size_bytes': 1000.0,
            'status': 'downloading',
            'aither_torrent_id': '1'
        }
        params2 = {
            'title': 'Movie 2',
            'file_size_bytes': 2000.0,
            'status': 'queued',
            'aither_torrent_id': '2'
        }
        database.record_download(params1)
        database.record_download(params2)

        active = database.get_active_downloads()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['title'], 'Movie 1')

    def test_get_download(self):
        params = {
            'title': 'Movie 1',
            'file_size_bytes': 1000.0,
            'status': 'queued',
            'aither_torrent_id': '1'
        }
        download_id = database.record_download(params)

        download = database.get_download(download_id)
        self.assertIsNotNone(download)
        self.assertEqual(download['title'], 'Movie 1')

        # Test non-existent download
        self.assertIsNone(database.get_download(999))

    def test_update_last_checked_and_get_system_status(self):
        # Initial state should have NULL last_checked
        status = database.get_system_status()
        self.assertIsNotNone(status)
        self.assertIsNone(status['last_checked'])
        self.assertIsNone(status['last_error'])

        # Update without error
        database.update_last_checked()
        status = database.get_system_status()
        self.assertIsNotNone(status['last_checked'])
        self.assertIsNone(status['last_error'])

        # Update with error
        database.update_last_checked("Connection Failed")
        status = database.get_system_status()
        self.assertIsNotNone(status['last_checked'])
        self.assertEqual(status['last_error'], "Connection Failed")

    def test_is_already_recorded(self):
        params1 = {
            'title': 'Movie 1',
            'file_size_bytes': 1000.0,
            'status': 'completed',
            'aither_torrent_id': '1'
        }
        params2 = {
            'title': 'Movie 2',
            'file_size_bytes': 2000.0,
            'status': 'denied',
            'aither_torrent_id': '2'
        }
        params3 = {
            'title': 'Movie 3',
            'file_size_bytes': 3000.0,
            'status': 'error',
            'aither_torrent_id': '3'
        }
        database.record_download(params1)
        database.record_download(params2)
        database.record_download(params3)

        self.assertTrue(database.is_already_recorded('1'))
        self.assertFalse(database.is_already_recorded('2'))
        self.assertFalse(database.is_already_recorded('3'))
        self.assertFalse(database.is_already_recorded('999'))

if __name__ == '__main__':
    unittest.main()
