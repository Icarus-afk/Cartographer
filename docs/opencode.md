# OpenCode Integration

Cartographer is a **Repository Intelligence Operating System** that transforms any codebase into a persistent, queryable knowledge graph. Within seconds of indexing, every class, function, method, interface, file, and directory becomes a first-class node connected by typed edges (CONTAINS, DEFINES, IMPORTS, CALLS, INHERITS, IMPLEMENTS, DECLARES). The graph lives in a portable SQLite database (~310 bytes/node) and supports semantic search, architecture detection, git intelligence, and token-aware compression.

This guide covers integration patterns, agent configuration, and best practices for using Cartographer with AI coding assistants like OpenCode.

---

## Quick Setup

### 1. Configure OpenCode tools

Add to your OpenCode configuration file (`~/.config/opencode/config.jsonc` or project-level `opencode.json`):

```jsonc
{
  "tools": {
    "cartographer-query": {
      "command": "cartographer query --db /path/to/index.db --max-tokens 2000",
      "description": "Answer natural language questions about the codebase. Arguments: a question like 'explain X' or 'what is the architecture'",
      "args": ["{{input}}"]
    },
    "cartographer-ask": {
      "command": "cartographer ask --db /path/to/index.db",
      "description": "Search the codebase for specific symbols, classes, functions, or files. Arguments: a symbol name to search for",
      "args": ["{{input}}"]
    },
    "cartographer-architecture": {
      "command": "cartographer architecture --detect --db /path/to/index.db",
      "description": "Detect the repository architecture including layers, patterns, frameworks, and dependency flows",
      "args": []
    },
    "cartographer-impact": {
      "command": "cartographer impact --db /path/to/index.db --max-tokens 1000",
      "description": "Find what depends on a given file or symbol. Arguments: file path or symbol name",
      "args": ["{{input}}"]
    },
    "cartographer-summarize": {
      "command": "cartographer summarize --db /path/to/index.db --max-tokens 1000",
      "description": "Generate a high-level summary of the repository",
      "args": []
    },
    "cartographer-git-blame": {
      "command": "cartographer git blame --db /path/to/index.db",
      "description": "Find who wrote a file or symbol. Arguments: file path or symbol name",
      "args": ["{{input}}"]
    },
    "cartographer-git-why": {
      "command": "cartographer git why --db /path/to/index.db",
      "description": "Find which commit introduced a file or symbol. Arguments: file path or symbol name",
      "args": ["{{input}}"]
    },
    "cartographer-embed": {
      "command": "cartographer embed --db /path/to/index.db",
      "description": "Generate vector embeddings for semantic search. Run this once after indexing to enable semantic queries",
      "args": []
    }
  }
}
```

### 2. Index your repository

```bash
cartographer --db /path/to/index.db index /path/to/repo
```

### 3. (Optional) Generate embeddings

```bash
cartographer --db /path/to/index.db embed
```

### 4. (Optional) Index git history

```bash
cd /path/to/repo && cartographer --db /path/to/index.db git index
```

### Alternative: Use the MCP Server

Instead of configuring individual tools, you can run the MCP server directly. Cartographer supports the Model Context Protocol (MCP), which lets AI assistants discover and call tools automatically:

```bash
cartographer mcp start
```

Configure your assistant to connect to the MCP server:

**Claude Desktop / Cursor / OpenCode:**
```json
{
  "mcpServers": {
    "cartographer": {
      "command": "cartographer-mcp",
      "args": ["--db", "/path/to/custom.db"]
    }
  }
}
```

The MCP server exposes **14 tools** — `search`, `impact`, `neighbors`, `path`, `summarize`, `architecture`, `similar`, `ask`, `graph_data`, `index`, `context`, `update_index`, `delete_file`, and `db_info` — plus 3 resources (`cartographer://repos`, `cartographer://repo/{name}`, `cartographer://node/{node_id}`). All tools accept optional `repo` and `db` parameters.

---

## Agent Integration Pattern

### Tool Selection Guide

| Agent Task | Best Tool | Why |
|---|---|---|---|
| "What is this project?" | `cartographer-summarize` | High-level overview |
| "Explain the architecture" | `cartographer-architecture` | Layer + pattern detection |
| "Give me full context" | `cartographer-context` | Token-budgeted summary + architecture + top nodes |
| "How does X work?" | `cartographer-query "explain X"` | Combines search + impact |
| "Where is Y defined?" | `cartographer-ask Y` | Direct symbol lookup |
| "What uses Z?" | `cartographer-query "what depends on Z"` | Impact analysis grouped by edge type |
| "Who wrote this?" | `cartographer-git-blame` | Git history |
| "Why does this exist?" | `cartographer-git-why` | Commit that introduced it |
| "What's the relationship between A and B?" | `cartographer-query "path between A and B"` | Graph path finding |

### Query Intent Mapping

When you use `cartographer query`, it automatically detects intent:

