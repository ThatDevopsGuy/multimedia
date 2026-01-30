#!/usr/bin/env python3
'''
===============================================================================

Script:         xyz2aac.py
Author:         Sebastian Weigand
Email:          sab@sab.systems
Current:        January 2026
Copyright:      2012-2026, Sebastian Weigand
License:        MIT
Description:    A script which converts various audio files to MPEG4/AAC files and
                copies over song metadata, utilizing Apple's CoreAudio (or ffmpeg)
                framework for better AAC quality and speed.
Version:        3.0 (Multiple Input Processing)
Requirements:
    OS:         Mac OS X, v10.5+    [afconvert]
    Platform:   Python 3.8+         [multiprocessing]
    Binaries:   flac                [decoding]
    Python Lib: mutagen             [metadata]

===============================================================================
'''

import logging
import os
from shutil import rmtree, which
from typing import Set, List, Optional, Any, Generator

logger = logging.getLogger('2aac')
console = logging.StreamHandler()
formatter = logging.Formatter(
    '[%(asctime)s] | %(levelname)-8s | %(funcName)20s() | %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)
logger.setLevel(logging.INFO)

# =============================================================================
# Sanity Checking:
# =============================================================================

try:
    import mutagen
    import argparse

    from subprocess import call, Popen, PIPE
    from multiprocessing import Pool

except ImportError as e:
    exit(f'Error: Unable to import requisite modules: {e}')


def is_program_valid(program: str) -> bool:
    return which(program) is not None


# =============================================================================
# Program Detection:
# =============================================================================

USE_AFCONVERT = False
USE_FFMPEG = False

if is_program_valid('afconvert'):
    USE_AFCONVERT = True
elif is_program_valid('ffmpeg'):
    USE_FFMPEG = True
else:
    exit('Error: Neither "afconvert" nor "ffmpeg" were found in your PATH.')

# Only check for FLAC if we are using afconvert (ffmpeg handles it natively)
if USE_AFCONVERT and not is_program_valid('flac'):
    exit('Error: "flac" is required when using "afconvert" but was not found in your PATH.')

def get_afconvert_codecs() -> Set[str]:
    '''
    Retrieve a set of supported codecs from the `afconvert` command-line utility.

    Returns:
        set: A set of strings representing the supported codecs (e.g., 'aac', 'alac').
    '''
    if not USE_AFCONVERT:
        return set()
    
    try:
        afconvert_help_formats = Popen(
            ['afconvert', '-hf'], stderr=PIPE).communicate()[1]
        
        if isinstance(afconvert_help_formats, bytes):
            afconvert_help_formats = afconvert_help_formats.decode('utf-8', errors='ignore')
            
        # Parse the output to find supported codecs
        # This is a bit heuristic based on the known output format
        codecs = set()
        # Common ones we know we want if they appear
        known_codecs = ['aac', 'aace', 'aacf', 'aach', 'aacl', 'aacp', 'alac', 'flac']
        for codec in known_codecs:
            if codec in afconvert_help_formats:
                codecs.add(codec)
        return codecs
    except Exception as e:
        logger.warning(f'Failed to get afconvert codecs: {e}')
        return set()

def get_ffmpeg_codecs() -> Set[str]:
    '''
    Retrieve a set of supported audio encoders from the `ffmpeg` command-line utility.

    Returns:
        set: A set of strings representing the supported codecs (e.g., 'aac', 'libmp3lame').
    '''
    if not USE_FFMPEG:
        return set()
        
    try:
        # Run ffmpeg -codecs
        output = Popen(['ffmpeg', '-codecs'], stdout=PIPE, stderr=PIPE).communicate()[0]
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='ignore')
            
        codecs = set()
        for line in output.splitlines():
            # Format is like: " DEA.L. aac                  AAC (Advanced Audio Coding)"
            # We want lines where the second character is 'E' (Encoder) and third is 'A' (Audio)
            # Actually checking the flags is safer.
            # Flags are usually first ~6 chars.
            parts = line.strip().split()
            if len(parts) < 2:
                continue
                
            # The first part is flags, second is codec name
            # Sometimes flags are empty or weird, but usually it's "DEV.LS" etc.
            # Let's rely on the position.
            # If the line starts with spaces, split() handles it.
            # But we need to check if it's an encoder and audio.
            
            # Example line: " DEA.L. aac "
            # parts[0] = "DEA.L."
            # parts[1] = "aac"
            
            if len(parts) >= 2 and 'E' in parts[0] and 'A' in parts[0]:
                codecs.add(parts[1])
                
        return codecs
    except Exception as e:
        logger.warning(f'Failed to get ffmpeg codecs: {e}')
        return set()

