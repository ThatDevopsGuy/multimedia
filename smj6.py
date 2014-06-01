#!/usr/bin/env python
# smj6.py | The Simple Media Jukebox, version 6
# Copyright 2010-2012 Sebastian Weigand
# Licensed under the MIT license
# Notes: This version introduces a permanent datastore, utilizes file metadata,
#        and allows for a (albeit very limited) preference file.

# ==============================================================================
# Imports:
# ==============================================================================

# Pythonic supplicants:
import os
import sys
from time import time
from subprocess import *

# Datastore:
import sqlite3

# Metadata handling:
from mutagen.easymp4 import EasyMP4 as m4
from mutagen.easyid3 import EasyID3 as m3
from mutagen.flac import FLAC as fl
from mutagen.oggvorbis import OggVorbis as ov

# ==============================================================================
# Libraries:
# ==============================================================================


def getRealPath(path):
    return os.path.realpath(os.path.expanduser(path))

# ------------------------------------------------------------------------------
# SQL transactions:
# ------------------------------------------------------------------------------


def establishSMJDatabase(location):
    sys.stdout.write('Creating the initial database...'.ljust(50))
    sys.stdout.flush()
    conn = sqlite3.connect(location)
    c = conn.cursor()
    c.execute('create table media(track text, artist text, album text, file text unique)')
    conn.commit()
    c.close()
    sys.stdout.write('[ OK ]\n')
    sys.stdout.flush()

# ------------------------------------------------------------------------------
# Media functions:
# ------------------------------------------------------------------------------


def play(result):
    print '\n--> Playing "' + result[0] + '" off of "' + result[2] + '" by "' + result[1] + '" -->\n'
    try:
        call(['mplayer', result[3]])

    except KeyboardInterrupt:
        print >> sys


def getMediaFilesFromLocation(location):
    print 'Media location:', '"' + location + '"'
    sys.stdout.write(('Finding media files...').ljust(50))
    sys.stdout.flush()

    location = getRealPath(location)
    results = Popen(
        'find ' + location +
        ' \\( -iname *.m4a -o -iname *.mp4 -o -iname *.mp3 -o -iname *.ogg -o -iname *.oga -o -iname *.flac \\)',
        shell=True, stdout=PIPE).communicate()[0].splitlines()

    if len(results) == 0:
        sys.stdout.write('[ None ]\n')
    else:
        sys.stdout.write('[ ' + str(len(results)) + ' ]\n')

    sys.stdout.flush()

    return results


def getNewerMediaFilesFromLocation(location, referenceFile):
    print 'Media location:', '"' + location + '"'
    sys.stdout.write(('Finding new media files...').ljust(50))
    sys.stdout.flush()

    location = getRealPath(location)
    results = Popen('find ' + location + ' -newer ' + referenceFile +
                    ' \\( -iname *.m4a -o -iname *.mp4 -o -iname *.mp3 -o -iname *.ogg -o -iname *.oga -o -iname *.flac \\)', shell=True, stdout=PIPE).communicate()[0].splitlines()

    if len(results) == 0:
        sys.stdout.write('[ None ]\n')
    else:
        sys.stdout.write('[ ' + str(len(results)) + ' ]\n')

    sys.stdout.flush()

    return results


def parseMediaFile(file, mediaLocation):
    name = file.lower()
    mediaLocation = getRealPath(mediaLocation)
    audio = {}

    try:
        if '.m4a' in name or '.mp4' in name:
            audio = m4(file)
        elif '.mp3' in name:
            audio = m3(file)
        elif '.ogg' in name or '.oga' in name:
            audio = og(file)
        elif '.flac' in name:
            audio = fl(file)
        else:
            print >> sys.stderr, 'Debug: Could not determine audio type of:', file
    except:
        print 'Issue with:', file

    if 'title' not in audio:
        audio['title'] = file.split('/')[-1].split('.')[:-1]

    if 'artist' not in audio or 'album' not in audio:
        with open(getRealPath('~/.smj/unknowns.txt'), 'a') as f:
            f.write('Issue with: ' + file + '\n')

        fields = file.split('/')

        # Attempt to figure out artist and album by folder hierarchy:
        if len(fields) >= len(mediaLocation.split('/')) + 2:
            audio['album'] = fields[-2] + ' (album guess)'
            audio['artist'] = fields[-3] + ' (artist guess)'
        else:
            audio['album'] = 'unknown'
            audio['artist'] = 'unknown'

    return {'track': audio['title'][0], 'artist': audio['artist'][0], 'album': audio['album'][0], 'file': file}


def mediaIndexer(files, mediaLocation):
    width = len(str(len(files)))
    length = str(len(files))

    sys.stdout.write('*' * (width * 2 + 3))
    sys.stdout.flush()
    for i, file in enumerate(files):
        sys.stdout.write(('\b' * (width * 2 + 3)) + str(i + 1).rjust(width) + ' / ' + length)
        sys.stdout.flush()
        yield parseMediaFile(file, mediaLocation)


def populateDB(dbFile, mediaLocation, mode='initial'):
    if mode == 'initial':
        songFiles = getMediaFilesFromLocation(mediaLocation)
    elif mode == 'freshen':
        songFiles = getNewerMediaFilesFromLocation(mediaLocation, dbFile)
    else:
        raise SyntaxError('Mode for populateDB() must be one of: initial or freshen.')

    if len(songFiles) == 0:
        return

    sys.stdout.write('Indexing media...'.ljust(50))
    sys.stdout.flush()

    conn = sqlite3.connect(dbFile)
    conn.text_factory = str
    c = conn.cursor()

    try:
        c.executemany(
            "insert into media (track, artist, album, file) values (:track, :artist, :album, :file)",
            mediaIndexer(songFiles, mediaLocation))
    except sqlite3.IntegrityError:
        # Don't bother catching uniqness errors here, just skip 'em.
        pass

    conn.commit()

    c.execute('select count(file) from media;')
    count = c.fetchall()
    c.close()

    sys.stdout.write('\n')
    sys.stdout.flush()