| Query Pattern | Intent | Example |
|---|---|---|
| "what is the architecture" | architecture | returns layers + patterns + frameworks |
| "explain X" | explain | returns nodes + dependents |
| "what depends on X" | impact | returns grouped dependents |
| "path between X and Y" | path | returns path hops |
| "summarize" | summarize | returns repo statistics |
| "who wrote X" | git_blame | returns commit history |
| "why was X introduced" | git_why | returns introducing commit |
| "what changes with X" | git_cochange | returns co-changing files |
| (anything else) | search | returns matching nodes |

### Token Savings Analysis

When an AI agent reasons about code without Cartographer, it must read raw source files — each file consuming hundreds to thousands of tokens. With Cartographer's MCP tools, structured graph queries replace raw file reads, reducing token consumption by 90–98% per interaction.

#### Measured Savings

| Task | Without Cartographer | With Cartographer | Savings |
|---|---|---|---|
| Repo onboarding | Read 50+ files (~60K tokens) | `summarize` + `architecture` (~700 tokens) | **98.8%** |
| "How does X work?" | Read X + imports + callers (5–8 files, ~6K tokens) | `search X` + `impact X` (~500 tokens) | **91.7%** |
| "What depends on Y?" | grep + read each dependent (~12K tokens) | `impact Y` (~300 tokens) | **97.5%** |
| Architecture overview | Read directory tree + configs (~15K tokens) | `architecture --detect` (~500 tokens) | **96.7%** |

#### Why It Matters

1. **Context window headroom**: 96% fewer tokens for code retrieval leaves space for instructions, conversation history, and reasoning
2. **Lower latency**: Fewer tokens = faster generation (10x on a 4K vs 100K token response)
3. **Fewer hallucinations**: Graph queries return exact, structured answers rather than LLM-inferred guesses
4. **Deterministic caching**: Graph output is identical every call — ideal for KV-cache optimization

#### Compression for Token Budgets

All commands support `--max-tokens` / `-m` to limit output size:

```bash
cartographer query -m 500 "explain the authentication system"
cartographer impact -m 200 "config.py"
cartographer ask -m 100 "UserService"
```

Compression strategies:
- **Nodes** (ask, search): groups by type when >10 results, shows counts + top files
- **Impact**: groups by edge type, shows top N per group
- **Path**: maintains structure, truncates from end
- **Summary**: condenses to top types/files, truncates lists

---

## Workflow: Onboarding to a New Repository

### Step 1: Index

```bash
cartographer index /path/to/repo
```

### Step 2: Get oriented

```
Agent → cartographer-summarize
→ "1200 files, 500 classes, 3000 functions, languages: Python, JavaScript"
```

### Step 3: Understand structure

```
Agent → cartographer-architecture
→ "MVC architecture, Django framework, layers: Controller, Data, Presentation"
```

### Step 4: Explore key components

```
Agent → cartographer-query "explain the UserService class"
→ "Found 3 matching nodes, 12 dependents via IMPORTS"
```

### Step 5: Trace dependencies

```
Agent → cartographer-query "what depends on the user repository"
→ "5 dependents via IMPORTS: UserService, AuthService, AdminController..."
```

### Step 6: Understand history

```
Agent → cartographer-git-blame "config.py"
→ "Modified by Jane Doe, last change: 'Add database config' (2024-03-15)"
```

---

## Advanced Configuration

### Multiple Database Support

For projects with multiple repositories:

```jsonc
{
  "tools": {
    "cartographer-repo1-query": {
      "command": "cartographer query --db /path/to/repo1.db -m 2000",
      "description": "Query the repo1 knowledge graph",
      "args": ["{{input}}"]
    },
    "cartographer-repo2-query": {
      "command": "cartographer query --db /path/to/repo2.db -m 2000",
      "description": "Query the repo2 knowledge graph",
      "args": ["{{input}}"]
    }
  }
}
```

### Automation Script

For CI/CD integration, create a re-indexing script:

```bash
#!/bin/bash
# reindex.sh — Run after code changes
REPO_PATH="${1:-.}"

echo "Re-indexing $REPO_PATH..."
CARTOGRAPHER_DB="$DB_PATH" cartographer index "$REPO_PATH"
CARTOGRAPHER_DB="$DB_PATH" cartographer embed
echo "Done. Updated knowledge graph at $REPO_PATH/.cartographer/data.db"
```

---

## Troubleshooting

### No results from query

1. Make sure the repository is indexed: `cartographer ask "test"` should return results
2. Check the DB path: `cartographer --db /path/to/db ask "test"`
3. Try a simpler query: `cartographer ask "handler"`

### Semantic search returns nothing

1. Run `cartographer embed` first
2. Check the model downloaded successfully (first run downloads ~33MB)

### Git commands return nothing

1. Run `cartographer git index` first
2. Check the path: `cartographer git index -p /path/to/repo`
3. Large repos may need `--max-count` to limit commit indexing

### Token budget still too tight?

See the [Whitepaper](whitepaper.md) for detailed token savings analysis and benchmark data across 14 real-world repositories.

### Tool timeout in OpenCode

Add `-m` flag to limit output:

```jsonc
"cartographer-query": {
  "command": "cartographer query -m 1500 --db /path/to/index.db",
  ...
}
```
