# multimedia

Random multimedia scripts:

* smj7.py      - A command-line music jukebox (and indexer) featuring a custom querying syntax
* xyz2aac.py  - A multi-process media converter utilizing CoreAudio to convert CoreAudio readable audio files to AAC or ALAC

## SMJ7 Auto-Generated Help

```
% ./smj7.py -h                                                                                                                                                                                            ✹
usage: smj7.py [-h] [-l LOCATION] [-q QUERY] [--database DATABASE] [--freshen]
               [--prune] [--force-rescan] [--json] [--show-paths] [-i INDENT]
               [--force-serial] [--syntax] [-d]

A simple command-line media indexer and jukebox.

optional arguments:
  -h, --help            show this help message and exit
  -l LOCATION, --location LOCATION
                        the location to search for media files [~/Music]
  -q QUERY, --query QUERY
                        input an SMJ7-style query, followed by playlist
                        commands, and disable interactive mode (see --syntax)
  --database DATABASE   the location to store the media database
                        [~/.smj/smj7.sqlite]
  --freshen             search for new files and scan them, and update
                        existing entries in the database, useful when adding
                        new albums or changing metadata
  --prune               delete entries from the database if the file no longer
                        exists (Note: if you suspect a large amount of files,
                        use --force-rescan instead)
  --force-rescan        nuke the database and start from scratch, useful when
                        a lot has changed since the last scan
  --json                skip playback and interactive selection, just output
                        matching results in JSON
  --show-paths          include path information in JSON track output
  -i INDENT, --indent INDENT
                        with --json, # of spaces to indent by, set to 0 to
                        dump block of text [2]
  --force-serial        disable parallelized media parsing, useful for slower
                        machines or older mechanical hard disk drives
  --syntax              show SMJ7-sylte syntax guide
  -d, --debug           enable debug mode

Note: mplayer is required to play files.
```

## SMJ7 Installation Instructions

### OS X

```
brew install mplayer
pip install mutagen scandir
git clone https://github.com/swdd/multimedia.git
./multimedia/smj7.py
```

### Linux Distributions

#### Arch

```
sudo pacman -S python2-pip mplayer
pip install mutagen scandir
git clone https://github.com/swdd/multimedia.git
./multimedia/smj7.py
```

#### Fedora / RedHat

```
sudo yum install mplayer python-pip
pip install mutagen scandir
git clone https://github.com/swdd/multimedia.git
./multimedia/smj7.py
```

#### Debian and Debian Derivatives

```
sudo apt-get install mplayer python-pip
pip install mutagen scandir
git clone https://github.com/swdd/multimedia.git
./multimedia/smj7.py
```

## SMJ7-Style Syntax

### tl;dr

Enjoy quick shorthand and get to your music quickly, easily, and all from the command line:

* `./smj7.py -q '@awol, #run'` : Automatically play all songs off of "Run" by "AWOLNATION"
* `./smj7.py -q '@decem, #live, $infanta'` : Play the live version of "Infanta" by "The Decemberists"
* `./smj7.py -q '!electronic, !dance, !party; s'` : Play a shuffled mix of those 3 genres

SMJ7 supports a new syntax for chaining queries together using single-character notation.
You can combine multiple parameters; like-type parameters will be logically ORed and
unlike-type parameters will be logically ANDed together.

* !some string                      - Search for genres matching the string
* @some string                      - Search for artists matching the string
* #some string                      - Search for albums matching the string
* $some string                      - Search for tracks matching the string
* some string                       - Search for artists, albums, or tracks matching the string

### Combinations

Parameters are comma-separated, and combined logically as mentioned above. All strings are
searched case-insensitively and will match on partial hits.

* @artist1, @artist2                  - Would search for any songs by either artist1 or artist2
* @artist1, #album1                   - Would search for any albums with "albums1" in it by any artist with "artist1" in it.
* something1                          - Would search for anything matching "something1", in any field
* something1, $track1                 - Would search for any tracks matching "track1" that have "something1" related to them

### Common Uses

* term1, term2, term3                 - Keep searching everything until the additional terms yield the specificity you wish
* @artist1, @artist2, #greatest hits  - Play the "Greatest Hits" albums by both artist1 and artist2
* @artist, #album, $tracknumber       - Play a specific track off of a specific album, useful when live albums exist alongside

### Examples

* @mingus, @coltrane, @brubeck        - Would play some assorted jazz tracks by these 3 artists
* @rolling stones, #greatest          - Would match "Greatest Hits" by "The Rolling Stones"
* @decemberists, #live, $infanta      - Would play the live version of "Infanta" by "The Decemberists"

### Playlist post-commands

When invoking from the command line, you should encapsulate your SMJ7-style query in quotes, so that your shell can pass it here properly.

To add playlist commands, simply append a semicolon ";" to your query and follow it with one of:

* #                                   - Play the #th song
* a                                   - Play all matching songs
* r                                   - Play a single, random matching song
* s                                   - Play all matching songs, shuffled

#### Examples of SMJ7-style query plus commands:

* ` ./smj7.py -q "@rolling stones, #greatest; a"` - Plays all songs matching the query
* ` ./smj7.py -q "@decemberists, #live; s"`       - Plays all songs matching the query, in a random order
