# Cartographer

## Repository Intelligence Operating System

### Founder-Level Product Requirements Document (PRD)

**Version:** 0.1.0 Explorer
**Status:** Research & Prototype Phase
**Category:** Developer Infrastructure / AI Infrastructure / Knowledge Graphs
**Product Type:** Repository Operating System
**Primary Audience:** Software Engineers, AI Agent Developers, Engineering Teams

---

# Executive Summary

Cartographer is a repository intelligence operating system that transforms software projects into navigable semantic knowledge graphs.

Current development tools treat repositories as collections of files.

Cartographer treats repositories as interconnected knowledge systems.

Instead of searching code:

```text
Find authentication
```

developers and AI agents can reason about:

```text
How does authentication work?

What breaks if JWT changes?

Why was Redis introduced?

Which architectural layer owns caching?

Show all payment-related business logic.
```

Cartographer acts as an intelligence layer sitting between:

```text
Repository
↓
Cartographer
↓
Humans
AI Agents
Developer Tools
```

The system creates a continuously updated semantic representation of software systems capable of supporting:

- Architecture discovery
- Impact analysis
- Knowledge retrieval
- Dependency analysis
- Context compression
- AI agent memory
- Repository exploration

---

# Vision

Every repository should have a map.

Modern software systems have become too complex for humans or AI agents to understand solely through source code.

Cartographer provides the missing abstraction layer:

```text
Maps for software.
```

---

# Mission

Transform repositories into navigable knowledge graphs that can be understood by humans and machines alike.

---

# Long-Term Vision

Ten years from now repositories will not be searched.

They will be queried.

Developers will not navigate files.

They will navigate knowledge.

AI agents will not read codebases.

They will reason over repository graphs.

Cartographer aims to become the standard intelligence layer for software systems.

---

# Problem Analysis

## Problem 1: Code Is Not Knowledge

Repositories contain:

- Code
- Documentation
- Configurations
- APIs
- Database schemas
- Commits
- Architecture

Current tools primarily understand:

```python
def login():
```

They do not understand:

```text
Authentication System
```

---

## Problem 2: AI Context Explosion

Current AI coding workflows:

```text
Question
↓
Search
↓
Retrieve Files
↓
Send Thousands Of Tokens
↓
Model
```

Problems:

- Expensive
- Slow
- Context limitations
- Missing relationships

---

## Problem 3: Architecture Is Implicit

Most architecture exists only inside developers' heads.

When senior engineers leave:

```text
Architecture disappears.
```

---

## Problem 4: Onboarding Cost

Large repositories often require:

```text
Weeks
or
Months
```

to understand.

---

# Core Product Principles

## Principle 1

Structure beats tokens.

---

## Principle 2

Relationships are more valuable than files.

---

## Principle 3

Knowledge should be traversable.

---

## Principle 4

Architecture should be discovered automatically.

---

## Principle 5

AI agents should consume graphs instead of repositories.

---

# Product Goals

## G1

Build a universal repository graph.

---

## G2

Support all major programming languages.

---

## G3

Provide architecture-aware retrieval.

---

## G4

Provide graph-aware AI context generation.

---

## G5

Reduce context usage by 80-95%.

---

## G6

Support million-line repositories.

---

# System Architecture

```text
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
Ingestion Layer
│
▼
Parsing Layer
│
▼
Graph Builder
│
▼
Semantic Layer
│
▼
Architecture Engine
│
▼
Knowledge Graph
│
▼
Retrieval Engine
│
▼
Humans / AI Agents
```

---

# Core Subsystems

1. Ingestion Engine
2. Parser Engine
3. Graph Engine
4. Embedding Engine
5. Architecture Engine
6. Retrieval Engine
7. Compression Engine
8. Git Intelligence Engine
9. Query Planner
10. Visualization Engine
11. MCP Integration Layer

---

# Ingestion Engine

## Purpose

Transform repositories into graph-ready data.

---

