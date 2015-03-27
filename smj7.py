#!/usr/bin/env python
# coding: utf-8
# smj7.py | The Simple Media Jukebox, version 7
# Copyright 2010-2015 Sebastian Weigand
# Licensed under the MIT license

# ==============================================================================
# Imports:
# ==============================================================================

# Bits needed for basic functionality:
import os
import sys
import logging

# Datastore:
import sqlite3

# Standard bits:
from argparse import ArgumentParser
from time import time, sleep
from scandir import walk
from itertools import imap
from math import log10

# Keep this choice separate, as it conflicts with a named variable:
from random import choice as random_choice
from random import shuffle

# Sub and multi-processing:
from subprocess import check_call, CalledProcessError
from multiprocessing import Pool

# Data exporting:
from json import dumps

# Metadata handling:
from mutagen.easymp4 import EasyMP4 as m4
from mutagen.easyid3 import EasyID3 as m3
from mutagen.flac import FLAC as fl
from mutagen.oggvorbis import OggVorbis as ov

# =================================================================================================
# Initialization
# =================================================================================================

# This sys reloading is needed to handle logger output of UTF-8 strings:
reload(sys)
sys.setdefaultencoding('utf8')

logger = logging.getLogger('smj7')
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] | %(levelname)-8s | %(funcName)20s() | %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)
logger.setLevel(logging.INFO)


def true_path(path):
    '''Because os.path.realpath doesn't quite work as it should'''
    return os.path.realpath(os.path.expanduser(path))

parser = ArgumentParser(description='A simple command-line media indexer and jukebox.',
                        epilog='Note: mplayer is required to play files.')

parser.add_argument('-l', '--location', default=true_path('~/Music/'),
                    type=str, help='the location to search for media files [~/Music]')

parser.add_argument('-Q', '--query', type=str,
                    help='input an SMJ7-style query, followed by playlist commands, and disable interactive mode (see --syntax)')

parser.add_argument('--database', default=true_path('~/.smj7.sqlite'),
                    type=str, help='the location to store the media database [~/.smj/smj7.sqlite]')

parser.add_argument('--freshen', action="store_true", default=False, help='search for new files and scan them, and remove stale files from the database, useful when adding new albums')

parser.add_argument('--force-rescan', action="store_true", default=False,
                    help='nuke the database and start from scratch, useful when a lot has changed since the last scan')

parser.add_argument('--json', action="store_true", default=False,
                    help='skip playback and interactive selection, just output matching results in JSON')

parser.add_argument('--include_paths', action="store_true", default=False,
                    help='include path information in JSON track output')

parser.add_argument('-i', '--indent', type=int, default=2, help='with --json, # of spaces to indent by, set to 0 to dump block of text [2]')

parser.add_argument('--force-serial', action="store_true", default=False,
                    help='disable parallelized media parsing, useful for slower machines or older mechanical hard disk drives')

parser.add_argument('--syntax', action="store_true", default=False,
                    help='show SMJ7-sylte syntax guide')

parser.add_argument('-d', '--debug', action="store_true", default=False,
                    help='enable debug mode')

args = parser.parse_args()

if args.debug:
    logger.setLevel(logging.DEBUG)
    console.setLevel(logging.DEBUG)

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

# =================================================================================================
# Functions
# =================================================================================================


def do_sql(query, db_file=args.database, column_data=None, multiple=False):
    ''' A simple SQLite wrapper which handles multiple execution options. '''
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

    # We don't care about overwriting values within the database:
    except sqlite3.IntegrityError:
        logger.debug('Ignoring IntegrityError and overwriting previous values.')
        pass

    response = curs.fetchall()

    conn.commit()
    curs.close()

    return response

# -------------------------------------------------------------------------------------------------


def make_db():
    ''' Perform the initial DB creation, update me if metadata columns change. '''
    sql = 'create table media(title text, artist text, album text, tracknumber int, discnumber int, genre text, path text unique)'
    logger.debug('Creating new SQLite table: "%s" for database in: "%s"' % (sql, args.database))
    do_sql(sql)

# -------------------------------------------------------------------------------------------------


def play(media_entries):
    ''' Play given media_entries as a list of dicts as you'd get from searching. '''
    
    for media in media_entries:
        print '\n--> Playing "' + media['title'] + '" off of "' + media['album'] + '" by "' + media['artist'] + '" -->\n'

        try:
            check_call(['mplayer', media['path']])

        except (KeyboardInterrupt, CalledProcessError):
            # This sleep helps with mplayer printing exiting stuff to stderr after we've printed our prompt:
            sleep(0.25)
            break

# -------------------------------------------------------------------------------------------------