def pruneDB(dbFile):
    sys.stdout.write('Pruning the database...'.ljust(50))
    sys.stdout.flush()

    conn = sqlite3.connect(dbFile)
    conn.text_factory = str
    c = conn.cursor()

    c.execute('select file from media;')
    filesFromDB = c.fetchall()

    for tuple in filesFromDB:
        if not os.path.exists(tuple[0]):
            c.execute("delete from media where file = '" + tuple[0] + "';")

    c.execute('select count(file) from media;')
    count = c.fetchall()

    conn.commit()
    c.close()

    removedTotal = len(filesFromDB) - count[0][0]

    if removedTotal == 0:
        sys.stdout.write('[ None ]\n')
    else:
        sys.stdout.write('[ ' + str(removedTotal) + ' ]\n')

    sys.stdout.flush()


def deleteDB(dbFile):
    print 'Deleting the database cannot be undone.'
    choice = raw_input('Are you sure you want to do this? [y/N] > ')
    if choice.lower() == 'y' or choice.lower() == 'yes':
        print 'Deleting the database...'
        os.remove(dbFile)
        print 'The database has been deleted.'
        # Can't open a file which doesn't exist, so exit:
        exit(0)
    else:
        print 'Aborting, no changes have been made.'

# ==============================================================================
# Initalization:
# ==============================================================================

smjLocation = getRealPath('~/.smj/')
dbFile = getRealPath('~/.smj/library.sqlite')
mediaLocation = getRealPath('~/Music/')

if os.path.exists(smjLocation):
    if os.path.exists(dbFile):
        if os.access(dbFile, os.R_OK) or not os.access(dbFile, os.W_OK):
            print 'Note: SMJ database found.'
        else:
            print >> sys.stderr, 'Error: Cannot read from and/or write to:', dbFile
    else:
        print 'Note: No SMJ database found.'
        establishSMJDatabase(dbFile)
        populateDB(dbFile, mediaLocation)
else:
    print 'Note: No SMJ database found.'
    os.mkdir(smjLocation)
    establishSMJDatabase(dbFile)
    populateDB(dbFile, mediaLocation)

# ==============================================================================
# Main loop:
# ==============================================================================

print '\nSimple Media Jukebox v6'
print 'Type "!quit" to quit, or use EOF.'
print 'Searching by track, album, and artist.'

conn = sqlite3.connect(dbFile)
conn.text_factory = str
c = conn.cursor()

commandCharacter = '*'

while True:
    try:
        input = raw_input('\n[' + commandCharacter + '] > ').lower()

        # Check for '!' commands:
        if input.startswith('!'):
            if input == '!quit' or input == '!q':
                print >> sys.stderr, 'Goodbye.'
                exit(0)

            elif input == '!freshen':
                populateDB(dbFile, mediaLocation, mode='freshen')
                continue

            elif input == '!prune':
                pruneDB(dbFile)
                continue

            elif input == '!a' or '!artist' in input:
                print 'Searching by artist.'
                commandCharacter = 'a'
                continue

            elif input == '!t' or '!track' in input:
                print 'Searching by track.'
                commandCharacter = 't'
                continue

            elif input == '!l' or '!album' in input:
                print 'Searching by album.'
                commandCharacter = 'l'
                continue

            elif input == '!*' or '!all' in input:
                print 'Searching by all.'
                commandCharacter = '*'
                continue

            elif input == '!deletedb':
                deleteDB(dbFile)
                continue

            elif input == '!quit' or input == '!q':
                print >> sys.stderr, '\nGoodbye.'
                exit(0)

            else:
                print >> sys.stderr, 'Not a valid command:', input
                continue

        # Search for something:
        sql = 'select * from media where '
        if commandCharacter == 't':
            sql += 'track like '
        elif commandCharacter == 'a':
            sql += 'artist like '
        elif commandCharacter == 'l':
            sql += 'album like '

        sql += '"%' + input + '%" order by artist;'

        if commandCharacter == '*':
            sql = 'select * from media where ' + \
                'track like "%' + input + '%" or ' + \
                'artist like "%' + input + '%" or ' + \
                'album like "%' + input + '%" order by artist;'

        c.execute(sql)
        results = c.fetchall()

        if len(results) == 1:
            play(results[0])

        elif len(results) > 1:

            artist = ''
            album = ''

            for i, result in enumerate(results):
                i = '[' + str(i + 1) + ']'

                if artist == result[1]:
                    if album == result[2]:
                        print '\t\t', i, result[0]
                    else:
                        print '\n\t', result[2]
                        print '\t', '-' * len(result[2])
                        print '\t\t', i, result[0]
                else:
                    print '\n', result[1]
                    print '=' * len(result[1])
                    print '\n\t', result[2]
                    print '\t', '-' * len(result[2])
                    print '\t\t', i, result[0]
                artist = result[1]
                album = result[2]

            choice = raw_input('\n[Play selection] > ')

            if choice.isdigit():
                choice = int(choice)
                if 0 < choice <= len(results):
                    play(results[choice - 1])
                else:
                    print 'Enter value from 1 to', len(results)
            else:
                print 'Would search here.'

        else:
            print 'No results found.'

    except KeyboardInterrupt:
        print ' ...'
        continue

    except EOFError:
        print >> sys.stderr, '\nGoodbye.'
        c.close()
        exit(0)
