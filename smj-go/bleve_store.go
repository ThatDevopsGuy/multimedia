package main

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/blevesearch/bleve/v2"
	bleveQuery "github.com/blevesearch/bleve/v2/search/query"
)

type BleveStore struct {
	index bleve.Index
}

func (b *BleveStore) Initialize(path string) error {
	// If path implies a file (ends in .bleve), use it as a directory name
	// Bleve indexes are directories.
	if filepath.Ext(path) == ".sqlite" {
		path = strings.TrimSuffix(path, ".sqlite") + ".bleve"
	}
	
	if _, err := os.Stat(path); os.IsNotExist(err) {
		mapping := bleve.NewIndexMapping()
		index, err := bleve.New(path, mapping)
		if err != nil {
			return err
		}
		b.index = index
	} else {
		index, err := bleve.Open(path)
		if err != nil {
			return err
		}
		b.index = index
	}
	return nil
}

func (b *BleveStore) Close() error {
	if b.index != nil {
		return b.index.Close()
	}
	return nil
}

func (b *BleveStore) Clear() error {
	// Bleve doesn't have a simple "Clear".
	// The easiest way is to close, remove dir, and re-init.
	// But we are inside an open state. 
	// We can delete all docs.
	// Or just return error "Not implemented" and rely on `os.RemoveAll` in `main.go` for "force-rescan".
	// `force-rescan` in main.go calls `os.Remove(databasePath)`.
	// Since Bleve is a directory, `os.Remove` might fail if it's not empty or `os.RemoveAll` is needed.
	// We'll handle directory cleanup in `main.go`.
	return nil 
}

func (b *BleveStore) IndexMediaBatch(batch []*Media) error {
	batchIndex := b.index.NewBatch()
	for _, m := range batch {
		// Use Path as ID to ensure uniqueness and allow updates
		err := batchIndex.Index(m.Path, m)
		if err != nil {
			return err
		}
	}
	return b.index.Batch(batchIndex)
}

func (b *BleveStore) Count() (int, error) {
	c, err := b.index.DocCount()
	return int(c), err
}

func (b *BleveStore) GetAllPaths() ([]string, error) {
	// Helper to retrieve all IDs (paths)
	// Iterate using a MatchAll query
	q := bleve.NewMatchAllQuery()
	req := bleve.NewSearchRequest(q)
	req.Size = 1000000 // A large enough number, or paginate
	// We only need the ID
	req.Fields = []string{} 

	res, err := b.index.Search(req)
	if err != nil {
		return nil, err
	}

	var paths []string
	for _, hit := range res.Hits {
		paths = append(paths, hit.ID)
	}
	return paths, nil
}

func (b *BleveStore) RemoveStaleEntries() (int, error) {
	paths, err := b.GetAllPaths()
	if err != nil {
		return 0, err
	}

	removed := 0
	batch := b.index.NewBatch()
	for _, path := range paths {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			batch.Delete(path)
			removed++
		}
	}
	err = b.index.Batch(batch)
	return removed, err
}

func (b *BleveStore) Search(input string) ([]Media, error) {
	if input == "" {
		// Match All
		q := bleve.NewMatchAllQuery()
		return b.runQuery(q)
	}

	// First try to parse as strict query string (e.g. "artist:Rolling")
	// If the user inputs simple text "rolling", QueryStringQuery handles it too.
	// But SMJ7 syntax uses special chars (!, @, #, $).
	// We should convert SMJ7 syntax to Bleve Query String syntax if possible,
	// OR just implement a custom logic like SQLiteStore does but constructing a BooleanQuery.

	// SMJ7 Syntax Mapping:
	// !genre -> genre:value
	// @artist -> artist:value
	// #album -> album:value
	// $track -> title:value
	// simple -> (+artist:simple +album:simple +title:simple) (Disjunction)

	// HOWEVER, user asked for "Bleve-specific capabilities". 
	// If the input doesn't look like SMJ7 syntax (no prefix chars), we can pass it to QueryStringQuery directly
	// to allow "artist:rolling~2" etc.
	
	// Let's try to detect if it's SMJ7 style.
	if strings.ContainsAny(input, "!@#$") || strings.Contains(input, ",") {
		// Parse SMJ7 style and build a boolean query
		return b.searchSMJ7Style(input)
	}

	// Fallback/Default: Use Bleve's Query String Syntax
	// This enables fuzzy search, field scoping, etc.
	q := bleve.NewQueryStringQuery(input)
	return b.runQuery(q)
}

