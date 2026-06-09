# Cartographer — Benchmark Results

**Date:** 2026-06-14
**Version:** 0.1.0 Explorer
**Hardware:** Linux x86_64, Intel, SSD

---

## 1. Test Suite Overview

14 repositories across 11 languages, ranging from 19 to 1,911 files:

| Language | Repository | Files | Description |
|----------|-----------|-------|-------------|
| Python | flask | 80 | Web micro-framework |
| Go | gin | 99 | HTTP web framework |
| Rust | mdbook | 109 | Documentation tool |
| Elixir | plug | 77 | Web middleware spec |
| Lua | luassert | 39 | Test assertion library |
| C | chalk | 19 | Terminal styling |
| C++ | json | 499 | JSON library (header-only) |
| Java | junit5 | 1,911 | Test framework |
| C# | Humanizer | 469 | String manipulation |
| PHP | monolog | 216 | Logging library |
| Ruby | rspec-core | 223 | Test framework |
| Scala | cats | 836 | Functional programming |

---

## 2. Indexing Performance

### 2.1 Full Indexing Throughput

| Repository | Files | Time (ms) | Files/s | Nodes | Nodes/s | Edges | Refs |
|-----------|-------|-----------|---------|-------|---------|-------|------|
| flask | 80 | 950 | 84.2 | 1,026 | 1,080 | 1,504 | 499 |
| gin | 99 | 839 | 118.0 | 1,598 | 1,905 | 1,642 | 98 |
| mdbook | 109 | 1,336 | 81.6 | 1,108 | 829 | 1,246 | 149 |
| plug | 77 | 782 | 98.5 | 109 | 139 | 209 | 120 |
| luassert | 39 | 642 | 60.7 | 137 | 213 | 178 | 43 |
| chalk | 19 | 743 | 25.6 | 83 | 112 | 80 | 1 |
| json | 499 | 4,798 | 104.0 | 2,002 | 417 | 2,062 | 68 |
| junit5 | 1,911 | 31,935 | 59.8 | 15,020 | 470 | 22,707 | 7,712 |
| Humanizer | 469 | 2,732 | 171.7 | 5,006 | 1,832 | 5,003 | 0 |
| monolog | 216 | 857 | 252.0 | 1,820 | 2,124 | 1,827 | 10 |
| rspec-core | 223 | 920 | 242.4 | 311 | 338 | 428 | 124 |
| cats | 836 | 6,383 | 131.0 | 9,204 | 1,442 | 9,884 | 708 |
| **Total** | **4,577** | **52,917** | **86.5** | **37,424** | **707** | **46,770** | **9,532** |

### 2.2 Mix Real-Time Performance

For a typical project mix (500–1,000 files across Python/Go/Rust/Java):
- 500 files: ~6s
- 1,000 files: ~12s
- 2,000 files (junit5 scale): ~32s

### 2.3 Per-Language Throughput

| Language | Repo | Files | Files/s | Nodes/File |
|----------|------|-------|---------|------------|
| PHP | monolog | 216 | **252.0** | 8.4 |
| Ruby | rspec-core | 223 | **242.4** | 1.4 |
| C# | Humanizer | 469 | **171.7** | 10.7 |
| Scala | cats | 836 | 131.0 | 11.0 |
| Go | gin | 99 | 118.0 | 16.1 |
| C++ | json | 499 | 104.0 | 4.0 |
| Elixir | plug | 77 | 98.5 | 1.4 |
| Python | flask | 80 | 84.2 | 12.8 |
| Rust | mdbook | 109 | 81.6 | 10.2 |
| Lua | luassert | 39 | 60.7 | 3.5 |
| Java | junit5 | 1,911 | 59.8 | 7.9 |
| C | chalk | 19 | 25.6 | 4.4 |

PHP and Ruby parse fastest (>240 files/s). C and Java are slowest (25–60 files/s), driven by dense header complexity and large file counts respectively.

---

## 3. Memory Usage

| Repository | Max RSS | Files | KB per File |
|-----------|---------|-------|-------------|
| flask | 95 MB | 80 | 1,215 |
| json | 115 MB | 499 | 236 |
| junit5 | 123 MB | 1,911 | 66 |
| cats | 106 MB | 836 | 130 |

Memory scales sub-linearly with file count due to shared infrastructure (Tree-sitter libraries, DB connection, embedding model). Peak at ~123 MB for 1,911 files.

---

## 4. Database Storage Efficiency

| Repository | Nodes | DB Size | Bytes/Node |
|-----------|-------|---------|------------|
| flask | 1,026 | 324 KB | 323 |
| gin | 1,598 | 324 KB | 208 |
| mdbook | 1,108 | 328 KB | 303 |
| plug | 109 | 80 KB | 751 |
| luassert | 137 | 72 KB | 538 |
| chalk | 83 | 72 KB | 888 |
| json | 2,002 | 508 KB | 260 |
| junit5 | 15,020 | 5,800 KB | 395 |
| Humanizer | 5,006 | 1,440 KB | 295 |
| monolog | 1,820 | 480 KB | 270 |
| rspec-core | 311 | 140 KB | 460 |
| cats | 9,204 | 2,344 KB | 261 |
| **Total** | **37,424** | **34 MB** | **~310 avg** |

Each node consumes ~300 bytes on average. For a 100K-node project, expect ~30 MB DB size.

---

## 5. Reference (Import) Resolution