def get_media_files(path):
    ''' Using scandir's optimized walking algorithm, we can discard GNU's `find`. Only catches 
        potential files via filename extension, but we could validate this in the future. '''

    for root, dirs, files in walk(path):
        for filename in files:
            if filename.endswith(('.m4a', '.mp3', '.ogg', '.oga', '.flac')):
                logger.debug('Found a potential media file: "%s"' % os.path.join(root, filename))
                yield os.path.join(root, filename)


def get_new_media_files(path):
    ''' Using scandir's optimized walking algorithm, we can discard GNU's `find`. Only catches 
        potential files via filename extension, but we could validate this in the future. '''

    db_time = os.stat(args.database)[8]

    for root, dirs, files in walk(path):
        for filename in files:
            absolute_filename = os.path.join(root, filename)
            if filename.endswith(('.m4a', '.mp3', '.ogg', '.oga', '.flac')) and os.stat(absolute_filename)[8] > db_time:
                logger.debug('Found a potential newer media file: "%s"' % absolute_filename)
                yield absolute_filename

# -------------------------------------------------------------------------------------------------


def parse_media_file(path):
    ''' Perform the parsing of media metadata, and clean it up into a more sensible format. '''

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

    # Remember, the Mutagen tag's value is a list:
    smj_metadata = {
        'artist': mutagen_metadata.get('artist', ['unknown artist'])[0],
        'album': mutagen_metadata.get('album', ['unknown album'])[0],
        'title': mutagen_metadata.get('title', [filename_split[0]])[0],
        'genre': mutagen_metadata.get('genre', ['unknown genre'])[0],
        'path': path
    }

    # Prefer the "sort" "album artist", which won't include things like "Someone featuring So-and-So":
    smj_metadata['artist'] = mutagen_metadata.get('albumartistsort', [smj_metadata['artist']])[0]

    # Catch very odd cases where the 'tracknumber' field is something other than a digit:
    for number in ['tracknumber', 'discnumber']:
        try:
            smj_metadata[number] = int(mutagen_metadata.get(number, ['0/0'])[0].split('/')[0])

        except ValueError:
            smj_metadata[number] = 0

    logger.debug('Parsed: %s' % str(smj_metadata))

    return smj_metadata

# -------------------------------------------------------------------------------------------------

# Both serial and parallel indexers use this SQL to shove data into SQLite:
insert_sql = 'insert into media (title, artist, album, tracknumber, discnumber, genre, path) values (:title, :artist, :album, :tracknumber, :discnumber, :genre, :path)'


def index_media(location=args.location, freshen=args.freshen):
    ''' Link the media file fetcher with the parser, and update the database. '''

    if freshen:
        before_count = do_sql('select count(path) from media')[0][0]
        file_getter = get_new_media_files
    else:
        file_getter = get_media_files

    before = time()
    
    if args.force_serial:
        adverb = 'Serially'
        try:
            do_sql(insert_sql, column_data=imap(parse_media_file, file_getter(location)), multiple=True)

        except KeyboardInterrupt:
            exit(1)
    
    else:
        adverb = 'Parallely'
        pool = Pool()
        try:
            # Set the chunksize for imap_unordered to a low but doable number that is > 1 for slightly better performance:
            do_sql(insert_sql, column_data=pool.imap_unordered(parse_media_file, file_getter(location), 8), multiple=True)
        
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
            exit(1)
        
        else:
            pool.close()
            pool.join()
    
    after = time()
    
    if freshen:
        after_count = do_sql('select count(path) from media')[0][0]
        print 'Indexer: %s indexed %s newer files in %s seconds.' % (adverb, after_count - before_count, round(after - before, 2))
    else:
        print 'Indexer: %s indexed %s files in %s seconds.' % (adverb, do_sql('select count(path) from media')[0][0], round(after - before, 2))

# -------------------------------------------------------------------------------------------------


def search_media(input_string):
    ''' Parse the SMJ7-style syntax, create the requisite SQL, and execute it. '''

    pre_sql = 'select * from media where '
    sql = ''
    post_sql = ' order by artist, album, discnumber, tracknumber'

    # These will store the different columns we'll be searching:
    genre_params = []
    artist_params = []
    album_params = []
    title_params = []
    multi_params = []

    # Break up the inputted string, get rid of whitespace, and filter it into the above categories:
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

    # These SQL blocks logically OR same-category (same-column) parameters, and group them:
    genre_sql = '(' + ' or '.join(['genre like ?'] * len(genre_params)) + ')'
    artist_sql = '(' + ' or '.join(['artist like ?'] * len(artist_params)) + ')'
    album_sql = '(' + ' or '.join(['album like ?'] * len(album_params)) + ')'
    title_sql = '(' + ' or '.join(['title like ?'] * len(title_params)) + ')'
    multi_sql = '(' + ' or '.join(['artist like ? or album like ? or title like ?'] * len(multi_params)) + ')'

    # This logically ANDs together the OR blocks from above:
    sql = pre_sql + ' and '.join(filter(lambda x: len(x) > 2, [genre_sql, artist_sql, album_sql, title_sql, multi_sql])) + post_sql
    
    # This creates the actual collection of variables for use with SQLite's "?" substitution:
    sql_params = ['%' + param + '%' for param in genre_params + artist_params + album_params + title_params + multi_params * 3]

    logger.debug('Crafted SQL statement: "%s"' % sql)
    logger.debug('Crafted SQL variables: "%s"' % sql_params)

    return do_sql(sql, column_data=sql_params)

