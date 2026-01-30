.PHONY: build static clean help

BINARY_NAME=smj-go
STATIC_BINARY_NAME=smj-go-static

build: ## Build the standard binary (supports SQLite + Bleve)
	go build -o $(BINARY_NAME)

static: ## Build a static, pure-Go binary (Bleve only, no SQLite)
	CGO_ENABLED=0 go build -o $(STATIC_BINARY_NAME) -ldflags '-extldflags "-static"'

clean: ## Remove build artifacts
	rm -f $(BINARY_NAME) $(STATIC_BINARY_NAME)

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'