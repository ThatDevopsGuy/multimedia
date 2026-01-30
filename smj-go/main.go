package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math"
	"math/rand"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/dhowden/tag"
)

var (
	location     string
	query        string
	databasePath string
	freshen      bool
	prune        bool
	forceRescan  bool
	outputJSON   bool
	showPaths    bool
	indent       int
	forceSerial  bool
	showSyntax   bool
	debug        bool
	useDocBackend bool
)

func truePath(path string) string {
	if strings.HasPrefix(path, "~") {
		home, _ := os.UserHomeDir()
		path = filepath.Join(home, path[1:])
	}
	abs, _ := filepath.Abs(path)
	return abs
}

func init() {
	home, _ := os.UserHomeDir()
	defaultMusic := filepath.Join(home, "Music")
	defaultDB := filepath.Join(home, ".smj7.sqlite")

	flag.StringVar(&location, "l", defaultMusic, "the location to search for media files")
	flag.StringVar(&location, "location", defaultMusic, "the location to search for media files")
	flag.StringVar(&query, "q", "", "input an SMJ7-style query")
	flag.StringVar(&query, "query", "", "input an SMJ7-style query")
	flag.StringVar(&databasePath, "database", defaultDB, "the location to store the media database")
	flag.BoolVar(&freshen, "freshen", false, "search for new files and scan them")
	flag.BoolVar(&prune, "prune", false, "delete entries from the database if the file no longer exists")
	flag.BoolVar(&forceRescan, "force-rescan", false, "nuke the database and start from scratch")
	flag.BoolVar(&outputJSON, "json", false, "output matching results in JSON")
	flag.BoolVar(&showPaths, "show-paths", false, "include path information in JSON track output")
	flag.IntVar(&indent, "i", 2, "with --json, # of spaces to indent by")
	flag.IntVar(&indent, "indent", 2, "with --json, # of spaces to indent by")
	flag.BoolVar(&forceSerial, "force-serial", false, "disable parallelized media parsing")
	flag.BoolVar(&showSyntax, "syntax", false, "show SMJ7-style syntax guide")
	flag.BoolVar(&debug, "d", false, "enable debug mode")
	flag.BoolVar(&debug, "debug", false, "enable debug mode")
	flag.BoolVar(&useDocBackend, "use-document-backend", false, "use experimental Bleve document backend")
}

func main() {
	flag.Parse()

	if showSyntax {
		fmt.Println(syntaxGuide)
		return
	}

	location = truePath(location)
	databasePath = truePath(databasePath)

	// Determine backend
	var store Datastore
	sqliteExists := fileExists(databasePath)
	blevePath := strings.TrimSuffix(databasePath, ".sqlite") + ".bleve"
	bleveExists := fileExists(blevePath)

	// Interactive First Launch Backend Selection
	if !sqliteExists && !bleveExists && !useDocBackend && query == "" && !outputJSON {
		fmt.Println("No existing database found.")
		fmt.Println("Select backend:")
		fmt.Println("1. Traditional SQLite (Default)")
		fmt.Println("2. Experimental Bleve (Document Store)")
		fmt.Print("> ")
		
		scanner := bufio.NewScanner(os.Stdin)
		if scanner.Scan() {
			choice := strings.TrimSpace(scanner.Text())
			if choice == "2" {
				useDocBackend = true
			}
		}
	}

	// Auto-select based on existing files if flag not explicitly set?
	// The requirement says "selectable at launch as a command-line argument".
	// But sticking to flag + explicit choice.
	
	if useDocBackend {
		store = &BleveStore{}
		databasePath = blevePath // Switch path to bleve dir
		
		// Import logic: If SQLite exists but Bleve doesn't, import.
		if sqliteExists && !bleveExists {
			fmt.Println("First launch of Document Backend detected.")
			fmt.Println("Importing existing SQLite database...")
			if err := importSQLiteToBleve(truePath(flag.Lookup("database").DefValue), store); err != nil {
				log.Printf("Import failed: %v", err)
			} else {
				fmt.Println("Import successful.")
			}
		}

	} else {
		store = &SQLiteStore{}
	}

	// Force Rescan Cleanup
	if forceRescan {
		if useDocBackend {
			os.RemoveAll(databasePath)
		} else {
			os.Remove(databasePath)
		}
	}

	if err := store.Initialize(databasePath); err != nil {
		log.Fatal(err)
	}
	defer store.Close()

	if _, err := os.Stat(location); os.IsNotExist(err) {
		log.Fatalf("Cannot scan a nonexistent path: \"%s\"", location)
	}

	if forceRescan {
		// Re-init happens inside Initialize usually, but if we deleted it above, Initialize recreated it empty.
		indexMedia(store, location, false)
	} else if freshen {
		indexMedia(store, location, true)
	}

	if prune {
		removed, _ := store.RemoveStaleEntries()
		fmt.Printf("Pruner: Removed %d stale files.\n", removed)
	}

	count, _ := store.Count()
	if count == 0 && !freshen && !forceRescan {
		indexMedia(store, location, false)
	}

	if outputJSON && query == "" {
		results, _ := store.Search("")
		fmt.Println(jsonizer(results))
		return
	}

	if query != "" {
		q := query
		cmd := "a"
		if strings.Contains(query, ";") {
			parts := strings.SplitN(query, ";", 2)
			q = parts[0]
			cmd = strings.TrimSpace(parts[1])
		}

		results, _ := store.Search(q)
		if outputJSON {
			fmt.Println(jsonizer(results))
			return
		}

		playlistHandler(cmd, results)
		return
	}

	interactiveLoop(store)
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return !os.IsNotExist(err)
}

