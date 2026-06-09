# Cartographer — Technical Architecture Document

**Version:** 0.1.0 Explorer
**Status:** Research & Prototype Phase

---

## Table of Contents

1. [System Overview](#system-overview)
2. [System Architecture](#system-architecture)
3. [Core Subsystems](#core-subsystems)
4. [Data Model](#data-model)
5. [Storage Layer](#storage-layer)
6. [Query Engine](#query-engine)
7. [CLI Specification](#cli-specification)
8. [MCP Integration](#mcp-integration)
9. [Performance Targets](#performance-targets)
10. [Benchmark Suite](#benchmark-suite)
11. [Success Criteria](#success-criteria)

---

## System Overview

Cartographer transforms software repositories into navigable semantic knowledge graphs. It is an intelligence layer that sits between repositories and their consumers (humans, AI agents, developer tools), enabling architecture-aware retrieval, impact analysis, and context compression.

### Core Principles

| Principle | Description |
|---|---|
| Structure beats tokens | Graph structure is more valuable than raw token count |
| Relationships > files | Edges between entities carry more meaning than isolated files |
| Knowledge should be traversable | Graphs enable navigation, not just search |
| Architecture should be automatic | No manual annotation required |
| AI agents consume graphs | Agents reason over graphs, not file trees |

---

## System Architecture

```
Repository
│
├── Source Code
├── Documentation
├── Git History
├── Configurations
├── APIs
├── Schemas
│
▼
┌─────────────────────┐
│   Ingestion Layer    │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│    Parsing Layer     │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│    Graph Builder     │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   Semantic Layer     │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│ Architecture Engine  │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   Knowledge Graph    │
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│  Retrieval Engine    │
└─────────────────────┘
          │
          ▼
   Humans / AI Agents
```

---

## Core Subsystems

| Subsystem | Responsibility |
|---|---|
| Ingestion Engine | Repository discovery, language/framework detection, tech fingerprinting |
| Parser Engine | Tree-sitter based AST extraction for all supported languages |
| Graph Engine | Build and maintain the repository knowledge graph (nodes + edges) |
| Embedding Engine | Generate vector embeddings for semantic understanding |
| Architecture Engine | Automatically infer architecture layers, patterns, and service boundaries |
| Retrieval Engine | Multi-stage retrieval (candidate discovery, graph expansion, ranking, packaging) |
| Compression Engine | Reduce token count via graph summarization |
| Git Intelligence Engine | Parse commits, authors, branches, tags, releases |
| Query Planner | Choose optimal retrieval strategy per query |
| Visualization Engine | Graph rendering and exploration UI |
| MCP Integration Layer | Expose graph capabilities to AI agents via Model Context Protocol |

### 1. Ingestion Engine

Detects and fingerprints repository characteristics:

- **Languages** — Python, JavaScript, TypeScript, Go, Rust, etc.
- **Frameworks** — Django, FastAPI, Spring, Express, Next.js, NestJS, Laravel, Actix, etc.
- **Package Managers** — npm, pip, cargo, go mod, etc.
- **Build Systems** — Webpack, esbuild, Make, CMake, etc.
- **Monorepo Detection** — Workspaces, packages, modules

Output: structured framework metadata with confidence scores:
```json
{
  "framework": "Django",
  "confidence": 0.98
}
```

### 2. Parser Engine

Based on Tree-sitter for language-agnostic AST parsing.

#### Phase 1 (MVP)
- Python, JavaScript, TypeScript, Go, Rust

#### Phase 2
- Java, Kotlin, C#, PHP, Ruby

#### Phase 3
- C, C++, Swift

### 3. Embedding Engine

Generates vector embeddings for semantic understanding of code and documentation.

#### Embedding Targets
- Functions, Classes, Files, APIs, Documentation, Commits, Issues

#### Model Strategy

| Stage | Model |
|---|---|
| MVP | `bge-small` |
| Alternative | `nomic-embed` |
| Future | Custom repository embeddings |

---

## Data Model

The knowledge graph consists of typed **nodes** connected by typed **edges**, stored in SQLite.

### Node Types

#### Structural Nodes
| Node | Example |
|---|---|
| Repository | `cartographer` |
| Directory | `backend/` |
| File | `auth.py` |
| Module | `src.auth` |
| Package | `django-rest-framework` |
| Class | `JWTManager` |
| Function | `authenticate_user()` |
| Method | `user.save()` |
| Interface | `RepositoryInterface` |
| Enum | `Status` |
| Constant | `MAX_RETRIES` |

#### Application Nodes
| Node | Example |
|---|---|
| API Endpoint | `POST /auth/login` |
| Controller | `AuthController` |
| Service | `PaymentService` |
| Repository (data) | `UserRepository` |
| Middleware | `AuthMiddleware` |
| Job | `EmailNotificationJob` |
| Worker | `QueueWorker` |
| Queue | `email_queue` |

#### Infrastructure Nodes
| Node | Example |
|---|---|
| Database | `PostgreSQL` |
| Table | `users` |
| Index | `idx_users_email` |
| Cache | `Redis` |
| Bucket | `S3:assets` |
| Topic | `order_events` |
| Container | `api-server` |
| Deployment | `production-us-east` |

#### Documentation Nodes
| Node | Example |
|---|---|
| Markdown | `README.md` |
| ADR | `adr-001-use-postgres.md` |
| Diagram | `architecture.puml` |
| Wiki | `Home` |
| Comment Block | docstring on `class Auth` |

#### Historical Nodes
| Node | Example |
|---|---|
| Commit | `a1b2c3d` |
| Author | `alice@example.com` |
| Branch | `main` |
| Tag | `v1.0.0` |
| Release | `Release v1.0.0` |

### Edge Types

#### Structural
| Edge | Description |
|---|---|
| `CONTAINS` | Directory → File, File → Class |
| `DEFINES` | File → Function |
| `DECLARES` | File → Variable/Constant |

#### Dependency
| Edge | Description |
|---|---|
| `IMPORTS` | File → Module |
| `CALLS` | Function → Function |
| `USES` | Class → Class |
| `REFERENCES` | Symbol → Symbol |
| `DEPENDS_ON` | Module → Package |

#### OOP
| Edge | Description |
|---|---|
| `INHERITS` | Class → Class |
| `IMPLEMENTS` | Class → Interface |
| `OVERRIDES` | Method → Method |

#### API
| Edge | Description |
|---|---|
| `EXPOSES` | Controller → Endpoint |
| `CONSUMES` | Service → API |
| `RETURNS` | Function → Type |

#### Database
| Edge | Description |
|---|---|
| `READS` | Function → Table |
| `WRITES` | Function → Table |
| `MIGRATES` | Migration → Table |

#### Historical
| Edge | Description |
|---|---|
| `CREATED_BY` | Entity → Author |
| `MODIFIED_BY` | Entity → Author |
| `INTRODUCED_IN` | Entity → Commit |
| `REMOVED_IN` | Entity → Commit |

#### Semantic
| Edge | Description |
|---|---|
| `SIMILAR_TO` | Node → Node (function similarity) |
| `RELATED_TO` | Node → Node (co-change) |
| `DUPLICATES` | Node → Node (duplicate logic) |
| `PATTERN_MATCH` | Node → Node (architectural pattern) |

---

## Storage Layer

### Primary Datastore

**SQLite** — single-file, portable, zero-configuration.

### Tables

| Table | Purpose |
|---|---|
| `nodes` | All graph entities (typed nodes with metadata) |
| `edges` | All graph relationships (typed edges) |
| `embeddings` | Vector storage for semantic search |
| `repositories` | Repository metadata (name, language, framework, index state) |
| `commits` | Git history indexed for temporal queries |
| `architecture` | Discovered architecture layers, patterns, and boundaries |

---

## Query Engine

### Query Lifecycle

```
Question
    ↓
Intent Detection
    ↓
Query Planning
    ↓
Graph Retrieval
    ↓
Expansion
    ↓
Ranking
    ↓
Compression
    ↓
Output
```

### Query Categories

| Category | Example |
|---|---|
| Feature Discovery | "Where is authentication implemented?" |
| Impact Analysis | "What breaks if JWT changes?" |
| Architecture | "Explain checkout architecture." |
| Historical | "Why was RabbitMQ added?" |
| Refactoring | "Find duplicated validation logic." |

### Query Planner

Selects optimal retrieval strategy based on intent:

| Intent | Strategy |
|---|---|
| Dependency impact | Dependency Traversal (graph walk) |
| Feature location | Semantic Search + Graph Search |
| Architecture explanation | Subgraph extraction |
| Historical reasoning | Git graph traversal |
| Similarity/copy-paste | Embedding similarity |

### Retrieval Stages

| Stage | Description |
|---|---|
| 1. Candidate Discovery | Semantic, keyword, graph, or hybrid search |
| 2. Graph Expansion | Traverse neighboring nodes with relevant edge types |
| 3. Relevance Scoring | Rank by semantic similarity, graph distance, frequency, recency, centrality |
| 4. Context Packaging | Compress into minimal graph context |

### Context Compression

| Method | Token Count |
|---|---|
| Traditional (50 files) | ~40,000 tokens |
| Cartographer (graph summary + critical nodes + architecture) | ~2,000 tokens |

Target: **80–95% context reduction**.

---

## CLI Specification

| Command | Description |
|---|---|
| `cartographer index .` | Index current repository |
| `cartographer ask "Where is authentication?"` | Query the knowledge graph |
| `cartographer architecture` | Discover and display repository architecture |
| `cartographer impact jwt.py` | Impact analysis for a file/symbol |
| `cartographer similar auth_service.py` | Find semantically similar code |
| `cartographer summarize` | Generate repository summary |

---

## MCP Integration

Exposes repository intelligence to AI agents via **Model Context Protocol**.

### MCP Tools

| Tool | Function |
|---|---|
| `search` | Search the knowledge graph |
| `impact` | Perform impact analysis |
| `architecture` | Explain repository architecture |
| `neighbors` | Traverse graph relationships |
| `summarize` | Generate compressed repository context |

---

## Architecture Discovery Engine

Automatically infers architecture without manual annotation.

### Detection Capabilities

| Category | What is Detected |
|---|---|
| Layer Detection | Presentation, Business, Persistence, Infrastructure |
| Pattern Detection | Repository, Factory, Adapter, Observer, CQRS, Event Sourcing |
| Service Boundaries | Auth, Payment, User, Notification domains |
| Data Flow | Request → Controller → Service → Repository → Database |

---

## Git Intelligence Engine

Supports historical and temporal reasoning:

- "Why was Redis introduced?"
- "What changed in authentication during 2025?"
- "Who understands payment infrastructure?"
- "What files usually change together?"

---

## Performance Targets

| Repository Size | Index Time |
|---|---|
| Small (100k LOC) | < 30s |
| Medium (1M LOC) | < 10 min |
| Large (10M LOC) | Incremental indexing |

### Key Metrics

- Sub-second graph queries
- Million-line repository support

---

## Benchmark Suite

### Baselines

- `grep` — baseline text search
- `ripgrep` — fast regex baseline
- Vector search — embedding-only baseline
- RAG — naive retrieval-augmented generation
- IDE search — VS Code / JetBrains search

### Evaluation Metrics

| Metric | Description |
|---|---|
| Precision | Fraction of relevant results |
| Recall | Fraction of relevant results retrieved |
| MRR | Mean Reciprocal Rank |
| Context Compression Ratio | Tokens saved vs. raw retrieval |
| Query Latency | Time to first result |
| Graph Coverage | Percentage of entities in graph |
| Architecture Detection Accuracy | Correctness of inferred architecture |

---

## Success Criteria

Cartographer is successful if:

- **80%+ context reduction** vs. traditional retrieval
- **Better retrieval** than vector-only systems (measured by MRR/precision/recall)
- **Accurate dependency analysis** — correct transitive impact identification
- **Accurate architecture detection** — layers, patterns, boundaries
- **Sub-second graph queries** for typical developer questions
- **Million-line repository support** without degradation

---

## Future Roadmap

| Version | Milestone |
|---|---|
| V1 | Repository graph engine |
| V2 | Visual explorer |
| V3 | VS Code integration |
| V4 | MCP server |
| V5 | Multi-repository graphs |
| V6 | Organization knowledge graph |
| V7 | Repository digital twin |

---

## Questions Cartographer Answers

```
Why was Redis introduced?
What changed in authentication during 2025?
Who understands payment infrastructure?
What files usually change together?
Where is authentication implemented?
What breaks if JWT changes?
Explain checkout architecture.
Why was RabbitMQ added?
Find duplicated validation logic.
```