## Responsibilities

### Repository Discovery

Detect:

```text
Languages
Frameworks
Package Managers
Build Systems
Monorepos
```

---

### Technology Detection

Examples:

```text
Django
FastAPI
Spring
Express
Next.js
NestJS
Laravel
Rust Actix
```

---

### Framework Fingerprinting

Generate:

```json
{
  "framework": "Django",
  "confidence": 0.98
}
```

---

# Parser Engine

## Technology

Tree-sitter

---

## Supported Languages

### Phase 1

- Python
- JavaScript
- TypeScript
- Go
- Rust

### Phase 2

- Java
- Kotlin
- C#
- PHP
- Ruby

### Phase 3

- C
- C++
- Swift

---

# Extracted Entities

## Repository

```text
Atlas
```

---

## Directory

```text
backend/
```

---

## File

```text
auth.py
```

---

## Function

```python
authenticate_user()
```

---

## Class

```python
JWTManager
```

---

## Interface

```go
RepositoryInterface
```

---

## Endpoint

```http
POST /auth/login
```

---

## Database Table

```sql
users
```

---

## Environment Variable

```env
DATABASE_URL
```

---

## Docker Service

```yaml
postgres
```

---

## Queue

```python
email_queue
```

---

# Graph Engine

## Purpose

Represent repositories as interconnected graphs.

---

# Node Types

## Structural Nodes

```text
Repository
Directory
File
Module
Package
Class
Function
Method
Interface
Enum
Constant
```

---

## Application Nodes

```text
API Endpoint
Controller
Service
Repository
Middleware
Job
Worker
Queue
```

---

## Infrastructure Nodes

```text
Database
Table
Index
Cache
Bucket
Topic
Container
Deployment
```

---

## Documentation Nodes

```text
Markdown
ADR
Diagram
Wiki
Comment Block
```

---

## Historical Nodes

```text
Commit
Author
Branch
Tag
Release
```

---

# Edge Types

## Structural

```text
CONTAINS
DEFINES
DECLARES
```

---

## Dependency

```text
IMPORTS
CALLS
USES
REFERENCES
DEPENDS_ON
```

---

## OOP

```text
INHERITS
IMPLEMENTS
OVERRIDES
```

---

## API

```text
EXPOSES
CONSUMES
RETURNS
```

---

## Database

```text
READS
WRITES
MIGRATES
```

---

## Historical

```text
CREATED_BY
MODIFIED_BY
INTRODUCED_IN
REMOVED_IN
```

---

## Semantic

```text
SIMILAR_TO
RELATED_TO
DUPLICATES
PATTERN_MATCH
```

---

# Embedding Engine

## Purpose

Capture meaning.

---

## Embedded Objects

### Functions

### Classes

### Files

### APIs

### Documentation

### Commits

### Issues

---

# Embedding Models

## MVP

```text
bge-small
```

---

## Alternative

```text
nomic-embed
```

---

## Future

Custom repository embeddings.

---

# Architecture Discovery Engine

## Purpose

Infer architecture automatically.

---

# Detection Categories

## Layer Detection

Detect:

```text
Presentation Layer
Business Layer
Persistence Layer
Infrastructure Layer
```

---

## Pattern Detection

Detect:

```text
Repository Pattern
Factory Pattern
Adapter Pattern
Observer Pattern
CQRS
Event Sourcing
```

---

## Service Boundaries

Detect:

```text
Auth Domain
Payment Domain
User Domain
Notification Domain
```

---

## Data Flow Discovery

Infer:

```text
Request
↓
Controller
↓
Service
↓
Repository
↓
Database
```

---

# Git Intelligence Engine

## Parse

### Commits

### Authors

### Releases

### Branches

### Tags

---

# Questions Supported

```text
Why was Redis introduced?
```

```text
What changed in authentication during 2025?
```

```text
Who understands payment infrastructure?
```

```text
What files usually change together?
```

---

# Semantic Similarity Engine