func importSQLiteToBleve(sqlitePath string, bleveStore Datastore) error {
	// Temporary SQLite store to read from
	src := &SQLiteStore{}
	if err := src.Initialize(sqlitePath); err != nil {
		return err
	}
	defer src.Close()

	// Initialize Bleve (already initialized in main, but okay)
	// Actually main calls Initialize AFTER this import block if we follow standard flow.
	// But we need Bleve open to write.
	// Let's assume bleveStore is NOT initialized in main yet?
	// Re-reading main logic: 
	// 1. `store = &BleveStore{}`
	// 2. `import...` passing `store`.
	// 3. `store.Initialize` called later.
	// So `store` is uninitialized here. We must initialize it.
	
	// Wait, checking main again.
	// `store.Initialize` is called AFTER import logic.
	// So we should Initialize inside here? Or change main order.
	// Changing main order is cleaner. Or Initialize temporarily here.
	
	if err := bleveStore.Initialize(databasePath); err != nil {
		return err
	}
	
	// Get all data
	allMedia, err := src.Search("")
	if err != nil {
		return err
	}
	
	// Batch Index
	// BleveStore.IndexMediaBatch handles batching internally? No, it takes a batch.
	// We should chunk it.
	batchSize := 500
	for i := 0; i < len(allMedia); i += batchSize {
		end := i + batchSize
		if end > len(allMedia) {
			end = len(allMedia)
		}
		
		// Convert []Media to []*Media
		var batchPtrs []*Media
		for j := i; j < end; j++ {
			batchPtrs = append(batchPtrs, &allMedia[j])
		}
		
		if err := bleveStore.IndexMediaBatch(batchPtrs); err != nil {
			return err
		}
	}
	
	return nil // Don't close bleveStore, main will rely on it or re-init (Open check handles it)
}

func parseMediaFile(path string) *Media {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()

	m, err := tag.ReadFrom(f)
	if err != nil {
		if debug {
			log.Printf("Error parsing %s: %v\n", path, err)
		}
		return nil
	}

	track, _ := m.Track()
	disc, _ := m.Disc()

	artist := m.Artist()
	if albumArtist := m.AlbumArtist(); albumArtist != "" {
		artist = albumArtist
	}

	title := m.Title()
	if title == "" {
		title = strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
	}

	album := m.Album()
	if album == "" {
		album = "unknown album"
	}

	genre := m.Genre()
	if genre == "" {
		genre = "unknown genre"
	}

	if artist == "" {
		artist = "unknown artist"
	}

	return &Media{
		Title:       title,
		Artist:      artist,
		Album:       album,
		TrackNumber: track,
		DiscNumber:  disc,
		Genre:       genre,
		Path:        path,
	}
}