AFCONVERT_CODECS = get_afconvert_codecs()
FFMPEG_CODECS = get_ffmpeg_codecs()

# Union of all available codecs
data_formats = sorted(list(AFCONVERT_CODECS | FFMPEG_CODECS))

if not data_formats:
    # Fallback if detection fails completely
    data_formats = ['aac']


def fix_path(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


# =============================================================================
# Argument Parsing:
# =============================================================================

parser = argparse.ArgumentParser(
    description=
    'Converts FLAC to MPEG4/AAC via CoreAudio and transfers metadata using Mutagen.',
    epilog=
    'Note: Mac OS X v10.5+ is required for HE AAC (aach), and 10.7 is required for HE AAC v2 (aacp).'
)

parser.add_argument(
    'location',
    nargs='?',
    default='.',
    type=str,
    help='the location to search for media files [.]')

parser.add_argument(
    '-q',
    '--quality',
    type=int,
    default=75,
    help='VBR quality, in percent [75]')

parser.add_argument(
    '-b',
    '--bitrate',
    type=int,
    default=128,
    help='average bitrate, in KB/s [128]')

parser.add_argument(
    '-l',
    '--lossless',
    action="store_true",
    default=False,
    help='encode in Apple Lossless (ALAC), overrides codec options [no]')

parser.add_argument(
    '-c',
    '--codec',
    choices=data_formats,
    default='aac',
    help='codec to use, if available on your platform [aac]')

parser.add_argument(
    '--debug', action="store_true", default=False, help='enable debug logging')

args = parser.parse_args()

if args.debug:
    logger.setLevel(logging.DEBUG)
    logger.debug('Debug mode enabled.')

# Fix up the arguments:
bitrate = args.bitrate * 1000
quality = str(int(args.quality / 100.0 * 127))
location = fix_path(args.location)
codec = args.codec

# Make sure we've got good paths:
if os.path.isdir(location):
    if not os.access(location, os.W_OK and os.R_OK):
        exit(f'Cannot read/write: {location}')
else:
    exit(f'Requested location does not exist: {location}')

if args.lossless:
    logger.debug(
        'We will be transcoding into Apple Lossless, matching the quality and sample rate.'
    )
    if USE_FFMPEG:
        logger.debug('Using FFmpeg for ALAC conversion.')
    else:
        logger.debug('Using afconvert for ALAC conversion.')
else:
    logger.debug(
        f'The following variables have been translated: "bitrate": "{bitrate}"; "quality": "{quality}"; "location": "{location}".')
    if USE_FFMPEG:
        logger.debug('Using FFmpeg for AAC conversion.')
    else:
        logger.debug('Using afconvert for AAC conversion.')

# =============================================================================
# Transcoding:
# =============================================================================

# First create our output directory:
output_location = os.path.join(location, 'converted_audio')
tmp_location = '/tmp/intermediate_audio/'

logger.debug(f'Will place converted files into: "{output_location}".')

for loc in (output_location, tmp_location):
    if not os.path.exists(loc):
        os.mkdir(loc)
        logger.debug(f'Created "{loc}".')


def get_audio_files(location: str) -> Generator[str, None, None]:
    for path, dirs, files in os.walk(location):
        for f in files:
            if (f.endswith('.m4a') or f.endswith('.mp3')
                    or f.endswith('.flac')) and not f.startswith('.'):
                print('Got audio file:', f)
                yield os.path.join(path, f)


def convert_flac_to_wav(flac_file: str, wav_file: str) -> None:
    logger.debug(f'Decoding "{os.path.basename(flac_file)}" to WAV.')
    call(['flac', '-d', flac_file, '-o', wav_file])


def convert_wav_to_aac(wav_file: str, m4a_file: str) -> None:
    wav_file_name = os.path.basename(wav_file)
    if args.lossless:
        # TODO: Fix multi-channel audio issues, enable proper conversion:
        # For 5.1 channel FLAC, cannot use soundcheck, must specify chanel layout:
        # call(['afconvert', '-f', 'm4af', '-d', 'alac', '-l',  'MPEG_5_1_A', wav_file, m4a_file])

        logger.debug(f'Converting "{wav_file_name}" to Apple-lossless M4A.')
        call([
            'afconvert', '-f', 'm4af', '-d', 'alac', '--soundcheck-generate',
            wav_file, m4a_file
        ])

    else:
        logger.debug(f'Converting "{wav_file_name}" to a "{bitrate}"-B/s, "{quality}"% quality "{codec}"-M4A.')
        call([
            'afconvert', '-f', 'm4af', '-d', codec, '-b',
            str(bitrate), '--src-complexity', 'bats', '-u', 'vbrq', quality,
            '--soundcheck-generate', wav_file, m4a_file
        ])


def convert_with_ffmpeg(input_file: str, output_file: str, lossless: bool = args.lossless) -> None:
    '''
    Convert an audio file using FFmpeg.

    Args:
        input_file (str): Path to the input audio file.
        output_file (str): Path to the output file.
        lossless (bool): Whether to encode in ALAC (Apple Lossless) or AAC.
    
    Raises:
        RuntimeError: If the FFmpeg command fails.
    '''
    cmd = ['ffmpeg', '-y', '-i', input_file, '-map_metadata', '0', '-id3v2_version', '3']

    if lossless:
        cmd.extend(['-c:a', 'alac'])
        logger.debug(f'FFmpeg: Converting "{os.path.basename(input_file)}" to ALAC.')
    else:
        # Use the selected codec
        # Note: ffmpeg bitrate is in bits/s, args.bitrate is in KB/s
        cmd.extend(['-c:a', codec, '-b:a', str(bitrate)])
        logger.debug(f'FFmpeg: Converting "{os.path.basename(input_file)}" to {codec} at {bitrate} bps.')

    cmd.append(output_file)
    
    # Run ffmpeg, suppressing output unless debug
    stderr_dest = None if args.debug else PIPE
    p = Popen(cmd, stdout=PIPE, stderr=stderr_dest)
    stdout, stderr = p.communicate()
    
    if p.returncode != 0:
        logger.error(f'FFmpeg failed: {stderr}')
        raise RuntimeError('FFmpeg conversion failed')


def convert_audio_to_aac(audio_file: str, m4a_file: str) -> None:
    '''
    Convert an audio file to AAC/M4A using the best available converter (afconvert or ffmpeg).

    Args:
        audio_file (str): Path to the input audio file.
        m4a_file (str): Path to the output M4A file.
    '''
    # Determine which converter to use based on the selected codec
    # Preference: afconvert > ffmpeg
    
    use_afconvert_for_this = False
    
    if codec in AFCONVERT_CODECS:
        use_afconvert_for_this = True
    elif codec in FFMPEG_CODECS:
        use_afconvert_for_this = False
    else:
        # If codec is not in either (maybe passed manually?), try afconvert if available, else ffmpeg
        if USE_AFCONVERT:
            use_afconvert_for_this = True
        elif USE_FFMPEG:
            use_afconvert_for_this = False
        else:
            exit('Error: No suitable converter found.')

    if not use_afconvert_for_this and USE_FFMPEG:
        convert_with_ffmpeg(audio_file, m4a_file)
        return

    logger.debug(f'Converting "{os.path.basename(audio_file)}" to a "{bitrate}"-B/s, "{quality}"% quality "{codec}"-M4A.')
    call([
        'afconvert', '-f', 'm4af', '-d', codec, '-b',
        str(bitrate), '--soundcheck-generate', audio_file, m4a_file
    ])


def transfer_metadata(source_file: str, target_file: str) -> None:
    '''
    Transfer metadata tags and cover art from the source file to the target file using Mutagen.

    Args:
        source_file (str): Path to the source audio file.
        target_file (str): Path to the target (converted) audio file.
    '''

    target_file_name = os.path.basename(target_file)

    # Open the file with "easy tags" to standardize tagging:
    metadata = mutagen.File(source_file, easy=True)

    logger.debug(f'Read metadata from: "{os.path.basename(source_file)}".')

    valid_keys = [
        'album', 'albumartist', 'albumartistsort', 'albumsort', 'artist',
        'artistsort', 'APIC:'
        'comment', 'composersort', 'covr', 'copyright', 'date', 'description',
        'discnumber', 'genre', 'grouping', 'musicbrainz_albumartistid',
        'musicbrainz_albumid', 'musicbrainz_albumstatus',
        'musicbrainz_albumtype', 'musicbrainz_artistid', 'musicbrainz_trackid',
        'pictures', 'title', 'titlesort', 'tracknumber'
    ]

    for key in list(metadata.keys()):
        if key not in valid_keys:
            del metadata[key]

    m4a_data = mutagen.File(target_file, easy=True)
    m4a_data.update(metadata)
    m4a_data.save()

    logger.debug(f'Saved initial metadata for "{target_file_name}".')

    # Open the file again with extended metadata for album art:
    additional_metadata = mutagen.File(source_file, easy=False)
    m4a_data = mutagen.File(target_file, easy=False)

    if type(additional_metadata) == mutagen.flac.FLAC:
        logger.debug('Examining FLAC metadata for cover art...')
        if hasattr(additional_metadata, 'pictures'):
            logger.debug(f'Converting FLAC cover art for: "{target_file_name}"')
            m4a_data['covr'] = [
                mutagen.mp4.MP4Cover(pic.data,
                                     mutagen.mp4.MP4Cover.FORMAT_JPEG)
                if 'jpeg' in pic.mime else mutagen.mp4.MP4Cover(
                    pic.data, mutagen.mp4.MP4Cover.FORMAT_PNG)
                for pic in additional_metadata.pictures
            ]

    elif type(additional_metadata) == mutagen.mp3.MP3:
        logger.debug('Examining MP3/ID3 metadata for cover art...')
        if 'APIC:' in additional_metadata:
            logger.debug(f'Converting MP3/ID3 cover art for: "{target_file_name}"')
            m4a_data['covr'] = [
                mutagen.mp4.MP4Cover(
                    additional_metadata['APIC:'].data,
                    mutagen.mp4.MP4Cover.FORMAT_JPEG
                    if 'jpeg' in additional_metadata['APIC:'].mime else
                    mutagen.mp4.MP4Cover.FORMAT_PNG)
            ]

    elif type(additional_metadata) == mutagen.mp4.MP4:
        logger.debug('Examining MP4 metadata for cover art...')
        if 'covr' in additional_metadata:
            logger.debug(f'Converting MP4 cover art for: "{target_file_name}"')
            m4a_data['covr'] = additional_metadata['covr']

    m4a_data.save()
    logger.debug(f'Finalized metadata for: "{target_file_name}"')


def process_audio_file(audio_file):
    '''
    Process a single audio file: convert it to AAC/ALAC and transfer metadata.

    Args:
        audio_file (str): Path to the input audio file.
    '''

    logger.debug(f'Began processing: "{os.path.basename(audio_file)}"')

    if audio_file.endswith('.flac'):
        m4a_file = os.path.join(output_location,
                                os.path.basename(audio_file[:-5])) + '.m4a'
        
        if USE_FFMPEG:
            # FFmpeg handles FLAC directly
            convert_with_ffmpeg(audio_file, m4a_file)
        else:
            # afconvert needs WAV
            wav_file = os.path.join(tmp_location, os.path.basename(
                audio_file[:-5])) + '.wav'
            convert_flac_to_wav(audio_file, wav_file)
            convert_wav_to_aac(wav_file, m4a_file)
            os.remove(wav_file)
            logger.debug(f'Removed intermediate WAV file: "{os.path.basename(wav_file)}".')

    else:
        m4a_file = os.path.join(output_location,
                                os.path.basename(audio_file[:-4])) + '.m4a'
        convert_audio_to_aac(audio_file, m4a_file)

    transfer_metadata(audio_file, m4a_file)

    print('Finished file:', m4a_file)


# =============================================================================
# Main:
# =============================================================================

print(f'Processing: {location}...')

try:
    pool = Pool()
    p = pool.map_async(process_audio_file, get_audio_files(location))
    p.get(0xFFFF)

except KeyboardInterrupt:
    exit('Aborting.')

# Clean-up:
rmtree(tmp_location, ignore_errors=True)

logger.debug(f'Recursively removed temporary directory: "{tmp_location}".')

print('Done.')

# EOF
