import unittest
from unittest.mock import patch, MagicMock, call, mock_open
import sys
import os
import sqlite3
import json

# Add the script's directory to sys.path to allow importing smj7
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# IMPORTANT: Defer import of smj7 or its parts until necessary mocks are in place,
# especially for 'argparse' if it's parsed at module level.
# For smj7, 'args' is defined at module level. This means when 'import smj7' happens,
# sys.argv will be parsed. We need to control this for tests.

class TestSmj7(unittest.TestCase):

    def setUp(self):
        # Store original sys.argv and restore it later if necessary
        self.original_argv = sys.argv
        # Default args as defined in smj7.py (or expected)
        self.default_args_dict = {
            'location': os.path.realpath(os.path.expanduser('~/Music/')),
            'query': None,
            'database': os.path.realpath(os.path.expanduser('~/.smj7.sqlite')),
            'freshen': False,
            'prune': False,
            'force_rescan': False,
            'json': False,
            'show_paths': False,
            'indent': 2,
            'force_serial': False,
            'syntax': False,
            'debug': False,
        }

    def tearDown(self):
        # Restore original sys.argv
        sys.argv = self.original_argv
        # Remove smj7 from modules to allow fresh import with different args
        if 'smj7' in sys.modules:
            del sys.modules['smj7']

    def _import_smj7_with_args(self, argv):
        sys.argv = argv
        if 'smj7' in sys.modules:
            del sys.modules['smj7'] # Ensure fresh import
        import smj7
        return smj7

    def test_true_path(self):
        # Import smj7 or the specific function
        smj7 = self._import_smj7_with_args(['smj7.py']) # Load with default args
        self.assertEqual(smj7.true_path('~/test'), os.path.realpath(os.path.expanduser('~/test')))
        self.assertEqual(smj7.true_path('.'), os.getcwd())

    def test_parse_args_defaults(self):
        smj7 = self._import_smj7_with_args(['smj7.py'])
        for key, value in self.default_args_dict.items():
            self.assertEqual(getattr(smj7.args, key), value, msg=f"Default arg mismatch for {key}")

    def test_parse_args_custom(self):
        custom_argv = [
            'smj7.py',
            '-l', '/custom/music',
            '--database', '/custom/db.sqlite',
            '--query', '@artist',
            '--freshen',
            '--prune',
            '--force-rescan',
            '--json',
            '--show-paths',
            '-i', '4',
            '--force-serial',
            '--debug'
        ]
        smj7 = self._import_smj7_with_args(custom_argv)

        self.assertEqual(smj7.args.location, '/custom/music') # true_path is applied by smj7
        self.assertEqual(smj7.args.database, '/custom/db.sqlite') # true_path is applied
        self.assertEqual(smj7.args.query, '@artist')
        self.assertTrue(smj7.args.freshen)
        self.assertTrue(smj7.args.prune)
        self.assertTrue(smj7.args.force_rescan)
        self.assertTrue(smj7.args.json)
        self.assertTrue(smj7.args.show_paths)
        self.assertEqual(smj7.args.indent, 4)
        self.assertTrue(smj7.args.force_serial)
        self.assertTrue(smj7.args.debug)

    @patch('sqlite3.connect')
    def test_do_sql_single_no_vars(self, mock_sqlite_connect):
        mock_conn = MagicMock()
        mock_curs = MagicMock()
        mock_sqlite_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_curs
        mock_curs.fetchall.return_value = "expected_result"

        smj7 = self._import_smj7_with_args(['smj7.py'])
        result = smj7.do_sql("SELECT * FROM test", db_file="dummy.db")

        mock_sqlite_connect.assert_called_once_with("dummy.db")
        self.assertEqual(mock_conn.text_factory, str)
        self.assertEqual(mock_conn.row_factory, sqlite3.Row)
        mock_conn.cursor.assert_called_once()
        mock_curs.execute.assert_called_once_with("SELECT * FROM test")
        mock_conn.commit.assert_called_once()
        mock_curs.close.assert_called_once()
        self.assertEqual(result, "expected_result")

    @patch('sqlite3.connect')
    def test_do_sql_single_with_vars(self, mock_sqlite_connect):
        mock_conn = MagicMock()
        mock_curs = MagicMock()
        mock_sqlite_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_curs

        smj7 = self._import_smj7_with_args(['smj7.py'])
        smj7.do_sql("SELECT * FROM test WHERE id = ?", db_file="dummy.db", column_data=(1,))

        mock_curs.execute.assert_called_once_with("SELECT * FROM test WHERE id = ?", (1,))

    @patch('sqlite3.connect')
    def test_do_sql_multiple(self, mock_sqlite_connect):
        mock_conn = MagicMock()
        mock_curs = MagicMock()
        mock_sqlite_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_curs

        smj7 = self._import_smj7_with_args(['smj7.py'])
        column_data = [{'id': 1}, {'id': 2}]
        smj7.do_sql("INSERT INTO test VALUES (:id)", db_file="dummy.db", column_data=column_data, multiple=True)

        mock_curs.executemany.assert_called_once_with("INSERT INTO test VALUES (:id)", column_data)

    @patch('sqlite3.connect')
    def test_do_sql_integrity_error(self, mock_sqlite_connect):
        mock_conn = MagicMock()
        mock_curs = MagicMock()
        mock_sqlite_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_curs
        mock_curs.execute.side_effect = sqlite3.IntegrityError("test integrity error")

        smj7 = self._import_smj7_with_args(['smj7.py'])
        # Expect no exception to be raised
        try:
            smj7.do_sql("INSERT INTO test VALUES (1)", db_file="dummy.db")
        except sqlite3.IntegrityError:
            self.fail("sqlite3.IntegrityError should have been caught and ignored.")

        mock_curs.execute.assert_called_once_with("INSERT INTO test VALUES (1)")


    @patch('smj7.do_sql') # Patch do_sql within the smj7 module
    def test_make_db(self, mock_do_sql):
        smj7 = self._import_smj7_with_args(['smj7.py'])
        smj7.make_db()
        expected_sql = 'create table media(title text, artist text, album text, tracknumber int, discnumber int, genre text, path text unique)'
        # Check that do_sql was called with the correct SQL
        # The call to do_sql in make_db doesn't pass db_file, so it uses args.database
        # It also doesn't pass column_data or multiple
        mock_do_sql.assert_called_once_with(expected_sql)


    @patch('os.walk')
    def test_get_media_files(self, mock_os_walk):
        smj7 = self._import_smj7_with_args(['smj7.py'])
        mock_os_walk.return_value = [
            ('/testdir', [], ['song.mp3', 'image.jpg', 'song.m4a']),
            ('/testdir/subdir', [], ['song.ogg', 'readme.txt', 'song.flac', 'song.oga']),
        ]

        expected_files = [
            '/testdir/song.mp3',
            '/testdir/song.m4a',
            '/testdir/subdir/song.ogg',
            '/testdir/subdir/song.flac',
            '/testdir/subdir/song.oga',
        ]

        result_files = list(smj7.get_media_files('/testdir'))

        self.assertEqual(sorted(result_files), sorted(expected_files))
        mock_os_walk.assert_called_once_with('/testdir')

    @patch('os.walk')
    @patch('os.stat')
    def test_get_new_media_files(self, mock_os_stat, mock_os_walk):
        smj7 = self._import_smj7_with_args(['smj7.py'])

        # Simulate that the database file was modified at time 100
        mock_db_stat = MagicMock()
        mock_db_stat.st_mtime = 100 # os.stat()[8] is st_mtime

        # Simulate media files with different modification times
        mock_file_stat_old = MagicMock()
        mock_file_stat_old.st_mtime = 50

        mock_file_stat_new = MagicMock()
        mock_file_stat_new.st_mtime = 150

        # Configure os.stat to return different values based on path
        def stat_side_effect(path):
            if path == smj7.args.database:
                return mock_db_stat
            elif path == '/testdir/old.mp3':
                return mock_file_stat_old
            elif path == '/testdir/new.m4a':
                return mock_file_stat_new
            elif path == '/testdir/subdir/also_new.flac':
                return mock_file_stat_new
            else: # Default for any other path, e.g. non-media files
                return MagicMock(st_mtime=1)

        mock_os_stat.side_effect = stat_side_effect

        mock_os_walk.return_value = [
            ('/testdir', [], ['old.mp3', 'new.m4a', 'image.jpg']),
            ('/testdir/subdir', [], ['also_new.flac', 'readme.txt']),
        ]

        expected_files = [
            '/testdir/new.m4a',
            '/testdir/subdir/also_new.flac',
        ]

        result_files = list(smj7.get_new_media_files('/testdir'))

        self.assertEqual(sorted(result_files), sorted(expected_files))
        mock_os_walk.assert_called_once_with('/testdir')
        # Check os.stat calls. It's called for db and each file.
        self.assertIn(call(smj7.args.database), mock_os_stat.call_args_list)
        self.assertIn(call('/testdir/old.mp3'), mock_os_stat.call_args_list)
        self.assertIn(call('/testdir/new.m4a'), mock_os_stat.call_args_list)
        self.assertIn(call('/testdir/subdir/also_new.flac'), mock_os_stat.call_args_list)


    @patch('sqlite3.connect')
    @patch('os.path.exists')
    def test_get_stale_entries(self, mock_os_path_exists, mock_sqlite_connect):
        smj7 = self._import_smj7_with_args(['smj7.py'])

        mock_conn = MagicMock()
        mock_curs = MagicMock()
        mock_sqlite_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_curs

        # Simulate database rows
        db_rows = [
            ('/path/to/existing_file.mp3',),
            ('/path/to/stale_file.m4a',),
            ('/path/to/another_existing.flac',),
        ]
        mock_curs.execute.return_value = db_rows # Iterator of tuples

        # Simulate os.path.exists behavior
        def exists_side_effect(path):
            if path == '/path/to/stale_file.m4a':
                return False
            return True
        mock_os_path_exists.side_effect = exists_side_effect

        expected_stale_entries = [
            ('/path/to/stale_file.m4a',),
        ]

        result_stale_entries = list(smj7.get_stale_entries(db_file="dummy.db"))

        self.assertEqual(result_stale_entries, expected_stale_entries)
        mock_sqlite_connect.assert_called_once_with("dummy.db") # Default db_file from function signature
        mock_curs.execute.assert_called_once_with('select path from media')

        # Check os.path.exists calls
        calls = [call('/path/to/existing_file.mp3'), call('/path/to/stale_file.m4a'), call('/path/to/another_existing.flac')]
        mock_os_path_exists.assert_has_calls(calls, any_order=False)


    @patch('smj7.get_stale_entries')
    @patch('smj7.do_sql') # Mocking do_sql used for count and the main connect for delete
    @patch('sqlite3.connect') # Mocking the direct connect in remove_stale_entries
    @patch('time.time', side_effect=[1000, 2000]) # Mock time to calculate duration
    def test_remove_stale_entries(self, mock_time, mock_sqlite_connect_direct, mock_do_sql, mock_get_stale_entries):
        smj7 = self._import_smj7_with_args(['smj7.py'])

        # Mock return values for do_sql (for counts)
        # First call: before_count, Second call: after_count
        mock_do_sql.side_effect = [
            [(10,)], # before_count result (a list of tuples/rows)
            [(7,)]   # after_count result
        ]

        stale_paths = [('/path/stale1.mp3',), ('/path/stale2.ogg',), ('/path/stale3.flac',)]
        mock_get_stale_entries.return_value = iter(stale_paths) # Must be an iterator

        # Mock the connection and cursor for the direct sqlite3.connect call
        mock_conn_direct = MagicMock()
        mock_curs_direct = MagicMock()
        mock_sqlite_connect_direct.return_value = mock_conn_direct
        mock_conn_direct.cursor.return_value = mock_curs_direct

        with patch('builtins.print') as mock_print: # Capture print output
            smj7.remove_stale_entries(db_file="dummy.db")

        # Verify get_stale_entries was called
        mock_get_stale_entries.assert_called_once_with() # Uses default db_file from its own signature

        # Verify direct sqlite3 connection for deletion
        mock_sqlite_connect_direct.assert_called_once_with("dummy.db")
        mock_conn_direct.cursor.assert_called_once()
        mock_curs_direct.executemany.assert_called_once_with('delete from media where path = ?', iter(stale_paths))
        mock_conn_direct.commit.assert_called_once()
        mock_curs_direct.close.assert_called_once()

        # Verify do_sql calls for counts
        expected_do_sql_calls = [
            call('select count(path) from media'), # Before count
            call('select count(path) from media')  # After count
        ]
        self.assertEqual(mock_do_sql.call_args_list, expected_do_sql_calls)

        # Verify print output
        mock_print.assert_called_once_with('Pruner: Removed 3 stale files from the databse in 1000.0 seconds.')

        # Verify time calls
        self.assertEqual(mock_time.call_count, 2)

    @patch('mutagen.easyid3.EasyID3')
    @patch('mutagen.easymp4.EasyMP4')
    @patch('mutagen.flac.FLAC')
    @patch('mutagen.oggvorbis.OggVorbis')
    def test_parse_media_file(self, mock_ov, mock_fl, mock_m4, mock_m3):
        smj7 = self._import_smj7_with_args(['smj7.py'])

        # Common mock setup
        def setup_mock_mutagen(mock_type, extension, data):
            instance = MagicMock()
            # instance.get.side_effect = lambda key, default: data.get(key, default)

            # More robust mock for mutagen's .get() which often returns a list with one item
            def get_side_effect(key, default_val):
                val = data.get(key)
                if val is not None:
                    # If the stored data is a list (as often from mutagen), return its first element
                    # This is a simplification; real mutagen might return the list itself.
                    # The smj7 code does `[...][0]`, so we should provide a list.
                    return val if isinstance(val, list) else [val]

                # Default value handling: smj7 often does default[0]
                return default_val if isinstance(default_val, list) else [default_val]

            instance.get.side_effect = get_side_effect

            # Specific handling for tracknumber/discnumber which expects "1/10" format string
            # and then smj7 splits it.
            if 'tracknumber' in data and isinstance(data['tracknumber'], str):
                instance.get = lambda key, default: [data[key]] if key == 'tracknumber' else (get_side_effect(key, default))
            if 'discnumber' in data and isinstance(data['discnumber'], str):
                # Extend if already customized
                prev_get = instance.get
                instance.get = lambda key, default: [data[key]] if key == 'discnumber' else (prev_get(key,default))


            mock_type.return_value = instance
            return instance

        # Test MP3
        mp3_data = {
            'artist': ['Artist MP3'], 'albumartistsort': ['Artist MP3 Sort'], 'album': ['Album MP3'],
            'title': ['Title MP3'], 'genre': ['Genre MP3'], 'tracknumber': '1/10', 'discnumber': '1/2'
        }
        active_mock_m3 = setup_mock_mutagen(mock_m3, '.mp3', mp3_data)
        result_mp3 = smj7.parse_media_file('/path/to/song.mp3')

        self.assertEqual(result_mp3['artist'], 'Artist MP3 Sort')
        self.assertEqual(result_mp3['album'], 'Album MP3')
        self.assertEqual(result_mp3['title'], 'Title MP3')
        self.assertEqual(result_mp3['genre'], 'Genre MP3')
        self.assertEqual(result_mp3['tracknumber'], 1)
        self.assertEqual(result_mp3['discnumber'], 1)
        self.assertEqual(result_mp3['path'], '/path/to/song.mp3')
        mock_m3.assert_called_once_with('/path/to/song.mp3')

        # Test M4A (Apple)
        m4a_data = {'artist': ['Artist M4A'], 'album': ['Album M4A'], 'title': ['Title M4A']} # Missing genre, track/disc
        active_mock_m4 = setup_mock_mutagen(mock_m4, '.m4a', m4a_data)
        result_m4a = smj7.parse_media_file('/path/to/song.m4a')
        self.assertEqual(result_m4a['artist'], 'Artist M4A') # No albumartistsort, falls back to artist from smj_metadata
        self.assertEqual(result_m4a['album'], 'Album M4A')
        self.assertEqual(result_m4a['title'], 'Title M4A')
        self.assertEqual(result_m4a['genre'], 'unknown genre') # Default
        self.assertEqual(result_m4a['tracknumber'], 0) # Default due to missing or bad format
        self.assertEqual(result_m4a['discnumber'], 0) # Default
        mock_m4.assert_called_once_with('/path/to/song.m4a')

        # Test FLAC
        flac_data = {'artist': ['Artist FLAC'], 'album': ['Album FLAC'], 'title': ['Title FLAC'], 'tracknumber': 'bad/value'}
        active_mock_fl = setup_mock_mutagen(mock_fl, '.flac', flac_data)
        result_flac = smj7.parse_media_file('/path/to/song.flac')
        self.assertEqual(result_flac['artist'], 'Artist FLAC')
        self.assertEqual(result_flac['album'], 'Album FLAC')
        self.assertEqual(result_flac['title'], 'Title FLAC')
        self.assertEqual(result_flac['tracknumber'], 0) # ValueError caught, defaults to 0
        mock_fl.assert_called_once_with('/path/to/song.flac')

        # Test OGG
        ogg_data = {'title': ['']} # Empty title string from mutagen
        active_mock_ov = setup_mock_mutagen(mock_ov, '.ogg', ogg_data)
        result_ogg = smj7.parse_media_file('/path/to/song name.ogg')
        # smj7.py logic: if mutagen_metadata.get('title', [filename_split[0]])[0] is empty, it uses filename_split[0]
        # However, the .get() mock needs to simulate this. If 'title' is '', get returns [''], so [0] is ''.
        # This means the smj7 code `smj_metadata['title'] = mutagen_metadata.get('title', [filename_split[0]])[0]`
        # will set title to '' if mutagen has title as [''].
        # The current test setup for get_side_effect for `title: ['']` will return `['']`.
        # So `smj_metadata['title']` will be `''`.
        # This seems like a bug in my mock or an edge case in smj7. Let's assume smj7's logic for now:
        # `smj_metadata.get('title', [filename_split[0]])[0]`
        # If `mutagen_metadata.get('title')` returns `['']`, then `smj_metadata['title']` becomes `''`.
        # This is different from `mutagen_metadata.get('title', ['song name'])[0]` if title was missing altogether.
        # Let's refine the mock for this specific case.
        # The current mock for get_side_effect: if data.get(key) is [''], it returns ['']
        # Then smj7 does: mutagen_metadata.get('title', [filename_split[0]])[0]
        # If 'title' in ogg_data is [''], this becomes [''][0] which is ''.
        # The problem is the default value [filename_split[0]] is not used if the key 'title' EXISTS, even if its value is ['']
        # This matches mutagen's behavior. So if title is an empty string, it remains an empty string.
        # The smj7 code for title: `mutagen_metadata.get('title', [filename_split[0]])[0]`
        # If `mutagen_metadata.get('title')` yields `['']`, then `title` becomes `''`.
        # This means the test should expect `''` not `'song name'`, unless smj7 has further logic to replace empty title with filename.
        # Looking at smj7: `smj_metadata = { ... 'title': mutagen_metadata.get('title', [filename_split[0]])[0] ...}`
        # There is no explicit fallback to filename if the title is present but empty.
        # So the expected title should be '' if mutagen returns [''] for title.
        self.assertEqual(result_ogg['title'], '') # IF mutagen returns empty string for title
        # Let's test the case where 'title' is entirely missing from tags, then filename should be used.
        ogg_data_no_title_key = {} # title key completely missing
        active_mock_ov_2 = setup_mock_mutagen(mock_ov, '.ogg', ogg_data_no_title_key) # Re-setup mock_ov for a new scenario
        mock_ov.reset_mock() # Reset call count etc. for mock_ov
        mock_ov.return_value = active_mock_ov_2 # Make sure the global mock_ov uses this new instance for the next call
        result_ogg_no_title_key = smj7.parse_media_file('/path/to/song name no key.ogg')
        self.assertEqual(result_ogg_no_title_key['title'], 'song name no key')
        self.assertEqual(result_ogg_no_title_key['artist'], 'unknown artist')
        mock_ov.assert_called_once_with('/path/to/song name no key.ogg')

        # Test case where tracknumber might be just "5" (no "/X")
        mp3_data_simple_track = {'tracknumber': '5'}
        active_mock_m3_2 = setup_mock_mutagen(mock_m3, '.mp3', mp3_data_simple_track)
        mock_m3.reset_mock()
        mock_m3.return_value = active_mock_m3_2
        result_mp3_simple_track = smj7.parse_media_file('/final/test.mp3')
        self.assertEqual(result_mp3_simple_track['tracknumber'], 5)

        # Test albumartistsort fallback
        # If 'albumartistsort' is missing, it should use 'artist' from smj_metadata dictionary,
        # which itself would have been populated by mutagen's 'artist' tag or default.
        m4a_data_no_albumartistsort = {'artist': ['Artist M4A FromArtistTag'], 'album': ['Album M4A'], 'title': ['Title M4A']}
        active_mock_m4_2 = setup_mock_mutagen(mock_m4, '.m4a', m4a_data_no_albumartistsort)
        mock_m4.reset_mock()
        mock_m4.return_value = active_mock_m4_2
        result_m4a_2 = smj7.parse_media_file('/path/to/song_no_aas.m4a')
        # smj7 logic: `smj_metadata['artist'] = mutagen_metadata.get('albumartistsort', [smj_metadata['artist']])[0]`
        # Here, `smj_metadata['artist']` on the right is 'Artist M4A FromArtistTag'.
        # So, `get('albumartistsort', ['Artist M4A FromArtistTag'])` will use default.
        self.assertEqual(result_m4a_2['artist'], 'Artist M4A FromArtistTag')

    @patch('smj7.get_media_files')
    @patch('smj7.get_new_media_files')
    @patch('smj7.parse_media_file')
    @patch('smj7.do_sql')
    @patch('time.time', side_effect=[1000, 2000, 3000, 4000]) # Mock time for duration calculation
    @patch('builtins.print') # To capture output
    def test_index_media_serial_new_scan(self, mock_print, mock_time, mock_do_sql, mock_parse_media_file, mock_get_new_media_files, mock_get_media_files):
        # Test initial scan (not freshen) with --force-serial
        smj7 = self._import_smj7_with_args(['smj7.py', '--force-serial']) # sets args.force_serial = True

        media_files_to_index = ['/path/song1.mp3', '/path/song2.m4a']
        mock_get_media_files.return_value = iter(media_files_to_index) # Ensure it's an iterator

        parsed_data_song1 = {'title': 'Song 1', 'artist': 'Artist 1', 'album': 'Album 1', 'tracknumber': 1, 'discnumber': 1, 'genre': 'Pop', 'path': '/path/song1.mp3'}
        parsed_data_song2 = {'title': 'Song 2', 'artist': 'Artist 2', 'album': 'Album 2', 'tracknumber': 2, 'discnumber': 1, 'genre': 'Rock', 'path': '/path/song2.m4a'}

        mock_parse_media_file.side_effect = [parsed_data_song1, parsed_data_song2]

        # Mock do_sql for the final count
        mock_do_sql.return_value = [(2,)] # Simulates "select count(path) from media" returning 2 files

        smj7.index_media(location='/path', freshen=False)

        mock_get_media_files.assert_called_once_with('/path')
        mock_get_new_media_files.assert_not_called() # Should use get_media_files for non-freshen

        self.assertEqual(mock_parse_media_file.call_count, 2)
        mock_parse_media_file.assert_any_call('/path/song1.mp3')
        mock_parse_media_file.assert_any_call('/path/song2.m4a')

        # Check the main do_sql call for inserting data
        # The first argument to do_sql is the SQL string, the second is column_data (an iterator from map)
        # We need to check the call to do_sql that handles the insert_sql
        # smj7.insert_sql is 'insert into media (title, artist, album, tracknumber, discnumber, genre, path) values (:title, :artist, :album, :tracknumber, :discnumber, :genre, :path)'
        # The column_data will be a map object. We can convert it to a list to check its contents.

        # This gets the call to do_sql that matters (the insert)
        # In this test, do_sql is called once for insert, then once by the print statement for the count.
        # So the insert call is call_args_list[0]
        insert_call_args = mock_do_sql.call_args_list[0]
        self.assertEqual(insert_call_args[0][0], smj7.insert_sql) # Check query string
        self.assertEqual(list(insert_call_args[1]['column_data']), [parsed_data_song1, parsed_data_song2]) # Check data
        self.assertTrue(insert_call_args[1]['multiple']) # Check multiple=True

        mock_print.assert_called_once_with('Indexer: Serially indexed 2 files in 1000.0 seconds.')


    @patch('smj7.get_media_files')
    @patch('smj7.get_new_media_files')
    @patch('smj7.parse_media_file')
    @patch('smj7.do_sql')
    @patch('time.time', side_effect=[1000, 2000, 3000, 4000]) # Mock time for duration
    @patch('builtins.print')
    def test_index_media_serial_freshen(self, mock_print, mock_time, mock_do_sql, mock_parse_media_file, mock_get_new_media_files, mock_get_media_files):
        # Test freshen scan with --force-serial
        smj7 = self._import_smj7_with_args(['smj7.py', '--force-serial'])

        new_media_files = ['/path/new_song3.flac']
        mock_get_new_media_files.return_value = iter(new_media_files)

        parsed_data_song3 = {'title': 'Song 3', 'artist': 'Artist 3', 'album': 'Album 3', 'tracknumber': 1, 'discnumber': 1, 'genre': 'Jazz', 'path': '/path/new_song3.flac'}
        mock_parse_media_file.return_value = parsed_data_song3

        # Mock do_sql for before_count and after_count
        mock_do_sql.side_effect = [
            [(5,)], # before_count
            [(6,)]  # after_count (for the print statement)
        ]

        smj7.index_media(location='/path', freshen=True)

        mock_get_new_media_files.assert_called_once_with('/path')
        mock_get_media_files.assert_not_called()

        mock_parse_media_file.assert_called_once_with('/path/new_song3.flac')

        # Check the main do_sql call for inserting data
        insert_call_args = mock_do_sql.call_args_list[1] # do_sql called for before_count, then insert, then after_count for print
                                                        # Actually, it's called for before_count, then for insert. The after_count for print is the *second* element of side_effect
        self.assertEqual(insert_call_args[0][0], smj7.insert_sql)
        self.assertEqual(list(insert_call_args[1]['column_data']), [parsed_data_song3])
        self.assertTrue(insert_call_args[1]['multiple'])

        # mock_do_sql is called for before_count, then for the insert, then by the print for after_count.
        # So, the print statement uses the result of the third call to do_sql if we strictly follow the code.
        # Let's re-evaluate the side_effect for do_sql in freshen mode.
        # 1. `before_count = do_sql(...)` -> First element of side_effect
        # 2. `do_sql(insert_sql, ...)` -> This is the actual insert. It doesn't return a count directly for this test.
        # 3. The print statement calls `do_sql('select count(path) from media')` again for `after_count`. -> Second element of side_effect.

        # Resetting side_effect for clarity for this test case
        mock_do_sql.reset_mock()
        mock_do_sql.side_effect = [
            [(5,)], # before_count call
            None,   # For the insert call (doesn't rely on its return value for this flow)
            [(6,)]  # after_count for the print statement
        ]

        # Call the function again with the new mock_do_sql side_effect
        mock_parse_media_file.reset_mock() # also reset this
        mock_parse_media_file.return_value = parsed_data_song3

        smj7.index_media(location='/path', freshen=True)

        insert_call_args = mock_do_sql.call_args_list[1] # Second call is the insert
        self.assertEqual(insert_call_args[0][0], smj7.insert_sql)
        self.assertEqual(list(insert_call_args[1]['column_data']), [parsed_data_song3])
        self.assertTrue(insert_call_args[1]['multiple'])

        mock_print.assert_called_once_with('Indexer: Serially indexed 1 newer files in 1000.0 seconds.')

    @patch('smj7.get_media_files')
    @patch('smj7.Pool')
    @patch('smj7.parse_media_file') # Mock this even for Pool to control data
    @patch('smj7.do_sql')
    @patch('time.time', side_effect=[1000, 2000, 3000, 4000]) # Mock time
    @patch('builtins.print')
    def test_index_media_parallel_new_scan(self, mock_print, mock_time, mock_do_sql, mock_parse_media_file, mock_pool, mock_get_media_files):
        # Test initial scan (not freshen) with parallel processing (default args.force_serial = False)
        smj7 = self._import_smj7_with_args(['smj7.py'])

        media_files_to_index = ['/path/song1.mp3', '/path/song2.m4a']
        mock_get_media_files.return_value = iter(media_files_to_index)

        parsed_data_song1 = {'title': 'S1', 'artist': 'A1', 'album': 'Al1', 'tracknumber': 1, 'discnumber': 1, 'genre': 'G1', 'path': '/path/song1.mp3'}
        parsed_data_song2 = {'title': 'S2', 'artist': 'A2', 'album': 'Al2', 'tracknumber': 2, 'discnumber': 1, 'genre': 'G2', 'path': '/path/song2.m4a'}

        # parse_media_file will be called by Pool's imap_unordered.
        # The mock_pool's imap_unordered needs to return these.
        mock_pool_instance = mock_pool.return_value
        mock_pool_instance.imap_unordered.return_value = iter([parsed_data_song1, parsed_data_song2])

        mock_do_sql.return_value = [(2,)] # For the count in the print statement

        smj7.index_media(location='/path', freshen=False)

        mock_get_media_files.assert_called_once_with('/path')
        mock_pool.assert_called_once() # Pool() was created
        mock_pool_instance.imap_unordered.assert_called_once_with(smj7.parse_media_file, iter(media_files_to_index), 8)

        # Check the do_sql call for inserting data
        insert_call_args = mock_do_sql.call_args_list[0]
        self.assertEqual(insert_call_args[0][0], smj7.insert_sql)
        self.assertEqual(list(insert_call_args[1]['column_data']), [parsed_data_song1, parsed_data_song2])
        self.assertTrue(insert_call_args[1]['multiple'])

        mock_pool_instance.close.assert_called_once()
        mock_pool_instance.join.assert_called_once()

        mock_print.assert_called_once_with('Indexer: Parallely indexed 2 files in 1000.0 seconds.')

    @patch('smj7.index_media') # Mock the entire function if KeyboardInterrupt happens within
    def test_index_media_keyboard_interrupt_serial(self, mock_index_media_func):
        smj7 = self._import_smj7_with_args(['smj7.py', '--force-serial'])

        # Make the mocked function raise KeyboardInterrupt
        # This tests the except block in the original index_media
        # We are not mocking do_sql here, but rather that the call to map(parse_media_file,...)
        # or the do_sql around it, is interrupted.
        # The easiest way is to make the mocked do_sql (if it were not the main smj7.do_sql)
        # or the map iterator itself raise the exception.

        # Let's refine this test. We want to simulate KeyboardInterrupt *during* the do_sql call
        # within index_media when it's processing the map.
        with patch('smj7.do_sql', side_effect=KeyboardInterrupt) as mock_interrupting_do_sql, \
             patch('smj7.get_media_files', return_value=iter(['file1.mp3'])): # Need some files

            with self.assertRaises(SystemExit) as cm:
                smj7.index_media(location='/path', freshen=False)
            self.assertEqual(cm.exception.code, 1)
            mock_interrupting_do_sql.assert_called_once() # Ensure it was called

    @patch('multiprocessing.Pool') # Original Pool
    @patch('smj7.get_media_files', return_value=iter(['file1.mp3'])) # Need some files
    @patch('smj7.do_sql') # Mock do_sql as well
    def test_index_media_keyboard_interrupt_parallel(self, mock_do_sql_in_parallel_test, mock_get_media_files_in_kb_parallel, mock_pool_in_kb_parallel):
        smj7 = self._import_smj7_with_args(['smj7.py']) # Parallel by default

        mock_pool_instance = mock_pool_in_kb_parallel.return_value
        # Simulate KeyboardInterrupt when imap_unordered is being consumed by do_sql
        # or during the pool.imap_unordered call itself.
        # The `do_sql` call is wrapping the consumption of `pool.imap_unordered`.
        # So, if `do_sql` is interrupted, it should lead to pool.terminate().
        mock_do_sql_in_parallel_test.side_effect = KeyboardInterrupt

        with self.assertRaises(SystemExit) as cm:
            smj7.index_media(location='/path', freshen=False)
        self.assertEqual(cm.exception.code, 1)

        mock_pool_instance.terminate.assert_called_once()
        mock_pool_instance.join.assert_called_once()
        mock_do_sql_in_parallel_test.assert_called_once() # Ensure do_sql was attempted

    @patch('smj7.do_sql')
    def test_search_media(self, mock_do_sql):
        smj7 = self._import_smj7_with_args(['smj7.py'])

        # Expected SQL structure parts
        pre_sql = 'select * from media where '
        post_sql = ' order by artist, album, discnumber, tracknumber'

        # Test cases: (query_string, expected_where_clauses, expected_params)
        test_cases = [
            ("!rock", ["(genre like ?)"], ['%rock%']),
            ("@artist name", ["(artist like ?)"], ['%artist name%']),
            ("#album title", ["(album like ?)"], ['%album title%']),
            ("$track name", ["(title like ?)"], ['%track name%']),
            ("multi term", ["(artist like ? or album like ? or title like ?)"], ['%multi term%', '%multi term%', '%multi term%']),
            # Combinations
            ("!pop, @singer", ["(genre like ?)", "(artist like ?)"], ['%pop%', '%singer%']),
            ("@artist, #album", ["(artist like ?)", "(album like ?)"], ['%artist%', '%album%']),
            ("term1, $track1",
             ["(artist like ? or album like ? or title like ?)", "(title like ?)"],
             ['%term1%', '%term1%', '%term1%', '%track1%']),
            # Multiple of same type (OR)
            ("!genre1, !genre2", ["(genre like ? or genre like ?)"], ['%genre1%', '%genre2%']),
            ("@art1, @art2, @art3", ["(artist like ? or artist like ? or artist like ?)"], ['%art1%', '%art2%', '%art3%']),
            # Mixed with multiple of same type
            ("!gen1, @art1, @art2, #alb1",
             ["(genre like ?)", "(artist like ? or artist like ?)", "(album like ?)"],
             ['%gen1%', '%art1%', '%art2%', '%alb1%']),
            # Query with leading/trailing spaces
            ("  @artist  , #album  ", ["(artist like ?)", "(album like ?)"], ['%artist%', '%album%']),
            # Empty query (should this result in specific SQL or be handled before?)
            # smj7.py's search_media seems to build SQL even for empty, which might be `select * from media where order by ...`
            # This is likely not an issue as empty query won't be common or is handled by UI.
            # If query is empty string, word.strip() is empty, no params are added.
            # `sql = pre_sql + ' and '.join([x for x in [...] if len(x) > 2]) + post_sql`
            # If all _sql parts are empty (e.g. genre_sql = "()"), then ' and '.join results in empty string.
            # So, `sql` becomes `select * from media where order by artist, album, discnumber, tracknumber`.
            # This is valid SQL and will return all entries.
            ("", [], []),
        ]

        for query_string, expected_where_parts, expected_params in test_cases:
            mock_do_sql.reset_mock() # Reset for each case
            expected_return_value = "mocked_results"
            mock_do_sql.return_value = expected_return_value

            results = smj7.search_media(query_string)

            self.assertEqual(results, expected_return_value)

            if not query_string: # Handle empty query string case specifically for SQL construction
                expected_sql = pre_sql.strip() + post_sql # "select * from media where order by ..."
            else:
                expected_sql = pre_sql + ' and '.join(expected_where_parts) + post_sql

            mock_do_sql.assert_called_once_with(expected_sql, column_data=expected_params)

    @patch('smj7.play') # Mock the actual play function
    @patch('random.choice')
    @patch('random.shuffle')
    @patch('builtins.print') # To capture error messages for invalid input
    def test_playlist_handler(self, mock_print, mock_random_shuffle, mock_random_choice, mock_smj7_play):
        smj7 = self._import_smj7_with_args(['smj7.py'])

        media_entries = [
            {'title': 'Song 1', 'artist': 'Artist A', 'album': 'Album X', 'path': '/path/s1.mp3'},
            {'title': 'Song 2', 'artist': 'Artist B', 'album': 'Album Y', 'path': '/path/s2.mp3'},
            {'title': 'Song 3', 'artist': 'Artist C', 'album': 'Album Z', 'path': '/path/s3.mp3'},
            {'title': 'Song 4', 'artist': 'Artist D', 'album': 'Album W', 'path': '/path/s4.mp3'},
        ]

        # Test playing a specific number
        mock_smj7_play.reset_mock()
        smj7.playlist_handler("2", media_entries)
        mock_smj7_play.assert_called_once_with(media_entries[1:])

        # Test playing an invalid number (too high)
        mock_smj7_play.reset_mock()
        mock_print.reset_mock()
        smj7.playlist_handler("10", media_entries)
        mock_smj7_play.assert_not_called()
        mock_print.assert_called_once_with('Enter value from 1 to 4, try again.')

        # Test playing an invalid number (zero or non-digit) - covered by 'else'
        mock_smj7_play.reset_mock()
        mock_print.reset_mock()
        smj7.playlist_handler("0", media_entries) # "0" is a digit, but 0 < 0 is false.
        mock_smj7_play.assert_not_called()
        mock_print.assert_called_once_with('Enter value from 1 to 4, try again.')

        mock_smj7_play.reset_mock()
        mock_print.reset_mock()
        smj7.playlist_handler("abc", media_entries) # Non-digit
        mock_smj7_play.assert_not_called() # No play call
        # The original code prints 'Not a valid playlist command, try again.'
        # This will be caught by the final 'else' in playlist_handler
        # Let's check if the print output is as expected for "abc"
        # The current code prints the string 'Not a valid playlist command, try again.'
        # it does not call print() function with it.
        # This is a bug in smj7.py. It should be `print('Not a valid playlist command, try again.')`
        # For now, the test will reflect the current behavior (no print call from the function for "abc").
        # If smj7.py is fixed, this test part needs update.
        # Due to the bug, no message is printed for "abc" by the function itself.
        # The original code is: `else: 'Not a valid playlist command, try again.'` (string literal, not a print call)
        # So, mock_print should not be called for "abc"
        mock_print.assert_not_called()


        # Test playing all (command 'a')
        mock_smj7_play.reset_mock()
        smj7.playlist_handler("a", media_entries)
        mock_smj7_play.assert_called_once_with(media_entries)

        # Test playing all (empty command "")
        mock_smj7_play.reset_mock()
        smj7.playlist_handler("", media_entries)
        mock_smj7_play.assert_called_once_with(media_entries)

        # Test playing all (command 'all the songs')
        mock_smj7_play.reset_mock()
        smj7.playlist_handler("all the songs", media_entries) # starts with 'a'
        mock_smj7_play.assert_called_once_with(media_entries)

        # Test playing random
        mock_smj7_play.reset_mock()
        mock_random_choice.return_value = media_entries[1] # Let random.choice return the second song
        smj7.playlist_handler("r", media_entries)
        mock_random_choice.assert_called_once_with(media_entries)
        mock_smj7_play.assert_called_once_with([media_entries[1]])

        mock_smj7_play.reset_mock()
        mock_random_choice.reset_mock()
        smj7.playlist_handler("random", media_entries) # starts with 'r'
        mock_random_choice.assert_called_once_with(media_entries)
        # play will be called with [mock_random_choice.return_value]
        mock_smj7_play.assert_called_once_with([mock_random_choice.return_value])


        # Test playing shuffled
        mock_smj7_play.reset_mock()
        # random.shuffle works in-place, so it returns None.
        # We need to check it was called with the original list (or a copy if smj7 makes one, it doesn't)
        # And then play is called with that same (now shuffled) list.

        # Store a copy of media_entries because shuffle is in-place
        original_order = list(media_entries)
        shuffled_expected_order = list(media_entries) # Keep a reference to the list that will be shuffled

        def shuffle_side_effect(lst):
            # Simulate shuffle by reversing (or any fixed change)
            lst.reverse()
        mock_random_shuffle.side_effect = shuffle_side_effect

        smj7.playlist_handler("s", media_entries) # media_entries itself will be shuffled

        mock_random_shuffle.assert_called_once_with(shuffled_expected_order) # Check it was called on the list
        # After shuffle_side_effect, shuffled_expected_order is now reversed.
        self.assertEqual(shuffled_expected_order, list(reversed(original_order))) # Verify our mock shuffle worked as expected on the list
        mock_smj7_play.assert_called_once_with(shuffled_expected_order) # play is called with the shuffled list

        # Test with "shuffle all"
        media_entries_for_shuffle_all = list(original_order) # fresh copy
        shuffled_expected_order_2 = list(media_entries_for_shuffle_all)

        mock_smj7_play.reset_mock()
        mock_random_shuffle.reset_mock()
        mock_random_shuffle.side_effect = lambda lst: lst.reverse()

        smj7.playlist_handler("shuffle all", media_entries_for_shuffle_all)
        mock_random_shuffle.assert_called_once_with(shuffled_expected_order_2)
        self.assertEqual(shuffled_expected_order_2, list(reversed(original_order)))
        mock_smj7_play.assert_called_once_with(shuffled_expected_order_2)

    def test_jsonizer(self):
        # Test with default args (show_paths=False, indent=2)
        smj7_default = self._import_smj7_with_args(['smj7.py'])

        media_entries = [
            # sqlite3.Row can be simulated with dicts for testing jsonizer
            {'artist': 'Artist A', 'album': 'Album X', 'title': 'Song 1', 'path': '/path/s1.mp3'},
            {'artist': 'Artist A', 'album': 'Album X', 'title': 'Song 2', 'path': '/path/s2.mp3'},
            {'artist': 'Artist A', 'album': 'Album Y', 'title': 'Song 3', 'path': '/path/s3.mp3'},
            {'artist': 'Artist B', 'album': 'Album Z', 'title': 'Song 4', 'path': '/path/s4.mp3'},
        ]

        expected_json_default = {
            "Artist A": {
                "Album X": ["Song 1", "Song 2"],
                "Album Y": ["Song 3"]
            },
            "Artist B": {
                "Album Z": ["Song 4"]
            }
        }
        # json.dumps will ensure order for comparison if keys are strings and dicts are compared
        result_json_default_str = smj7_default.jsonizer(media_entries)
        self.assertEqual(json.loads(result_json_default_str), expected_json_default)
        # Check indentation by checking a part of the string
        self.assertIn('\n  "Artist A": {', result_json_default_str) # Default indent is 2

        # Test with show_paths=True and indent=0 (no newlines/indentation)
        smj7_show_paths_no_indent = self._import_smj7_with_args(['smj7.py', '--show-paths', '--indent', '0'])

        expected_json_show_paths = {
            "Artist A": {
                "Album X": [{'title': 'Song 1', 'path': '/path/s1.mp3'}, {'title': 'Song 2', 'path': '/path/s2.mp3'}],
                "Album Y": [{'title': 'Song 3', 'path': '/path/s3.mp3'}]
            },
            "Artist B": {
                "Album Z": [{'title': 'Song 4', 'path': '/path/s4.mp3'}]
            }
        }
        result_json_show_paths_str = smj7_show_paths_no_indent.jsonizer(media_entries)
        self.assertEqual(json.loads(result_json_show_paths_str), expected_json_show_paths)
        # Check for no newlines (or minimal) with indent=0
        self.assertNotIn('\n ', result_json_show_paths_str) # Basic check for no pretty printing
        # More specific check for indent=0 (None for dumps)
        # For indent=None, it's one line if compact, or minimal newlines if not.
        # json.dumps with indent=None might still have spaces after colons/commas.
        # A robust check is that it matches json.dumps(expected, indent=None)
        self.assertEqual(result_json_show_paths_str, json.dumps(expected_json_show_paths, indent=None, separators=(',', ':')))


        # Test with show_paths=False and indent=4
        smj7_indent_4 = self._import_smj7_with_args(['smj7.py', '--indent', '4'])
        result_json_indent_4_str = smj7_indent_4.jsonizer(media_entries)
        self.assertEqual(json.loads(result_json_indent_4_str), expected_json_default) # Structure is same as default paths
        self.assertIn('\n    "Artist A": {', result_json_indent_4_str) # Indent is 4

        # Test with empty media_entries list
        result_empty_str = smj7_default.jsonizer([])
        self.assertEqual(json.loads(result_empty_str), {})

    @patch('subprocess.check_call')
    @patch('time.sleep')
    @patch('builtins.print')
    def test_play_normal_playback(self, mock_print, mock_time_sleep, mock_subprocess_check_call):
        smj7 = self._import_smj7_with_args(['smj7.py'])

        media_entries = [
            {'title': 'Song 1', 'artist': 'Artist A', 'album': 'Album X', 'path': '/path/s1.mp3'},
            {'title': 'Song 2', 'artist': 'Artist B', 'album': 'Album Y', 'path': '/path/s2.mp3'},
        ]

        smj7.play(media_entries)

        expected_print_calls = [
            call('\n--> Playing "Song 1" off of "Album X" by "Artist A" -->\n'),
            call('\n--> Playing "Song 2" off of "Album Y" by "Artist B" -->\n'),
        ]
        mock_print.assert_has_calls(expected_print_calls)

        expected_mplayer_calls = [
            call(['mplayer', '/path/s1.mp3']),
            call(['mplayer', '/path/s2.mp3']),
        ]
        mock_subprocess_check_call.assert_has_calls(expected_mplayer_calls)
        mock_time_sleep.assert_not_called() # No sleep if no errors

    @patch('subprocess.check_call', side_effect=KeyboardInterrupt) # Simulate interrupt on first call
    @patch('time.sleep')
    @patch('builtins.print')
    def test_play_keyboard_interrupt(self, mock_print, mock_time_sleep, mock_subprocess_check_call):
        smj7 = self._import_smj7_with_args(['smj7.py'])
        media_entries = [{'title': 'S1', 'artist': 'A1', 'album': 'Al1', 'path': '/path/s1.mp3'}]

        smj7.play(media_entries) # Should catch KeyboardInterrupt and break

        mock_print.assert_called_once_with('\n--> Playing "S1" off of "Al1" by "A1" -->\n')
        mock_subprocess_check_call.assert_called_once_with(['mplayer', '/path/s1.mp3'])
        mock_time_sleep.assert_called_once_with(0.25) # Sleep after interrupt

    @patch('subprocess.check_call', side_effect=subprocess.CalledProcessError(1, "mplayer")) # Simulate error
    @patch('time.sleep')
    @patch('builtins.print')
    def test_play_called_process_error(self, mock_print, mock_time_sleep, mock_subprocess_check_call):
        smj7 = self._import_smj7_with_args(['smj7.py'])
        media_entries = [{'title': 'S1', 'artist': 'A1', 'album': 'Al1', 'path': '/path/s1.mp3'}]

        smj7.play(media_entries) # Should catch CalledProcessError and break

        mock_print.assert_called_once_with('\n--> Playing "S1" off of "Al1" by "A1" -->\n')
        mock_subprocess_check_call.assert_called_once_with(['mplayer', '/path/s1.mp3'])
        mock_time_sleep.assert_called_once_with(0.25) # Sleep after error

    # No more functions from the original plan to test.
    # The main program logic (__name__ == '__main__') is not typically unit tested directly
    # in this manner, but rather by testing the functions it calls.