func indexMedia(store Datastore, root string, isFreshen bool) {
	// Need mtime check?
	// Datastore interface doesn't expose raw path checks easily without query.
	// We can use GetAllPaths.
	
	var existingPaths map[string]bool
	if isFreshen {
		existingPaths = make(map[string]bool)
		paths, _ := store.GetAllPaths()
		for _, p := range paths {
			existingPaths[p] = true
		}
	}

	start := time.Now()

	filesChan := make(chan string, 100)
	mediaChan := make(chan *Media, 100)
	var wgWorkers sync.WaitGroup
	var wgWriter sync.WaitGroup

	// Discovery
	go func() {
		defer close(filesChan)
		filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
			if err != nil { return nil }
			if d.IsDir() { return nil }
			
			ext := strings.ToLower(filepath.Ext(path))
			if ext == ".mp3" || ext == ".m4a" || ext == ".ogg" || ext == ".oga" || ext == ".flac" {
				// For freshen, we want to update if it exists OR is new.
				// The Python logic was: "if minMtime == 0 or entry.stat().st_mtime > minMtime".
				// Here "minMtime" was db mtime.
				// If we want to strictly follow "freshen updates existing entries", we should index it.
				// If we want to only add NEW files, that's different.
				// SMJ7 freshen: "search for new files ... AND update existing entries".
				// So we basically scan everything? 
				// The Python code: `file_getter = lambda p: get_media_files(p, min_mtime=db_mtime)`
				// It ONLY yields files modified AFTER the DB was modified.
				// So it relies on FS mtime vs DB file mtime.
				
				if isFreshen {
					info, err := d.Info()
					if err == nil {
						// We need DB mtime.
						// Use os.Stat(databasePath)
						dbStat, dbErr := os.Stat(databasePath)
						if dbErr == nil && info.ModTime().After(dbStat.ModTime()) {
							filesChan <- path
						}
					}
				} else {
					filesChan <- path
				}
			}
			return nil
		})
	}()

	// Workers
	numWorkers := 1
	if !forceSerial {
		numWorkers = runtime.NumCPU()
	}

	for i := 0; i < numWorkers; i++ {
		wgWorkers.Add(1)
		go func() {
			defer wgWorkers.Done()
			for path := range filesChan {
				if m := parseMediaFile(path); m != nil {
					mediaChan <- m
				}
			}
		}()
	}

	go func() {
		wgWorkers.Wait()
		close(mediaChan)
	}()

	// Writer
	var processedCount int
	wgWriter.Add(1)
	go func() {
		defer wgWriter.Done()
		const batchSize = 500
		batch := make([]*Media, 0, batchSize)

		write := func(b []*Media) {
			if len(b) > 0 {
				store.IndexMediaBatch(b)
				processedCount += len(b)
			}
		}

		for m := range mediaChan {
			batch = append(batch, m)
			if len(batch) >= batchSize {
				write(batch)
				batch = batch[:0]
			}
		}
		write(batch)
	}()

	wgWriter.Wait()

	adverb := "Parallely"
	if forceSerial {
		adverb = "Serially"
	}

	if isFreshen {
		fmt.Printf("Indexer: %s indexed %d newer files in %.2f seconds.\n", adverb, processedCount, time.Since(start).Seconds())
	} else {
		count, _ := store.Count()
		fmt.Printf("Indexer: %s indexed %d files in %.2f seconds.\n", adverb, count, time.Since(start).Seconds())
	}
}

func jsonizer(results []Media) string {
	type AlbumMap map[string][]interface{}
	type ArtistMap map[string]AlbumMap

	hierarchy := make(ArtistMap)
	for _, m := range results {
		if _, ok := hierarchy[m.Artist]; !ok {
			hierarchy[m.Artist] = make(AlbumMap)
		}
		if _, ok := hierarchy[m.Artist][m.Album]; !ok {
			hierarchy[m.Artist][m.Album] = []interface{}{}
		}

		var track interface{}
		if showPaths {
			track = map[string]string{"title": m.Title, "path": m.Path}
		} else {
			track = m.Title
		}
		hierarchy[m.Artist][m.Album] = append(hierarchy[m.Artist][m.Album], track)
	}

	var b []byte
	if indent > 0 {
		b, _ = json.MarshalIndent(hierarchy, "", strings.Repeat(" ", indent))
	} else {
		b, _ = json.Marshal(hierarchy)
	}
	return string(b)
}

