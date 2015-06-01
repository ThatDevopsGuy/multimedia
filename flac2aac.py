#!/usr/bin/env python
'''
===============================================================================
                   ______   ___  _____  ___    ___   ___  _____
                  / __/ /  / _ |/ ___/ |_  |  / _ | / _ |/ ___/
                 / _// /__/ __ / /__  / __/  / __ |/ __ / /__  
                /_/ /____/_/ |_\___/ /____/ /_/ |_/_/ |_\___/
                                   
                                   FLAC 2 AAC
===============================================================================

Script:         flac2aac.py 
Author:         Sebastian Weigand
Email:          sab@sab.systems
Current:        February 2014
Copyright:      2012-2015, Sebastian Weigand
License:        MIT
Description:    A script which converts FLAC files to MPEG4/AAC files and
                copies over song metadata, utilizing Apple's CoreAudio
                framework for better AAC support.
Version:        2.2 (Convert to baseline)
Requirements:
    OS:         Mac OS X, v10.5+    [afconvert]
    Platform:   Python 2.6+         [multiprocessing]
    Binaries:   flac                [decoding]
    Python Lib: mutagen             [metadata]

===============================================================================
'''

import os
import sys
from shutil import rmtree

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

data_formats = [format for format in ['aac', 'aace', 'aacf', 'aach', 'aacl', 'aacp']
                if format in afconvert_help_formats]


def fix_path(path):
    return os.path.realpath(os.path.expanduser(path))

# =============================================================================
# Argument Parsing:
# =============================================================================

parser = argparse.ArgumentParser(
    description='Converts FLAC to MPEG4/AAC via CoreAudio and transfers metadata using Mutagen.',
    epilog='Note: Mac OS X v10.5+ is required for HE AAC (aach), and 10.7 is required for HE AAC v2 (aacp).')


parser.add_argument('location',
                    default=fix_path(os.curdir),
                    type=str,
                    help='the location to search for media files [.]')

parser.add_argument(
    '-l', '--lossless',
    action="store_true",
    default=False,
    help='encode in Apple Lossless (ALAC), overrides codec options [no]')

parser.add_argument('-q', '--quality',
                    type=int,
                    default=75,
                    help='VBR quality, in percent [75]')

parser.add_argument('-c', '--codec',
                    choices=data_formats,
                    default='aac',
                    help='codec to use, if available on your platform [aac]')

parser.add_argument('--abr',
                    action="store_true",
                    default=False,
                    help='use average bitrate, instead of variable [no]')

parser.add_argument('--bitrate',
                    type=int,
                    default=256,
                    help='average bitrate, in KB/s [256]')

parser.add_argument('--baseline',
                    action="store_true",
                    default=False,
                    help='convert both AAC (M4A) and MP3 audio files to AAC with the above quality (ignores --lossless).')

args = parser.parse_args()

# Fix up the arguments:
bitrate = args.bitrate * 1000
quality = str(int(args.quality / 100.0 * 127))
args.location = fix_path(args.location)

# Make sure we've got good paths:
if os.path.isdir(args.location):
    if not os.access(args.location, os.W_OK and os.R_OK):
        exit('Cannot read/write: %s' % args.location)
else:
    exit('Requested location does not exist: %s' % args.location)

# See `afconvert -h` to set the right mode:
if args.abr:
    vbr_mode = 0
else:
    vbr_mode = 3

# =============================================================================
# Transcoding:
# =============================================================================

# First create our output directory:
output_location = os.path.join(args.location, 'converted_audio')
tmp_location = '/tmp/intermediate_audio/'

for loc in (output_location, tmp_location):
    if not os.path.exists(loc):
        os.mkdir(loc)


def get_flac_files(location):
    global file_count
    for path, dirs, files in walk(location):
        for f in files:
            if f.endswith('.flac') and not f.startswith('.'):
                print 'Got FLAC file:', f
                yield os.path.join(path, f)