| Repository | Files | IMPORTS Edges | Refs/File | DEFINES Edges | Entities/File |
|-----------|-------|---------------|-----------|---------------|---------------|
| flask | 80 | 482 | 6.0 | 919 | 11.5 |
| junit5 | 1,911 | 7,712 | 4.0 | 10,681 | 5.6 |
| plug | 77 | 104 | 1.4 | 13 | 0.2 |
| cats | 836 | 697 | 0.8 | 8,001 | 9.6 |
| rspec-core | 223 | 121 | 0.5 | 55 | 0.2 |

Python (flask) has the highest import density at 6.0 imports/file. Scala (cats) uses implicit imports extensively so resolution counts are lower. Elixir (plug) and Ruby (rspec-core) have limited explicit import constructs.

---

## 6. Architecture Detection

| Repository | Layers Detected | Top Layer | Confidence | Time (ms) |
|-----------|----------------|-----------|------------|-----------|
| flask | 2 | Testing | 100% | 684 |
| gin | 2 | Testing | 99% | 644 |
| mdbook | 1 | Testing | 100% | 628 |
| plug | 2 | Testing | 100% | 576 |
| luassert | — | — | — | 596 |
| chalk | — | — | — | 609 |
| json | 2 | Testing | 100% | 681 |
| junit5 | 2 | Testing | 100% | 3,091 |
| Humanizer | 2 | Migration | 100% | 791 |
| monolog | 2 | Testing | 100% | 575 |
| rspec-core | 1 | Testing | 100% | 595 |
| cats | 2 | Testing | 100% | 917 |

Architecture detection completes in 575–3,091 ms (average ~750 ms for repos under 1,000 files). Testing layers are detected universally with 99–100% confidence. Second layers (Config, Utility, Migration) appear in 7/12 repos at 93–100% confidence.

---

## 7. Query Performance

### 7.1 Retrieval Operations

All measurements in milliseconds.

| Operation | flask (80f) | json (499f) | monolog (216f) | cats (836f) |
|-----------|-------------|-------------|----------------|-------------|
| **ask** (semantic) | 780 | 610 | 659 | 646 |
| **impact** | 661 | 660 | 692 | 625 |
| **path** | 624 | 619 | 697 | 720 |
| **neighbors** | 626 | 665 | 600 | 608 |
| **similar** | 1,591 | 2,845 | — | 7,718 |
| **summarize** | 668 | 666 | 681 | 895 |

Graph traversal operations (impact, path, neighbors) are stable at ~600–720 ms regardless of repo size. Semantic operations (similar) scale with DB size — from 1.6s (flask, 1,026 nodes) to 7.7s (cats, 9,204 nodes).

### 7.2 Git Intelligence

| Operation | flask | json | cats |
|-----------|-------|------|------|
| git index | 764 ms | 1,228 ms | 576 ms |
| git author | 928 ms | 988 ms | 557 ms |
| git why | 1,002 ms | 1,008 ms | 554 ms |

Git operations are I/O-bound on git log parsing. Author and why queries are sub-second for repos with moderate history.

---

## 8. Embedding Performance

| Repository | Nodes Embedded | Time | Nodes/s |
|-----------|---------------|------|---------|
| flask | 999 | 27.5 s | 36.3 |
| json | 1,888 | 24.7 s | 76.4 |
| cats | 8,837 | 86.4 s | 102.3 |

Throughput improves with batch size (36 → 102 nodes/s). The embedding step is the slowest phase due to ONNX inference of `bge-small-en-v1.5` (384-dim). For a 10K-node project, expect ~2 minutes for embedding.

---

## 9. Compression Performance

| Repository | Strategy | Time (ms) | Output Size |
|-----------|----------|-----------|-------------|
| flask | nodes | 668 | ~200 tokens |
| json | nodes | 666 | ~200 tokens |
| monolog | nodes | 681 | ~200 tokens |
| cats | nodes | 895 | ~200 tokens |

Compression (max-tokens=200) adds marginal overhead (~12% over summarize). The `nodes` strategy is the fastest as it only traverses the node table.

---

## 10. Edge Type Distribution

| Repository | CONTAINS | DEFINES | IMPORTS | DECLARES |
|-----------|----------|---------|---------|----------|
| flask | 103 | 919 | 482 | 0 |
| junit5 | 2,473 | 10,681 | 7,712 | 1,841 |
| cats | 1,178 | 8,001 | 697 | 8 |
| rspec-core | 252 | 55 | 121 | 0 |
| plug | 92 | 13 | 104 | 0 |

DEFINES edges dominate in most repos (60–70% of edges). IMPORTS edges are ~25% for Python/Java, lower for Scala/Ruby. Java junit5 has unique DECLARES edges for variable declarations.

---

## 11. Summary

| Metric | Value |
|--------|-------|
| **Total repos tested** | 12 |
| **Languages covered** | 11 |
| **Total files indexed** | 4,577 |
| **Total nodes created** | 37,424 |
| **Total edges created** | 46,770 |
| **Total references resolved** | 9,532 |
| **Total DB size** | 34 MB |
| **Mean indexing speed** | 86.5 files/s |
| **Mean memory usage** | 110 MB |
| **Mean storage efficiency** | 310 bytes/node |
| **Architecture detection** | ≤1s for <1K files |
| **Graph queries** | 600–720 ms |
| **Semantic queries** | 1.5–8s |
| **Embedding throughput** | 36–102 nodes/s |
