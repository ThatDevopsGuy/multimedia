//go:build !cgo

package main

import "errors"

type SQLiteStore struct{}

func (s *SQLiteStore) Initialize(path string) error {
	return errors.New("SQLite backend is not available in non-CGO builds. Please use --use-document-backend or rebuild with CGO_ENABLED=1")
}

func (s *SQLiteStore) Close() error { return nil }

func (s *SQLiteStore) Clear() error { return nil }

func (s *SQLiteStore) IndexMediaBatch(batch []*Media) error { return nil }

func (s *SQLiteStore) Count() (int, error) { return 0, nil }

func (s *SQLiteStore) GetAllPaths() ([]string, error) { return nil, nil }

func (s *SQLiteStore) RemoveStaleEntries() (int, error) { return 0, nil }

func (s *SQLiteStore) Search(input string) ([]Media, error) { return nil, nil }
