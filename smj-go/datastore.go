package main

// Media represents a single media file and its metadata.
type Media struct {
	Title       string `json:"title"`
	Artist      string `json:"artist"`
	Album       string `json:"album"`
	TrackNumber int    `json:"tracknumber"`
	DiscNumber  int    `json:"discnumber"`
	Genre       string `json:"genre"`
	Path        string `json:"path"`
}

// Datastore is the interface that any backend must implement.
type Datastore interface {
	// Initialize prepares the datastore (e.g., create tables, open index).
	Initialize(path string) error
	
	// Close cleans up resources.
	Close() error
	
	// IndexMediaBatch adds or updates a batch of media entries.
	IndexMediaBatch(batch []*Media) error
	
	// Count returns the total number of media entries.
	Count() (int, error)
	
	// Search returns media entries matching the query string.
	// If query is empty, it should return all entries (or a reasonable default).
	Search(query string) ([]Media, error)
	
	// RemoveStaleEntries checks all entries and removes those that no longer exist on disk.
	// Returns the number of removed entries.
	RemoveStaleEntries() (int, error)
	
	// GetAllPaths returns a list of all file paths currently in the store.
	// This is useful for efficient freshening or staleness checks.
	GetAllPaths() ([]string, error)

	// Clear removes all data from the store.
	Clear() error
}
