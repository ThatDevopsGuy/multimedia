# multimedia

Random multimedia scripts

## SMJ7-Style Syntax

SMJ7 supports a new syntax for chaining queries together using single-character notation.
You can combine multiple parameters; like-type parameters will be logically ORed and
unlike-type parameters will be logically ANDed together.

!<some string>                      - Search for genres matching the string
@<some string>                      - Search for artists matching the string
#<some string>                      - Search for albums matching the string
$<some string>                      - Search for tracks matching the string
<some string>                       - Search for artists, albums, or tracks matching the string

### Combinations

Parameters are comma-separated, and combined logically as mentioned above. All strings are
searched case-insensitively and will match on partial hits.

@artist1, @artist2                  - Would search for any songs by either artist1 or artist2
@artist1, #album1                   - Would search for any albums with "albums1" in it by any artist with "artist1" in it.
something1                          - Would search for anything matching "something1", in any field
something1, $track1                 - Would search for any tracks matching "track1" that have "something1" related to them

### Common Uses

term1, term2, term3                 - Keep searching everything until the additional terms yield the specificity you wish
@artist1, @artist2, #greatest hits  - Play the "Greatest Hits" albums by both artist1 and artist2
@artist, #album, $tracknumber       - Play a specific track off of a specific album, useful when live albums exist alongside

### Examples

@mingus, @coltrane, @brubeck        - Would play some assorted jazz tracks by these 3 artists
@rolling stones, #greatest          - Would match "Greatest Hits" by "The Rolling Stones"
@decemberists, #live, $infanta      - Would play the live version of "Infanta" by "The Decemberists"

### Playlist post-commands

When invoking from the command line, you should encapsulate your SMJ7-style query in quotes, so that your shell can pass it here properly.

To add playlist commands, simply append a semicolon ";" to your query and follow it with one of:

#                                   - Play the #th song
a                                   - Play all matching songs
r                                   - Play a single, random matching song
s                                   - Play all matching songs, shuffled

#### Examples of SMJ7-style query plus commands:

./smj7.py -Q "@rolling stones, #greatest; a" - Plays all songs matching the query
./smj7.py -Q "@decemberists, #live; s"       - Plays all songs matching the query, in a random order