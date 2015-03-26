#!/usr/bin/env python
# coding: utf-8
# smj7.py | The Simple Media Jukebox, version 7
# Copyright 2010-2012 Sebastian Weigand
# Licensed under the MIT license

# ==============================================================================
# Imports:
# ==============================================================================

# Pythonic supplicants:
import os
import sys
from time import time, sleep
from subprocess import *
import scandir
import itertools
import multiprocessing
import logging
import argparse
import json

import random

# Datastore:
import sqlite3

# Metadata handling:
from mutagen.easymp4 import EasyMP4 as m4
from mutagen.easyid3 import EasyID3 as m3
from mutagen.flac import FLAC as fl
from mutagen.oggvorbis import OggVorbis as ov

# ==============================================================================
# Initialization
# ==============================================================================

# This sys reloading is needed to handle logger output of UTF-8 strings:
reload(sys)
sys.setdefaultencoding('utf8')

logger = logging.getLogger('smj7')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] | %(levelname)-8s | %(funcName)20s() | %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


def true_path(path):
    return os.path.realpath(os.path.expanduser(path))

parser = argparse.ArgumentParser(
    description='A simple command-line media indexer and jukebox.',
    epilog='Note: mplayer is required to play files.')

parser.add_argument('-l', '--location', default=true_path('~/Music/iTunes/iTunes Media/Music/'),
                    type=str, help='the location to search for media files [~/Music]')

parser.add_argument('-Q', '--smj-query', type=str,
                    help='input an SMJ7-style query, followed by playlist commands, and disable interactive mode (see --syntax)')

parser.add_argument('--database', default=true_path('~/.smj7.sqlite'),
                    type=str, help='the location to store the media database [~/.smj/smj7.sqlite]')

#parser.add_argument('--freshen', action="store_true", default=False, help='search for new files and scan them, and remove stale files from the database, useful when adding new albums')

parser.add_argument('--rescan', action="store_true", default=False,
                    help='rescan every file in the database, overwriting old entries (does not freshen), useful when metadata has been updated (think Musicbrainz)')

parser.add_argument('--force-complete-scan', action="store_true", default=False,
                    help='nuke the database and start from scratch, useful when a lot has changed since the last scan')

parser.add_argument('--json', action="store_true", default=False,
                    help='skip playback and interactive selection, just output matching results in JSON')

parser.add_argument('--force-serial', action="store_true", default=False,
                    help='disable parallelized media parsing, useful for slower machines or older mechanical hard disk drives')

parser.add_argument('--syntax', action="store_true", default=False,
                    help='show SMJ7-sylte syntax guide')

parser.add_argument('-d', '--debug', action="store_true", default=False,
                    help='enable debug mode')

args = parser.parse_args()

if args.debug:
    ch.setLevel(logging.DEBUG)

if args.syntax:
    print '''

# SMJ7-Style Syntax

SMJ7 supports a new syntax for chaining queries together using single-character notation.
You can combine multiple parameters; like-type parameters will be logically ORed and
unlike-type parameters will be logically ANDed together.

!<some string>                      - Search for genres matching the string
@<some string>                      - Search for artists matching the string
#<some string>                      - Search for albums matching the string
$<some string>                      - Search for tracks matching the string
<some string>                       - Search for artists, albums, or tracks matching the string

## Combinations

Parameters are comma-separated, and combined logically as mentioned above. All strings are
searched case-insensitively and will match on partial hits.

@artist1, @artist2                  - Would search for any songs by either artist1 or artist2
@artist1, #album1                   - Would search for any albums with "albums1" in it by any artist with "artist1" in it.
something1                          - Would search for anything matching "something1", in any field
something1, $track1                 - Would search for any tracks matching "track1" that have "something1" related to them

## Common Uses

term1, term2, term3                 - Keep searching everything until the additional terms yield the specificity you wish
@artist1, @artist2, #greatest hits  - Play the "Greatest Hits" albums by both artist1 and artist2
@artist, #album, $tracknumber       - Play a specific track off of a specific album, useful when live albums exist alongside

## Examples

@mingus, @coltrane, @brubeck        - Would play some assorted jazz tracks by these 3 artists
@rolling stones, #greatest          - Would match "Greatest Hits" by "The Rolling Stones"
@decemberists, #live, $infanta      - Would play the live version of "Infanta" by "The Decemberists"

## Playlist post-commands

When invoking from the command line, you should encapsulate your SMJ7-style query in quotes, so that your shell can pass it here properly.

To add playlist commands, simply append a semicolon ";" to your query and follow it with one of:

#                                   - Play the #th song
a                                   - Play all matching songs
r                                   - Play a single, random matching song
s                                   - Play all matching songs, shuffled

### Examples of SMJ7-style query plus commands:

./smj7.py -Q "@rolling stones, #greatest; a" - Plays all songs matching the query
./smj7.py -Q "@decemberists, #live; s"       - Plays all songs matching the query, in a random order

'''