# -------------------------------------------------------------------------------------------------


def playlist_handler(input_string, media_entries):
    ''' Handle the commands needed to generate a playlist. '''

    input_string = input_string.strip()

    if input_string.isdigit():
        input_string = int(input_string)
        if 0 < input_string <= len(media_entries):
            play(media_entries[input_string - 1:])
        else:
            print 'Enter value from 1 to %s, try again.' % len(media_entries)
    
    elif input_string.startswith('a'):
        play(media_entries)
    
    elif input_string.startswith('r'):
        play([random_choice(media_entries)])
    
    elif input_string.startswith('s'):
        # random.shuffle does it in-place:
        shuffle(media_entries)
        play(media_entries)
    
    else:
        'Not a valid playlist command, try again.'

# -------------------------------------------------------------------------------------------------


def jsonizer(media_entries, include_paths=args.include_paths):
    ''' Convert track-specific media entries to artist: album: track hierarchy, in JSON. '''

    if args.indent == 0:
        # Must be None type to disable newlines:
        json_indentation_option = None
    else:
        json_indentation_option = args.indent

    hierarchy = {}

    for media in media_entries:
        if include_paths:
            track = {'title': media['title'],
                     'path': media['path']
            }
        else:
            track = media['title']

        if media['artist'] in hierarchy:
            if media['album'] in hierarchy[media['artist']]:
                hierarchy[media['artist']][media['album']].append(track)
            else:
                hierarchy[media['artist']][media['album']] = [track]
        else:
            hierarchy[media['artist']] = {media['album']: [track]}

    return dumps(hierarchy, indent=json_indentation_option)


# =================================================================================================
# Main program logic
# =================================================================================================

if __name__ == '__main__':

    if not os.path.exists(args.location):
        exit('Cannot scan a nonexistent path: "%s"' % args.location)

    if os.path.exists(args.database):
        if args.force_rescan:
            # SQLite doesn't like truncating:
            os.remove(args.database)
            make_db()
            index_media()

        elif args.freshen:
            index_media()

    else:
        make_db()
        index_media()

    # If someone wants a full dump of their music collection:
    if args.json and not args.query:
        print jsonizer(do_sql('select * from media'))
        exit()

    # For non-interactive searching:
    if args.query:
        if ';' in args.query:
            query, command = args.query.split(';')
        else:
            query = args.query
            command = 'a'

        results = search_media(query)

        if args.json:
            # sqlite.Row objects are not JSON serializable, `dict` them here:
            print jsonizer(results)
            # Exit as JSON is not intended for playback:
            exit()

        # Finally kick off the results and playlist command for playback:
        playlist_handler(command, results)
        # Exit otherwise we will fall through to interactive mode:
        exit()

    # =============================================================================================
    # Interactive loop
    # =============================================================================================

    count = do_sql('select count(path) from media')[0][0]

    print 'For help with SMJ7-style syntax, use ./smj7.py --syntax'
    print 'Available parameters: !genre, @artist name, #album name, $track name'

    while True:
        try:
            # Python 2.7 is required for: '{:,}'.format(<value>) to make it add commas to 1,000s:
            input = raw_input('\n[SMJ7 | %s files] > ' % '{:,}'.format(count))

            results = search_media(input)

            if len(results) == 1:
                play(results)

            elif len(results) > 1:

                # Store the last used artist and album for grouping:
                artist = ''
                album = ''

                ''' Print results in the form of:
                    # Artist 1
                     ## Album 1
                        [1] Track 1
                        [2] Track 2
                '''

                for i, result in enumerate(results):
                    # Pad out the number so all of them line up:
                    i = '[ ' + str(i + 1).rjust(int(log10(len(results))) + 1) + ' ]'

                    if artist == result['artist']:
                        if album == result['album']:
                            print '   ', i, result['title']
                        
                        else:
                            print '\n ## ', result['album']
                            print '   ', i, result['title']
                    
                    else:
                        print '\n#', result['artist']
                        print '\n ##', result['album']
                        print   '   ', i, result['title']
                    
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