def get_audio_files(location):
    global file_count
    for path, dirs, files in walk(location):
        for f in files:
            if (f.endswith('.m4a') or f.endswith('.mp3')) and not f.startswith('.'):
                print 'Got audio file:', f
                yield os.path.join(path, f)


def convert_flac_to_wav(flac_file, wav_file):
    call(['flac', '-s', '-f', '-d', flac_file, '-o', wav_file])


def convert_wav_to_aac(wav_file, m4a_file, lossless=args.lossless):
    if args.lossless:
        # TODO: Fix multi-channel audio issues, enable proper conversion:
        # For 5.1 channel FLAC, cannot use soundcheck, must specify chanel layout:
        # call(['afconvert', '-f', 'm4af', '-d', 'alac', '-l',  'MPEG_5_1_A', wav_file, m4a_file])

        call(['afconvert', '-f', 'm4af', '-d', 'alac',
              '--soundcheck-generate', wav_file, m4a_file])
    else:
        call(['afconvert', '-f', 'm4af', '-d', args.codec, '-b',
              str(bitrate), '--src-complexity', 'bats', '-s',
              str(vbr_mode), '-u', 'vbrq', quality,
              '--soundcheck-generate', wav_file, m4a_file])


def convert_readable_audio_to_aac(audio_file, m4a_file):
    call(['afconvert', '-f', 'm4af', '-d', args.codec, '-b',
          str(bitrate), '--soundcheck-generate', audio_file, m4a_file])


def transfer_metadata(source_file, target_file):
    # Open the file with "easy tags" to standardize tagging:
    metadata = mutagen.File(source_file, easy=True)
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

    # Open the file again with extended metadata for album art:
    additional_metadata = mutagen.File(source_file, easy=False)
    m4a_data = mutagen.File(target_file, easy=False)

    if type(additional_metadata) == mutagen.flac.FLAC:
        m4a_data['covr'] = [mutagen.mp4.MP4Cover(pic.data, mutagen.mp4.MP4Cover.FORMAT_JPEG) if 'jpeg' in pic.mime else mutagen.mp4.MP4Cover(pic.data, mutagen.mp4.MP4Cover.FORMAT_PNG) for pic in additional_metadata.pictures]

    elif type(additional_metadata) == mutagen.mp3.MP3:
        m4a_data['covr'] = [mutagen.mp4.MP4Cover(additional_metadata['APIC:'].data, mutagen.mp4.MP4Cover.FORMAT_JPEG if 'jpeg' in additional_metadata['APIC:'].mime else mutagen.mp4.MP4Cover.FORMAT_PNG)]

    elif type(additional_metadata) == mutagen.mp4.MP4:
        m4a_data['covr'] = additional_metadata['covr']

    m4a_data.save()


def process_flac_file(flac_file):
    wav_file = os.path.join(tmp_location, os.path.basename(flac_file[:-5])) + '.wav'
    m4a_file = os.path.join(output_location, os.path.basename(flac_file[:-5])) + '.m4a'

    convert_flac_to_wav(flac_file, wav_file)
    convert_wav_to_aac(wav_file, m4a_file)
    transfer_metadata(flac_file, m4a_file)
    os.remove(wav_file)

    print 'Finished file:', m4a_file


def process_audio_file(audio_file):
    m4a_file = os.path.join(output_location, os.path.basename(audio_file[:-4])) + '.m4a'
    convert_readable_audio_to_aac(audio_file, m4a_file)
    transfer_metadata(audio_file, m4a_file)

    print 'Finished file:', m4a_file


# =============================================================================
# Main:
# =============================================================================

print 'Processing: %s...' % args.location

try:
    pool = Pool()

    if args.baseline:
        p = pool.map_async(process_audio_file, get_audio_files(args.location))
    else:
        p = pool.map_async(process_flac_file, get_flac_files(args.location))
    p.get(0xFFFF)

except KeyboardInterrupt:
    exit('Aborting.')

# Clean-up:
rmtree(tmp_location, ignore_errors=True)

print 'Done.'

# EOF