## Purpose

Discover hidden relationships.

---

# Similarity Types

## Function Similarity

Detect duplicate business logic.

---

## Architectural Similarity

Detect repeated architecture.

---

## Module Similarity

Detect overlapping responsibilities.

---

# Query Engine

## Query Lifecycle

```text
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

---

# Query Categories

## Feature Discovery

```text
Where is authentication implemented?
```

---

## Impact Analysis

```text
What breaks if JWT changes?
```

---

## Architecture Questions

```text
Explain checkout architecture.
```

---

## Historical Questions

```text
Why was RabbitMQ added?
```

---

## Refactoring Questions

```text
Find duplicated validation logic.
```

---

# Query Planner

e

## Purpose

Choose optimal retrieval strategy.

---

# Example

Question:

```text
What breaks if payment_service changes?
```

Planner chooses:

```text
Dependency Traversal
```

instead of

```text
Semantic Search
```

---

# Retrieval Engine

## Stage 1

Initial Candidate Discovery

Methods:

```text
Semantic Search
Keyword Search
Graph Search
Hybrid Search
```

---

## Stage 2

Graph Expansion

Expand neighbors.

---

## Stage 3

Relevance Scoring

Factors:

```text
Semantic Similarity
Graph Distance
Usage Frequency
Recency
Centrality
```

---

## Stage 4

Context Packaging

Generate compressed graph context.

---

# Context Compression Engine

## Purpose

Reduce tokens.

---

# Traditional Workflow

```text
50 Files
≈
40,000 Tokens
```

---

# Cartographer Workflow

```text
Graph Summary
+
Critical Nodes
+
Architecture Context

≈

2,000 Tokens
```

---

# MCP Integration

## Purpose

Expose repository intelligence to AI agents.

---

# MCP Tools

## search

```text
Search graph
```

---

## impact

```text
Impact analysis
```

---

## architecture

```text
Architecture explanation
```

---

## neighbors

```text
Graph traversal
```

---

## summarize

```text
Generate repository context
```

---

# CLI Specification

## Index Repository

```bash
cartographer index .
```

---

## Ask Questions

```bash
cartographer ask "Where is authentication implemented?"
```

---

## Explain Architecture

```bash
cartographer architecture
```

---

## Impact Analysis

```bash
cartographer impact jwt.py
```

---

## Similarity Search

```bash
cartographer similar auth_service.py
```

---

## Repository Summary

```bash
cartographer summarize
```

---

# Storage Layer

## SQLite

Primary datastore.

---

# Tables

## nodes

Stores graph entities.

---

## edges

Stores graph relationships.

---

## embeddings

Stores vectors.

---

## repositories

Metadata.

---

## commits

History.

---

## architecture

Discovered architecture.

---

# Performance Targets

## Small Repository

100k LOC

Index < 30s

---

## Medium Repository

1M LOC

Index < 10min

---

## Large Repository

10M LOC

Incremental indexing.

---

# Benchmark Suite

## Baselines

### grep

### ripgrep

### vector search

### RAG

### IDE search

---

# Metrics

## Precision

## Recall

## MRR

## Context Compression Ratio

## Query Latency

## Graph Coverage

## Architecture Detection Accuracy

---

# Success Criteria

Cartographer is successful if:

- 80%+ context reduction
- Better retrieval than vector-only systems
- Accurate dependency analysis
- Accurate architecture detection
- Sub-second graph queries
- Support for repositories exceeding one million lines of code

---

# Future Roadmap

## V1

Repository graph engine

---

## V2

Visual explorer

---

## V3

VS Code integration

---

## V4

MCP server

---

## V5

Multi-repository graphs

---

## V6

Organization knowledge graph

---

## V7

Repository digital twin

---

# Ultimate Goal

Create a universal intelligence layer between software repositories and intelligent systems.

Repositories become knowledge graphs.

AI agents consume maps instead of files.

Developers navigate knowledge instead of code.
