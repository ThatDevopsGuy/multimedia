#!/usr/bin/env python
'''
===============================================================================

Script:         xyz2aac.py 
Author:         Sebastian Weigand
Email:          sab@sab.systems
Current:        June 2015
Copyright:      2012-2015, Sebastian Weigand
License:        MIT
Description:    A script which converts various audio files to MPEG4/AAC files and
                copies over song metadata, utilizing Apple's CoreAudio
                framework for better AAC quality and speed.
Version:        2.3 (Multiple Input Processing)
Requirements:
    OS:         Mac OS X, v10.5+    [afconvert]
    Platform:   Python 2.6+         [multiprocessing]
    Binaries:   flac                [decoding]
    Python Lib: mutagen             [metadata]

===============================================================================
'''

import os
import sys
import logging
from shutil import rmtree

logger = logging.getLogger('2aac')
console = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] | %(levelname)-8s | %(funcName)20s() | %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)
logger.setLevel(logging.INFO)

# =============================================================================
# Sanity Checking:
# =============================================================================

try:
    import mutagen
    import fnmatch
    import argparse

    from subprocess import call, Popen, PIPE
    from multiprocessing import Pool, cpu_count
    from scandir import walk

except ImportError, e:
    exit('Error: Unable to import requisite modules: %s' % e)


def is_progam_valid(program):
    paths = os.environ["PATH"].split(os.pathsep)

    for path in paths:
        if os.access(os.path.join(path, program), os.X_OK):
            return True
    return False


for program in ['flac', 'afconvert']:
    if not is_progam_valid(program):
        exit('Error: Unable to execute/find "%s" from your PATH.' % program)

afconvert_help_formats = Popen(['afconvert', '-hf'], stderr=PIPE).communicate()[1]

data_formats = [format for format in ['aac', 'aace', 'aacf', 'aach', 'aacl', 'aacp'] if format in afconvert_help_formats]


def fix_path(path):
    return os.path.realpath(os.path.expanduser(path))

# =============================================================================
# Argument Parsing:
# =============================================================================

parser = argparse.ArgumentParser(
    description='Converts FLAC to MPEG4/AAC via CoreAudio and transfers metadata using Mutagen.',
    epilog='Note: Mac OS X v10.5+ is required for HE AAC (aach), and 10.7 is required for HE AAC v2 (aacp).')


parser.add_argument('location',
                    nargs='?',
                    default='.',
                    type=str,
                    help='the location to search for media files [.]')

parser.add_argument('-q', '--quality',
                    type=int,
                    default=75,
                    help='VBR quality, in percent [75]')

parser.add_argument('-b', '--bitrate',
                    type=int,
                    default=128,
                    help='average bitrate, in KB/s [128]')

parser.add_argument('-l', '--lossless',
                    action="store_true",
                    default=False,
                    help='encode in Apple Lossless (ALAC), overrides codec options [no]')

parser.add_argument('-c', '--codec',
                    choices=data_formats,
                    default='aac',
                    help='codec to use, if available on your platform [aac]')

parser.add_argument('--debug',
                    action="store_true",
                    default=False,
                    help='enable debug logging')

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
        exit('Cannot read/write: %s' % location)
else:
    exit('Requested location does not exist: %s' % location)

if args.lossless:
    logger.debug('We will be transcoding into Apple Lossless, matching the quality and sample rate.')
else:
    logger.debug('The following variables have been translated: "bitrate": "%s"; "quality": "%s"; "location": "%s".' % (bitrate, quality, location))

# =============================================================================
# Transcoding:
# =============================================================================

# First create our output directory:
output_location = os.path.join(location, 'converted_audio')
tmp_location = '/tmp/intermediate_audio/'

logger.debug('Will place converted files into: "%s".' % output_location)

for loc in (output_location, tmp_location):
    if not os.path.exists(loc):
        os.mkdir(loc)
        logger.debug('Created "%s".' % loc)

def get_audio_files(location):
    for path, dirs, files in walk(location):
        for f in files:
            if (f.endswith('.m4a') or f.endswith('.mp3') or f.endswith('.flac')) and not f.startswith('.'):
                print 'Got audio file:', f
                yield os.path.join(path, f)


def convert_flac_to_wav(flac_file, wav_file):
    logger.debug('Converting FLAC file to intermediate WAV file: "%s".' % os.path.basename(flac_file))
    call(['flac', '-s', '-f', '-d', flac_file, '-o', wav_file])


def convert_wav_to_aac(wav_file, m4a_file, lossless=args.lossless):
    wav_file_name = os.path.basename(wav_file)
    if args.lossless:
        # TODO: Fix multi-channel audio issues, enable proper conversion:
        # For 5.1 channel FLAC, cannot use soundcheck, must specify chanel layout:
        # call(['afconvert', '-f', 'm4af', '-d', 'alac', '-l',  'MPEG_5_1_A', wav_file, m4a_file])

        logger.debug('Converting "%s" to Apple-lossless M4A.' % wav_file_name)
        call(['afconvert', '-f', 'm4af', '-d', 'alac', '--soundcheck-generate', wav_file, m4a_file])

    else:
        logger.debug('Converting "%s" to a "%s"-B/s, "%s"%% quality "%s"-M4A.' % (wav_file_name, bitrate, quality, codec))
        call(['afconvert', '-f', 'm4af', '-d', codec, '-b',
              str(bitrate), '--src-complexity', 'bats', '-u', 'vbrq', quality,
              '--soundcheck-generate', wav_file, m4a_file])