func playlistHandler(cmd string, results []Media) {
	if len(results) == 0 {
		fmt.Println("No results found.")
		return
	}

	cmd = strings.ToLower(strings.TrimSpace(cmd))
	if i, err := strconv.Atoi(cmd); err == nil {
		if i > 0 && i <= len(results) {
			play(results[i-1:])
		} else {
			fmt.Printf("Enter value from 1 to %d, try again.\n", len(results))
		}
		return
	}

	switch {
	case cmd == "a" || cmd == "":
		play(results)
	case cmd == "r":
		rand.Seed(time.Now().UnixNano())
		play([]Media{results[rand.Intn(len(results))]})
	case cmd == "s":
		rand.Seed(time.Now().UnixNano())
		shuffled := make([]Media, len(results))
		copy(shuffled, results)
		rand.Shuffle(len(shuffled), func(i, j int) {
			shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
		})
		play(shuffled)
	default:
		fmt.Println("Not a valid playlist command, try again.")
	}
}

func play(results []Media) {
	mplayer, err := exec.LookPath("mplayer")
	if err != nil {
		fmt.Println("Error: MPlayer not found in PATH.")
		return
	}

	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt)
	defer signal.Stop(c)

	for _, m := range results {
		fmt.Printf("\n--> Playing \"%s\" off of \"%s\" by \"%s\" -->\n\n", m.Title, m.Album, m.Artist)
		cmd := exec.Command(mplayer, m.Path)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr

		err := cmd.Start()
		if err != nil {
			fmt.Printf("Error starting mplayer: %v\n", err)
			continue
		}

		done := make(chan error, 1)
		go func() {
			done <- cmd.Wait()
		}()

		select {
		case <-c:
			fmt.Println("\nSkipping...")
			<-done
			return 
		case err := <-done:
			time.Sleep(250 * time.Millisecond)
			if err != nil {
				if exitErr, ok := err.(*exec.ExitError); ok {
					_ = exitErr
					return
				}
			}
		}
	}
}

func interactiveLoop(store Datastore) {
	count, _ := store.Count()

	fmt.Println("For help with SMJ7-style syntax, use smj-go --syntax")
	fmt.Println("Available parameters: !genre, @artist name, #album name, $track name")

	scanner := bufio.NewScanner(os.Stdin)
	for {
		fmt.Printf("\n[SMJ7 | %s files] > ", commatize(count))
		if !scanner.Scan() {
			fmt.Fprintln(os.Stderr, "\nGoodbye.")
			break
		}
		input := scanner.Text()
		results, _ := store.Search(input)

		if len(results) == 0 {
			fmt.Println("No results found.")
			continue
		}

		if len(results) == 1 {
			play(results)
			continue
		}

		// Print results
		var lastArtist, lastAlbum string
		for i, r := range results {
			iStr := fmt.Sprintf("[ %*d ]", int(math.Log10(float64(len(results))))+1, i+1)

			if lastArtist != r.Artist {
				fmt.Printf("\n %s\n%s\n", r.Artist, strings.Repeat("=", len(r.Artist)))
				fmt.Printf("\n  %s\n   %s\n", r.Album, strings.Repeat("-", len(r.Album)))
				fmt.Printf("    %s %s\n", iStr, r.Title)
			} else if lastAlbum != r.Album {
				fmt.Printf("\n  %s\n   %s\n", r.Album, strings.Repeat("-", len(r.Album)))
				fmt.Printf("    %s %s\n", iStr, r.Title)
			} else {
				fmt.Printf("    %s %s\n", iStr, r.Title)
			}
			lastArtist = r.Artist
			lastAlbum = r.Album
		}

		fmt.Println("\nEnter # to play, or one of: (A)ll, (R)andom choice, or (S)huffle all\n")
		fmt.Print("[Play command] > ")
		if !scanner.Scan() {
			break
		}
		choice := scanner.Text()
		playlistHandler(choice, results)
	}
}

func commatize(n int) string {
	s := strconv.Itoa(n)
	if len(s) <= 3 {
		return s
	}
	var res []string
	for len(s) > 3 {
		res = append(res, s[len(s)-3:])
		s = s[:len(s)-3]
	}
	res = append(res, s)
	for i, j := 0, len(res)-1; i < j; i, j = i+1, j-1 {
		res[i], res[j] = res[j], res[i]
	}
	return strings.Join(res, ",")
}

const syntaxGuide = `
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

./smj-go -q "@rolling stones, #greatest; a" - Plays all songs matching the query
./smj-go -q "@decemberists, #live; s"       - Plays all songs matching the query, in a random order

# Bleve Backend Features

If using the experimental Bleve backend, you can also use standard search queries:

title:love~2                       - Fuzzy match title for "love" with edit distance 2
+artist:queen -title:live          - Must be Queen, must not be "live"
`