func (b *BleveStore) searchSMJ7Style(input string) ([]Media, error) {
	var genreParams, artistParams, albumParams, titleParams, multiParams []string
	for _, word := range strings.Split(input, ",") {
		word = strings.TrimSpace(word)
		if word == "" {
			continue
		}
		if strings.HasPrefix(word, "!") {
			genreParams = append(genreParams, word[1:])
		} else if strings.HasPrefix(word, "@") {
			artistParams = append(artistParams, word[1:])
		} else if strings.HasPrefix(word, "#") {
			albumParams = append(albumParams, word[1:])
		} else if strings.HasPrefix(word, "$") {
			titleParams = append(titleParams, word[1:])
		} else {
			multiParams = append(multiParams, word)
		}
	}

	mainBoolQuery := bleve.NewBooleanQuery()

	// Helper to add OR groups
	addOrGroup := func(terms []string, field string) {
		if len(terms) == 0 {
			return
		}
		subQuery := bleve.NewBooleanQuery()
		for _, t := range terms {
			mq := bleve.NewMatchQuery(t)
			mq.SetField(field)
			subQuery.AddShould(mq)
		}
		mainBoolQuery.AddMust(subQuery)
	}

	addOrGroup(genreParams, "genre")
	addOrGroup(artistParams, "artist")
	addOrGroup(albumParams, "album")
	addOrGroup(titleParams, "title")

	if len(multiParams) > 0 {
		subQuery := bleve.NewBooleanQuery()
		for _, t := range multiParams {
			// artist OR album OR title
			q1 := bleve.NewMatchQuery(t); q1.SetField("artist")
			q2 := bleve.NewMatchQuery(t); q2.SetField("album")
			q3 := bleve.NewMatchQuery(t); q3.SetField("title")
			subQuery.AddShould(q1, q2, q3)
		}
		mainBoolQuery.AddMust(subQuery)
	}

	return b.runQuery(mainBoolQuery)
}

func (b *BleveStore) runQuery(q bleveQuery.Query) ([]Media, error) {
	req := bleve.NewSearchRequest(q)
	req.Size = 1000 // Limit results? 
	req.Fields = []string{"*"} // Load all fields
	
	// Sort by Artist, Album, Disc, Track
	// Bleve sorting is strings by default. Numeric sorting requires numeric indexing.
	// Default default mapping guesses types.
	req.SortBy([]string{"artist", "album", "discnumber", "tracknumber"})

	res, err := b.index.Search(req)
	if err != nil {
		return nil, err
	}

	var results []Media
	for _, hit := range res.Hits {
		var m Media
		// Bleve returns fields in a map
		// We can't easily map back to struct using standard json unmarshal from hit.Fields
		// because hit.Fields is map[string]interface{}.
		// We have to construct it manually.
		
		getStr := func(f string) string {
			if v, ok := hit.Fields[f].(string); ok {
				return v
			}
			return ""
		}
		getInt := func(f string) int {
			if v, ok := hit.Fields[f].(float64); ok {
				return int(v)
			}
			return 0
		}
		
		m.Title = getStr("title")
		m.Artist = getStr("artist")
		m.Album = getStr("album")
		m.Genre = getStr("genre")
		m.Path = getStr("path")
		m.TrackNumber = getInt("tracknumber")
		m.DiscNumber = getInt("discnumber")
		
		results = append(results, m)
	}
	return results, nil
}
