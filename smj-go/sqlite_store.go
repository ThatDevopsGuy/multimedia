//go:build cgo

package main

import (
	"database/sql"
	"os"
	"strings"

	_ "github.com/mattn/go-sqlite3"
)

type SQLiteStore struct {
	db *sql.DB
}

func (s *SQLiteStore) Initialize(path string) error {
	db, err := sql.Open("sqlite3", path)
	if err != nil {
		return err
	}
	s.db = db

	sqlStmt := `CREATE TABLE IF NOT EXISTS media(
		title TEXT,
		artist TEXT,
		album TEXT,
		tracknumber INTEGER,
		discnumber INTEGER,
		genre TEXT,
		path TEXT UNIQUE
	);`
	_, err = s.db.Exec(sqlStmt)
	return err
}

func (s *SQLiteStore) Close() error {
	if s.db != nil {
		return s.db.Close()
	}
	return nil
}

func (s *SQLiteStore) Clear() error {
	_, err := s.db.Exec("DELETE FROM media")
	return err
}

func (s *SQLiteStore) IndexMediaBatch(batch []*Media) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	stmt, err := tx.Prepare("INSERT OR REPLACE INTO media (title, artist, album, tracknumber, discnumber, genre, path) VALUES (?, ?, ?, ?, ?, ?, ?)")
	if err != nil {
		tx.Rollback()
		return err
	}
	defer stmt.Close()

	for _, m := range batch {
		_, err = stmt.Exec(m.Title, m.Artist, m.Album, m.TrackNumber, m.DiscNumber, m.Genre, m.Path)
		if err != nil {
			// Log but continue? Or fail batch?
			// For now, logging externally isn't easy here, so we just continue
		}
	}
	return tx.Commit()
}

func (s *SQLiteStore) Count() (int, error) {
	var count int
	err := s.db.QueryRow("SELECT COUNT(*) FROM media").Scan(&count)
	return count, err
}

func (s *SQLiteStore) GetAllPaths() ([]string, error) {
	rows, err := s.db.Query("SELECT path FROM media")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var paths []string
	for rows.Next() {
		var path string
		if err := rows.Scan(&path); err == nil {
			paths = append(paths, path)
		}
	}
	return paths, nil
}

func (s *SQLiteStore) RemoveStaleEntries() (int, error) {
	paths, err := s.GetAllPaths()
	if err != nil {
		return 0, err
	}

	tx, err := s.db.Begin()
	if err != nil {
		return 0, err
	}
	stmt, err := tx.Prepare("DELETE FROM media WHERE path = ?")
	if err != nil {
		tx.Rollback()
		return 0, err
	}
	defer stmt.Close()

	removed := 0
	for _, path := range paths {
		if _, err := os.Stat(path); os.IsNotExist(err) {
			stmt.Exec(path)
			removed++
		}
	}
	err = tx.Commit()
	return removed, err
}

func (s *SQLiteStore) Search(input string) ([]Media, error) {
	if input == "" {
		rows, err := s.db.Query("SELECT title, artist, album, tracknumber, discnumber, genre, path FROM media ORDER BY artist, album, discnumber, tracknumber")
		if err != nil {
			return nil, err
		}
		return s.scanRows(rows)
	}

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

	var sqlParts []string
	var args []interface{}

	if len(genreParams) > 0 {
		var subParts []string
		for _, p := range genreParams {
			subParts = append(subParts, "genre LIKE ?")
			args = append(args, "%"+p+"%")
		}
		sqlParts = append(sqlParts, "("+strings.Join(subParts, " OR ")+")")
	}
	if len(artistParams) > 0 {
		var subParts []string
		for _, p := range artistParams {
			subParts = append(subParts, "artist LIKE ?")
			args = append(args, "%"+p+"%")
		}
		sqlParts = append(sqlParts, "("+strings.Join(subParts, " OR ")+")")
	}
	if len(albumParams) > 0 {
		var subParts []string
		for _, p := range albumParams {
			subParts = append(subParts, "album LIKE ?")
			args = append(args, "%"+p+"%")
		}
		sqlParts = append(sqlParts, "("+strings.Join(subParts, " OR ")+")")
	}
	if len(titleParams) > 0 {
		var subParts []string
		for _, p := range titleParams {
			subParts = append(subParts, "title LIKE ?")
			args = append(args, "%"+p+"%")
		}
		sqlParts = append(sqlParts, "("+strings.Join(subParts, " OR ")+")")
	}
	if len(multiParams) > 0 {
		var subParts []string
		for _, p := range multiParams {
			subParts = append(subParts, "(artist LIKE ? OR album LIKE ? OR title LIKE ?)")
			args = append(args, "%"+p+"%", "%"+p+"%", "%"+p+"%")
		}
		sqlParts = append(sqlParts, "("+strings.Join(subParts, " OR ")+")")
	}

	query := "SELECT title, artist, album, tracknumber, discnumber, genre, path FROM media"
	if len(sqlParts) > 0 {
		query += " WHERE " + strings.Join(sqlParts, " AND ")
	}
	query += " ORDER BY artist, album, discnumber, tracknumber"

	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	return s.scanRows(rows)
}

func (s *SQLiteStore) scanRows(rows *sql.Rows) ([]Media, error) {
	defer rows.Close()
	var results []Media
	for rows.Next() {
		var m Media
		err := rows.Scan(&m.Title, &m.Artist, &m.Album, &m.TrackNumber, &m.DiscNumber, &m.Genre, &m.Path)
		if err != nil {
			return nil, err
		}
		results = append(results, m)
	}
	return results, nil
}