# Fix up some parameters:
args.location = true_path(args.location)
args.database = true_path(args.database)

if args.force_complete_scan:
    args.rescan = True


def do_sql(query, db_file=args.database, column_data=None, multiple=False):
    conn = sqlite3.connect(db_file)
    conn.text_factory = str
    conn.row_factory = sqlite3.Row
    curs = conn.cursor()

    try:
        if multiple:
            logger.debug('Received executemany SQL transaction for "%s": "%s" with variables.' % (db_file, query))
            curs.executemany(query, column_data)

        elif column_data is not None:
            logger.debug('Received single variable-based SQL transaction for "%s": "%s" with variables.' %
                         (db_file, query))
            curs.execute(query, column_data)

        else:
            logger.debug('Received single SQL transaction for "%s": "%s"' % (db_file, query))
            curs.execute(query)

    except sqlite3.IntegrityError:
        logger.debug('Ignoring IntegrityError and overwriting previous values.')
        pass

    response = curs.fetchall()

    conn.commit()
    curs.close()

    return response


def make_db():
    sql = 'create table media(title text, artist text, album text, tracknumber int, discnumber int, genre text, path text unique)'
    logger.debug('Creating new SQLite table: "%s" for database in: "%s"' % (sql, args.database))
    do_sql(sql)


def play(media_entries):
    for media in media_entries:
        print '\n--> Playing "' + media['title'] + '" off of "' + media['album'] + '" by "' + media['artist'] + '" -->\n'

        try:
            check_call(['mplayer', media['path']])

        except (KeyboardInterrupt, CalledProcessError):
            # This sleep helps with mplayer printing exiting stuff to stderr after we've printed our prompt:
            sleep(0.25)
            break


def get_media_files(path):
    for root, dirs, files in scandir.walk(path):
        for filename in files:
            if filename.endswith(('.m4a', '.mp3', '.ogg', '.oga', '.flac')):
                logger.debug('Found a potential media file: "%s"' % os.path.join(root, filename))
                yield os.path.join(root, filename)


def parse_media_file(path):
    filename = os.path.split(path)[1]
    filename_split = os.path.splitext(filename)
    extension = filename_split[1]

    if extension == '.m4a':
        mutagen_metadata = m4(path)

    elif extension == '.mp3':
        mutagen_metadata = m3(path)

    elif extension in ('.oga', '.ogg'):
        mutagen_metadata = og(path)

    elif extension == '.flac':
        mutagen_metadata = fl(path)

    # Remember, the Mutagen 'artist' value is a list:
    smj_metadata = {
        'artist': mutagen_metadata.get('artist', ['unknown artist'])[0],
        'album': mutagen_metadata.get('album', ['unknown album'])[0],
        'title': mutagen_metadata.get('title', [filename_split[0]])[0],
        'genre': mutagen_metadata.get('genre', ['unknown genre'])[0],
        'path': path
    }

    smj_metadata['artist'] = mutagen_metadata.get('albumartistsort', [smj_metadata['artist']])[0]

    try:
        smj_metadata['tracknumber'] = int(mutagen_metadata.get('tracknumber', ['0/0'])[0].split('/')[0])

    except ValueError:
        smj_metadata['tracknumber'] = 0

    try:
        smj_metadata['discnumber'] = int(mutagen_metadata.get('discnumber', ['0/0'])[0].split('/')[0])

    except ValueError:
        smj_metadata['discnumber'] = 0

    logger.debug('Parsed: %s' % str(smj_metadata))

    return smj_metadata

insert_sql = 'insert into media (title, artist, album, tracknumber, discnumber, genre, path) values (:title, :artist, :album, :tracknumber, :discnumber, :genre, :path)'


def index_media(location=args.location):
    before = time()
    do_sql(insert_sql, column_data=itertools.imap(parse_media_file, get_media_files(location)), multiple=True)
    after = time()
    logger.info('Serially indexed %s files in %s seconds.' %
                (str(do_sql('select count(path) from media')[0][0]), round(after - before, 2)))