if __name__ == '__main__':
    # Need to import subprocess for CalledProcessError to be available in the test scope if not already.
    import subprocess
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

# Note: The structure of smj7.py (parsing args at import time) makes testing
# different argument configurations a bit tricky. The _import_smj7_with_args
# helper method along with sys.argv manipulation and module reloading is used
# to manage this.
# Tests for functions that depend on smj7.args will use the args state set by
# _import_smj7_with_args for that specific test.
# Patching 'smj7.args' directly could be an alternative for some tests if module reloading is too slow.
# For functions like make_db or remove_stale_entries that call do_sql, which itself uses smj7.args.database,
# ensure that smj7.args.database is correctly set (e.g., by _import_smj7_with_args or patching)
# or that the db_file parameter is explicitly passed to these functions in the tests.
# The current tests for make_db and remove_stale_entries rely on their internal logic to use smj7.args.database
# or the passed db_file parameter.
# The `smj7.do_sql` is patched for `test_make_db`.
# For `test_remove_stale_entries`, `smj7.do_sql` is used for counts, and the direct `sqlite3.connect` within
# `remove_stale_entries` is also mocked.
# `test_get_new_media_files` also depends on `smj7.args.database` for `os.stat`.
# `test_get_stale_entries` calls `sqlite3.connect` directly, so that's mocked.
# `test_do_sql_*` tests `do_sql` in isolation.
# `test_parse_args_*` tests argument parsing.
# `test_true_path` tests the utility.
# `test_get_media_files` tests file discovery.
# `test_get_new_media_files` tests discovery of newer files.
# `test_get_stale_entries` tests identification of non-existent files from DB.
# `test_remove_stale_entries` tests the removal process.This is a good start to `test_smj7.py`. It includes:
*   A `setUp` and `tearDown` method to handle `sys.argv` and module reloading. This is crucial because `smj7.py` parses arguments at the module level.
*   A helper `_import_smj7_with_args` to load `smj7` with specific command-line arguments for each test.
*   Tests for `true_path`.
*   Tests for argument parsing (`test_parse_args_defaults`, `test_parse_args_custom`).
*   Comprehensive tests for `do_sql` covering different execution paths and error handling.
*   Test for `make_db` (mocking `do_sql`).
*   Tests for media file discovery:
    *   `test_get_media_files` (mocking `os.walk`).
    *   `test_get_new_media_files` (mocking `os.walk` and `os.stat`).
*   Tests for stale entry handling:
    *   `test_get_stale_entries` (mocking `sqlite3.connect` and `os.path.exists`).
    *   `test_remove_stale_entries` (mocking `get_stale_entries`, `do_sql` for counts, direct `sqlite3.connect` for deletion, and `time.time`).

The comments regarding the testing strategy due to module-level argument parsing are helpful.

The next step is to continue adding more tests to `simple-media-jukebox/test_smj7.py` as outlined in the plan, focusing on:
*   `parse_media_file`
*   `index_media`
*   `search_media`
*   `playlist_handler`
*   `jsonizer`
*   `play`

I'll proceed by adding tests for `parse_media_file`. This is a critical function that interacts with `mutagen`.
