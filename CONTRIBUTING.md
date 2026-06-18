# Contributing to Cartographer

Thank you for considering contributing to Cartographer! We welcome contributions of all kinds — bug fixes, new features, documentation improvements, and more.

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

1. Check the [issue tracker](https://github.com/Icarus-afk/cartographer/issues) for existing reports
2. If none exists, [open a new issue](https://github.com/Icarus-afk/cartographer/issues/new) with:
   - A clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Python version, OS, and relevant environment info

### Suggesting Features

1. [Open a feature request](https://github.com/Icarus-afk/cartographer/issues/new) with:
   - A clear description of the problem you're solving
   - Proposed API or behavior (if applicable)
   - Why this is useful to the project

### Pull Requests

1. **Fork the repo** and create your branch from `main`
2. **Run tests** before submitting: `make test`
3. **Run linting**: `make lint`
4. **Write tests** for any new functionality
5. **Keep PRs focused** — one feature/fix per PR
6. **Update documentation** if your change affects usage

### Development Setup

```bash
pip install -e ".[dev,watch]"
```

### Project Structure

```
cartographer/           # Python package (CLI + MCP server)
  cli.py                # Click CLI (30 commands)
  mcp/                  # MCP server (14 tools, 3 resources)
  ingestion/            # File discovery + indexing
  parser/               # 20 tree-sitter language parsers
  graph/                # Knowledge graph builder
  embedding/            # Vector embeddings (384-dim)
  query/                # Search + traversal
  architecture/         # Architecture detection
  compression/          # Token-aware compression
  git/                  # Git intelligence
  storage/              # SQLite persistence
editors/vscode/         # VS Code extension (TypeScript)
docs/                   # Documentation
tests/                  # Test suite (73+ tests)
```

## Style Guide

- **Python**: Follow ruff defaults (line length 100, PEP 8)
- **TypeScript**: Follow project tsconfig conventions
- **Commits**: Use conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, etc.)
- **Documentation**: Keep docs up to date with code changes

## Questions?

Open a [discussion](https://github.com/Icarus-afk/cartographer/discussions) or email <ehasan.ahmed01@gmail.com>.