def index_media_faster(location=args.location):
    pool = multiprocessing.Pool()
    before = time()
    do_sql(insert_sql, column_data=pool.imap_unordered(parse_media_file, get_media_files(location), 8), multiple=True)
    after = time()
    logger.info('Parallely indexed %s files in %s seconds.' %
                (str(do_sql('select count(path) from media')[0][0]), round(after - before, 2)))


def search_media(input_string):
    pre_sql = 'select * from media where '
    sql = ''
    post_sql = ' order by artist, album, discnumber, tracknumber'

    genre_params = []
    artist_params = []
    album_params = []
    title_params = []
    multi_params = []

    for word in input_string.split(','):
        word = word.strip()
        if word.startswith('!'):
            genre_params.append(word[1:])
        elif word.startswith('@'):
            artist_params.append(word[1:])
        elif word.startswith('#'):
            album_params.append(word[1:])
        elif word.startswith('$'):
            title_params.append(word[1:])
        else:
            multi_params.append(word)

    genre_sql = '(' + ' or '.join(['genre like ?'] * len(genre_params)) + ')'
    artist_sql = '(' + ' or '.join(['artist like ?'] * len(artist_params)) + ')'
    album_sql = '(' + ' or '.join(['album like ?'] * len(album_params)) + ')'
    title_sql = '(' + ' or '.join(['title like ?'] * len(title_params)) + ')'
    multi_sql = '(' + ' or '.join(['artist like ? or album like ? or title like ?'] * len(multi_params)) + ')'

    sql = pre_sql + \
        ' and '.join(filter(lambda x: len(x) > 2, [genre_sql, artist_sql, album_sql, title_sql, multi_sql])) + post_sql
    sql_params = ['%' + param + '%' for param in genre_params +
                  artist_params + album_params + title_params + multi_params * 3]

    logger.debug('Crafted SQL statement: "%s"' % sql)
    logger.debug('Crafted SQL variables: "%s"' % sql_params)

    return do_sql(sql, column_data=sql_params)


def playlist_handler(input_string, media_entries):
    input_string = input_string.strip()
    if input_string.isdigit():
        input_string = int(input_string)
        if 0 < input_string <= len(media_entries):
            play(media_entries[input_string - 1 :])
        else:
            print 'Enter value from 1 to', len(media_entries)
    elif input_string.startswith('a'):
        play(media_entries)
    elif input_string.startswith('r'):
        play([random.choice(media_entries)])
    elif input_string.startswith('s'):
        random.shuffle(media_entries)
        play(media_entries)
    else:
        'Not a valid playlist command, search again.'

# ==============================================================================
# Main loop:
# ==============================================================================

if not os.path.exists(args.location):
    exit('Cannot scan a nonexistent path: "%s"' % args.location)

if os.path.exists(args.database):
    if args.force_complete_scan:
        os.remove(args.database)
        make_db()
else:
    make_db()
    args.rescan = True

if args.rescan:
    if args.force_serial:
        index_media()
    else:
        index_media_faster()

if args.smj_query:
    if ';' in args.smj_query:
        query, command = args.smj_query.split(';')
    else:
        query = args.smj_query
        command = 'a'

    results = search_media(query)

    if args.json:
        print json.dumps(map(dict, results), indent=2)
        exit()

    playlist_handler(command, results)
    exit()


count = do_sql('select count(path) from media')[0][0]

print 'For help with SMJ7-style syntax, run the script with --syntax'
print 'Examples: just a query; !genre, @artist name, #album name, $track name'

while True:
    try:
        input = raw_input('\n[SMJ7 | %s files] > ' % '{:,}'.format(count))

        results = search_media(input)

        if len(results) == 1:
            play(results)

        elif len(results) > 1:

            artist = ''
            album = ''

            for i, result in enumerate(results):
                i = '[' + str(i + 1) + ']'

                if artist == result['artist']:
                    if album == result['album']:
                        print '    ', i, result['title']
                    else:
                        print '\n  ', result['album']
                        print '  ', '-' * len(result['album'])
                        print '    ', i, result['title']
                else:
                    print '\n', result['artist']
                    print '=' * len(result['artist'])
                    print '\n  ', result['album']
                    print '  ', '-' * len(result['album'])
                    print '    ', i, result['title']
                artist = result['artist']
                album = result['album']

            print '\nEnter # to play, or one of: (A)ll, (R)andom choice, or (S)huffle all'
            choice = raw_input('\n[Play command] > ').lower()
            playlist_handler(choice, results)

        else:
            print 'No results found.'

    except KeyboardInterrupt:
        print ' ...'
        continue

    except EOFError:
        print >> sys.stderr, '\nGoodbye.'
        exit(0)