def convert_audio_to_aac(audio_file, m4a_file):
    logger.debug('Converting "%s" to a "%s"-B/s, "%s"%% quality "%s"-M4A.' % (os.path.basename(audio_file), bitrate, quality, codec))
    call(['afconvert', '-f', 'm4af', '-d', codec, '-b',
          str(bitrate), '--soundcheck-generate', audio_file, m4a_file])


def transfer_metadata(source_file, target_file):

    target_file_name = os.path.basename(target_file)

    # Open the file with "easy tags" to standardize tagging:
    metadata = mutagen.File(source_file, easy=True)
    
    logger.debug('Read metadata from: "%s".' % os.path.basename(source_file))

    valid_keys = ['album', 'albumartist', 'albumartistsort', 'albumsort',
                  'artist', 'artistsort', 'APIC:'
                  'comment', 'composersort', 'covr',
                  'copyright',
                  'date',
                  'description',
                  'discnumber',
                  'genre',
                  'grouping',
                  'musicbrainz_albumartistid',
                  'musicbrainz_albumid',
                  'musicbrainz_albumstatus',
                  'musicbrainz_albumtype',
                  'musicbrainz_artistid',
                  'musicbrainz_trackid',
                  'pictures',
                  'title',
                  'titlesort',
                  'tracknumber']

    for key in metadata.keys():
        if key not in valid_keys:
            del metadata[key]

    m4a_data = mutagen.File(target_file, easy=True)
    m4a_data.update(metadata)
    m4a_data.save()

    logger.debug('Saved initial metadata for "%s".' % target_file_name)

    # Open the file again with extended metadata for album art:
    additional_metadata = mutagen.File(source_file, easy=False)
    m4a_data = mutagen.File(target_file, easy=False)

    if type(additional_metadata) == mutagen.flac.FLAC:
        logger.debug('Examining FLAC metadata for cover art...')
        if hasattr(additional_metadata, 'pictures'):
            logger.debug('Converting FLAC cover art for: "%s"' % target_file_name)
            m4a_data['covr'] = [mutagen.mp4.MP4Cover(pic.data, mutagen.mp4.MP4Cover.FORMAT_JPEG) if 'jpeg' in pic.mime else mutagen.mp4.MP4Cover(pic.data, mutagen.mp4.MP4Cover.FORMAT_PNG) for pic in additional_metadata.pictures]

    elif type(additional_metadata) == mutagen.mp3.MP3:
        logger.debug('Examining MP3/ID3 metadata for cover art...')
        if 'APIC:' in additional_metadata:
            logger.debug('Converting MP3/ID3 cover art for: "%s"' % target_file_name)
            m4a_data['covr'] = [mutagen.mp4.MP4Cover(additional_metadata['APIC:'].data, mutagen.mp4.MP4Cover.FORMAT_JPEG if 'jpeg' in additional_metadata['APIC:'].mime else mutagen.mp4.MP4Cover.FORMAT_PNG)]

    elif type(additional_metadata) == mutagen.mp4.MP4:
        logger.debug('Examining MP4 metadata for cover art...')
        if 'covr' in additional_metadata:
            logger.debug('Converting MP4 cover art for: "%s"' % target_file_name)
            m4a_data['covr'] = additional_metadata['covr']

    m4a_data.save()
    logger.debug('Finalized metadata for: "%s"' % target_file_name)


def process_audio_file(audio_file):

    logger.debug('Began processing: "%s"' % os.path.basename(audio_file))

    if audio_file.endswith('.flac'):
        m4a_file = os.path.join(output_location, os.path.basename(audio_file[:-5])) + '.m4a'
        wav_file = os.path.join(tmp_location, os.path.basename(audio_file[:-5])) + '.wav'
        convert_flac_to_wav(audio_file, wav_file)
        convert_wav_to_aac(wav_file, m4a_file)
        os.remove(wav_file)
        logger.debug('Removed intermediate WAV file: "%s".' % os.path.basename(wav_file))

    else:
        m4a_file = os.path.join(output_location, os.path.basename(audio_file[:-4])) + '.m4a'
        convert_audio_to_aac(audio_file, m4a_file)
    
    transfer_metadata(audio_file, m4a_file)
    
    print 'Finished file:', m4a_file


# =============================================================================
# Main:
# =============================================================================

print 'Processing: %s...' % location

try:
    pool = Pool()
    p = pool.map_async(process_audio_file, get_audio_files(location))
    p.get(0xFFFF)

except KeyboardInterrupt:
    exit('Aborting.')

# Clean-up:
rmtree(tmp_location, ignore_errors=True)

logger.debug('Recursively removed temporary directory: "%s".' % tmp_location)

print 'Done.'

# EOF
