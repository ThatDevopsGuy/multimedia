import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the script's directory to sys.path to allow importing xyz2aac
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import the functions and classes from xyz2aac.py
# Note: This will execute xyz2aac.py upon import.
# We need to ensure that argparse.parse_args() is mocked *before* this import
# if we want to control command line arguments for module-level code.
# However, for testing functions, we can call them directly.

class TestXyz2Aac(unittest.TestCase):

    def setUp(self):
        # It's crucial to mock sys.argv before xyz2aac is imported if it parses args at import time.
        # For this structure, we'll assume xyz2aac can be imported and then its functions tested.
        # We will mock parse_args where it's called, or specific functions within xyz2aac.

        # To test functions that rely on 'args' from 'xyz2aac.py', we might need to patch 'xyz2aac.args'
        # or mock 'xyz2aac.parser.parse_args()'

        # Default args as defined in xyz2aac.py
        self.default_args = {
            'location': '.',
            'quality': 75,
            'bitrate': 128,
            'lossless': False,
            'codec': 'aac',
            'debug': False,
        }

    @patch('sys.argv', ['xyz2aac.py'])
    def test_parse_args_defaults(self):
        # Import a fresh version of the module or re-evaluate its argparse section.
        # This is tricky because argparse happens at import time in the original script.
        # A better approach for highly testable scripts is to have main() function that takes argv.

        # For now, let's assume we can import and test the parser object directly
        # or test the 'args' object after import if it's accessible.

        # Since args are parsed at module level in xyz2aac.py, we need to reload the module
        # or specifically call a parsing function if it were refactored.
        # Let's try to import the parser object if possible, or specific functions that use args.

        # Patching xyz2aac.parser.parse_args for the scope of this test
        with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
            # Simulate the default arguments being returned
            mock_parse_args.return_value = argparse.Namespace(**self.default_args)

            # We need to import or re-import xyz2aac or its relevant parts here
            # to make it use the mocked parse_args.
            # This is complex due to the script's structure.
            # A simpler way for this subtask is to assume xyz2aac.py can be imported
            # and we can then inspect its 'args' object or test functions that use it.

            # Let's re-import a fresh copy of xyz2aac or its parser for testing
            # For this example, we'll assume 'xyz2aac.args' is available after import.
            # This requires careful handling of when xyz2aac is imported.

            # If xyz2aac.py is imported at the top of this test file, 'args' is already set.
            # We would need to reload the module under the patch.
            import importlib
            import xyz2aac # Import the module to be tested

            # Reload the module to ensure parse_args is called again
            # This ensures that the module-level 'args = parser.parse_args()' uses the mock
            importlib.reload(xyz2aac)

            self.assertEqual(xyz2aac.args.location, os.path.realpath(os.path.expanduser(self.default_args['location'])))
            self.assertEqual(xyz2aac.args.quality, self.default_args['quality'])
            self.assertEqual(xyz2aac.args.bitrate, self.default_args['bitrate'])
            self.assertEqual(xyz2aac.args.lossless, self.default_args['lossless'])
            self.assertEqual(xyz2aac.args.codec, self.default_args['codec'])
            self.assertEqual(xyz2aac.args.debug, self.default_args['debug'])

    def test_fix_path(self):
        # We need to import the function from the module
        from xyz2aac import fix_path
        self.assertEqual(fix_path('~/test'), os.path.expanduser('~/test'))
        self.assertEqual(fix_path('.'), os.getcwd())

    @patch('scandir.walk')
    def test_get_audio_files(self, mock_walk):
        from xyz2aac import get_audio_files # Import here to use potential mocks

        mock_walk.return_value = [
            ('/testdir', [], ['song.flac', 'image.jpg', '.hidden.mp3']),
            ('/testdir/subdir', [], ['song2.m4a', 'song3.mp3', 'non-audio.txt']),
        ]

        expected_files = [
            '/testdir/song.flac',
            '/testdir/subdir/song2.m4a',
            '/testdir/subdir/song3.mp3',
        ]

        # Before calling get_audio_files, ensure xyz2aac.location is set if the function uses it globally
        # For this test, assume get_audio_files takes location as an argument or we patch the global
        # The function get_audio_files(location) takes location as an argument.

        result_files = list(get_audio_files('/testdir'))

        self.assertEqual(sorted(result_files), sorted(expected_files))
        mock_walk.assert_called_once_with('/testdir')

    @patch('subprocess.call')
    def test_convert_flac_to_wav(self, mock_call):
        from xyz2aac import convert_flac_to_wav
        convert_flac_to_wav('test.flac', 'test.wav')
        mock_call.assert_called_once_with(['flac', '-s', '-f', '-d', 'test.flac', '-o', 'test.wav'])

    @patch('subprocess.call')
    def test_convert_wav_to_aac_lossy(self, mock_call):
        # We need to import or have access to 'args', 'bitrate', 'quality', 'codec' from xyz2aac
        # This means xyz2aac must have been imported and its args parsed.
        # For simplicity, we might need to patch these global variables within xyz2aac for this test.
        import xyz2aac # Ensure it's imported

        # Patch global variables used by convert_wav_to_aac
        with patch('xyz2aac.args') as mock_args, \
             patch('xyz2aac.bitrate', 128000), \
             patch('xyz2aac.quality', '90'), \
             patch('xyz2aac.codec', 'aac'):

            mock_args.lossless = False # Ensure lossy path

            xyz2aac.convert_wav_to_aac('test.wav', 'test.m4a')

            expected_call = [
                'afconvert', '-f', 'm4af', '-d', 'aac', '-b', '128000',
                '--src-complexity', 'bats', '-u', 'vbrq', '90',
                '--soundcheck-generate', 'test.wav', 'test.m4a'
            ]
            mock_call.assert_called_once_with(expected_call)

    @patch('subprocess.call')
    def test_convert_wav_to_aac_lossless(self, mock_call):
        import xyz2aac
        with patch('xyz2aac.args') as mock_args:
            mock_args.lossless = True # Ensure lossless path

            xyz2aac.convert_wav_to_aac('test.wav', 'test.m4a')

            expected_call = [
                'afconvert', '-f', 'm4af', '-d', 'alac',
                '--soundcheck-generate', 'test.wav', 'test.m4a'
            ]
            mock_call.assert_called_once_with(expected_call)

    @patch('subprocess.call')
    def test_convert_audio_to_aac(self, mock_call):
        import xyz2aac
        with patch('xyz2aac.bitrate', 256000), \
             patch('xyz2aac.quality', '100'), \
             patch('xyz2aac.codec', 'aach'):

            xyz2aac.convert_audio_to_aac('test.mp3', 'test.m4a')
            expected_call = [
                'afconvert', '-f', 'm4af', '-d', 'aach', '-b', '256000',
                '--soundcheck-generate', 'test.mp3', 'test.m4a'
            ]
            mock_call.assert_called_once_with(expected_call)

    @patch('mutagen.File')
    def test_transfer_metadata_flac(self, mock_mutagen_file):
        import xyz2aac # for transfer_metadata
        import mutagen # for specific types if needed

        # Mock source file metadata (FLAC)
        mock_source_meta = MagicMock(spec=mutagen.flac.FLAC)
        mock_source_meta.easy = True # for initial call
        mock_source_meta.keys.return_value = ['artist', 'album', 'title', 'genre', 'date', 'tracknumber', 'comment', 'covr'] # 'covr' will be handled by non-easy part

        # Simulate easy tags
        mock_source_meta_easy_dict = {
            'artist': ['Test Artist'], 'album': ['Test Album'], 'title': ['Test Title'],
            'genre': ['Test Genre'], 'date': ['2023'], 'tracknumber': ['1/10'], 'comment': ['Test Comment']
        }
        mock_source_meta.__getitem__.side_effect = lambda key: mock_source_meta_easy_dict[key]

        # Mock target file (M4A)
        mock_target_meta = MagicMock(spec=mutagen.mp4.MP4)
        mock_target_meta.easy = True

        # Mock the picture object for FLAC
        mock_picture = MagicMock(spec=mutagen.flac.Picture)
        mock_picture.data = b'imagedata'
        mock_picture.mime = 'image/jpeg'

        # Second call to mutagen.File for non-easy version (source)
        mock_source_meta_non_easy = MagicMock(spec=mutagen.flac.FLAC)
        mock_source_meta_non_easy.pictures = [mock_picture]

        # Second call to mutagen.File for non-easy version (target)
        mock_target_meta_non_easy = MagicMock(spec=mutagen.mp4.MP4)

        def mutagen_file_side_effect(filename, easy=False):
            if filename == 'source.flac':
                if easy:
                    return mock_source_meta
                else:
                    # This is the second call for source.flac (easy=False)
                    return mock_source_meta_non_easy
            elif filename == 'target.m4a':
                if easy:
                    return mock_target_meta
                else:
                    # This is the second call for target.m4a (easy=False)
                    return mock_target_meta_non_easy
            raise FileNotFoundError(f"Unexpected file: {filename}")

        mock_mutagen_file.side_effect = mutagen_file_side_effect

        # Mock MP4Cover
        with patch('mutagen.mp4.MP4Cover') as mock_mp4_cover:
            mock_mp4_cover.return_value = "mocked_cover_object"

            xyz2aac.transfer_metadata('source.flac', 'target.m4a')

            # Check easy tags transfer
            mock_target_meta.update.assert_called_once()
            args_update, _ = mock_target_meta.update.call_args
            # self.assertEqual(args_update[0]['artist'], ['Test Artist']) # Example check
            mock_target_meta.save.assert_called_once() # First save (easy tags)

            # Check cover art transfer
            mock_mp4_cover.assert_called_once_with(b'imagedata', mutagen.mp4.MP4Cover.FORMAT_JPEG)
            self.assertEqual(mock_target_meta_non_easy['covr'], ["mocked_cover_object"])

            # Ensure save is called on the non-easy m4a_data object
            mock_target_meta_non_easy.save.assert_called_once()


    @patch('xyz2aac.convert_flac_to_wav')
    @patch('xyz2aac.convert_wav_to_aac')
    @patch('xyz2aac.transfer_metadata')
    @patch('os.remove')
    def test_process_audio_file_flac(self, mock_os_remove, mock_transfer_metadata,
                                     mock_convert_wav_to_aac, mock_convert_flac_to_wav):
        import xyz2aac # for process_audio_file and output_location, tmp_location

        # Ensure output_location and tmp_location are set as the function expects
        # These are global in xyz2aac.py. We can patch them if they are not constant.
        # For this test, assume they are defined as in the script.
        # xyz2aac.output_location = '/test_output'
        # xyz2aac.tmp_location = '/test_tmp'
        # It's better if these are passed or configured cleanly.
        # If they are fixed strings in the module, we can use them.

        # We need to ensure xyz2aac.output_location and xyz2aac.tmp_location are defined.
        # If xyz2aac.py was imported, they should be.
        # Let's assume they are:
        # xyz2aac.output_location = 'converted_audio' # As per script
        # xyz2aac.tmp_location = '/tmp/intermediate_audio/' # As per script

        test_flac_file = 'test_song.flac'
        base_name = 'test_song'
        expected_m4a = os.path.join(xyz2aac.output_location, base_name + '.m4a')
        expected_wav = os.path.join(xyz2aac.tmp_location, base_name + '.wav')

        xyz2aac.process_audio_file(test_flac_file)

        mock_convert_flac_to_wav.assert_called_once_with(test_flac_file, expected_wav)
        mock_convert_wav_to_aac.assert_called_once_with(expected_wav, expected_m4a)
        mock_os_remove.assert_called_once_with(expected_wav)
        mock_transfer_metadata.assert_called_once_with(test_flac_file, expected_m4a)

    @patch('xyz2aac.convert_audio_to_aac')
    @patch('xyz2aac.transfer_metadata')
    def test_process_audio_file_other(self, mock_transfer_metadata, mock_convert_audio_to_aac):
        import xyz2aac

        test_mp3_file = 'test_song.mp3'
        base_name = 'test_song'
        expected_m4a = os.path.join(xyz2aac.output_location, base_name + '.m4a')

        xyz2aac.process_audio_file(test_mp3_file)

        mock_convert_audio_to_aac.assert_called_once_with(test_mp3_file, expected_m4a)
        mock_transfer_metadata.assert_called_once_with(test_mp3_file, expected_m4a)


if __name__ == '__main__':
    # Need to import argparse here for the mock_parse_args.return_value to use it
    import argparse
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

# Note on running tests:
# Due to the script structure (arg parsing at import time), running this test file directly
# might be complex without refactoring xyz2aac.py (e.g. to have a main(argv) function).
# The test_parse_args_defaults method is particularly sensitive to this.
# The other tests assume that `xyz2aac.args` (and derived globals like `bitrate`, `quality`, `codec`)
# are either patched during the test or that the module's default argparse values are acceptable.
# For `test_parse_args_defaults`, `importlib.reload(xyz2aac)` is used to try and re-trigger parsing
# under the mock's context.
