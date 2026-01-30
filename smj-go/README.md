# Simple Media Jukebox (Go Version)

A Go reimplementation of the Simple Media Jukebox.

## Features

- Fast media indexing (parallelized)
- SQLite database for metadata storage
- Custom query syntax for searching
- Interactive REPL
- JSON output support
- Playback via `mplayer`

## Usage

```bash
go build -o smj-go
./smj-go -l /path/to/music
```

For help with syntax:
```bash
./smj-go --syntax
```
