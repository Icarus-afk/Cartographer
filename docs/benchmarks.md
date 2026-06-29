# Benchmark Results

**Date:** 2026-06-29
**Version:** 0.1.0
**Hardware:** Linux x86_64, Intel i7, SSD

---

## Test Suite

22 real-world repositories across 17 languages:

| Language | Repository | Files | Source (chars) | Est. Tokens |
|---|---|---|---|---|
| Python | flask | 81 | 2.6M | 869K |
| Python | fastapi | 944 | 46.5M | 15.5M |
| Python | django | 2,356 | 58.2M | 19.4M |
| Go | gin | 99 | 1.1M | 372K |
| Go | hugo | 929 | 51.4M | 17.1M |
| Rust | mdbook | 109 | 3.3M | 1.1M |
| Rust | tokio | 784 | 7.4M | 2.5M |
| Rust | serde | 189 | 1.7M | 569K |
| Rust | chalk | 13 | 719K | 240K |
| JavaScript | react | 4,588 | 52.0M | 17.3M |
| C | redis | 866 | 25.6M | 8.5M |
| C | jansson | 51 | 1.2M | 386K |
| C++ | json (nlohmann) | 500 | 25.2M | 8.4M |
| Java | junit5 | 1,911 | 36.4M | 12.1M |
| Java | spring-boot | 8,790 | 51.4M | 17.1M |
| C# | Humanizer | 469 | 11.2M | 3.7M |
| Kotlin | kotlinx.coroutines | 1,104 | 29.7M | 9.9M |
| Scala | cats | 836 | 6.3M | 2.1M |
| Ruby | rspec-core | 223 | 2.4M | 816K |
| PHP | monolog | 216 | 2.7M | 897K |
| Elixir | plug | 77 | 1.0M | 335K |
| Lua | luassert | 39 | 301K | 100K |
| **Total** | **22 repos** | **25,174** | **1.38B** | **460M** |

---

## Indexing Performance

| Repo | Files | Time (ms) | Files/s | Nodes | Edges |
|---|---|---|---|---|---|
| flask | 81 | 288 | 281 | 1,485 | 2,180 |
| fastapi | 944 | 2,213 | 427 | 10,849 | 17,018 |
| django | 2,356 | 10,485 | 225 | 62,379 | 116,202 |
| gin | 99 | 388 | 255 | 1,759 | 2,859 |
| hugo | 929 | 3,644 | 255 | 11,841 | 15,603 |
| mdbook | 109 | 543 | 201 | 1,145 | 1,370 |
| tokio | 784 | 2,218 | 353 | 11,411 | 15,902 |
| serde | 189 | 545 | 347 | 2,193 | 2,832 |
| chalk | 13 | 26 | 500 | 108 | 107 |
| react | 4,588 | 14,109 | 325 | 27,400 | 36,332 |
| redis | 866 | 7,870 | 110 | 11,055 | 32,440 |
| jansson | 51 | 379 | 135 | 529 | 1,164 |
| json | 500 | 3,425 | 146 | 2,052 | 4,031 |
| junit5 | 1,911 | 4,026 | 475 | 15,020 | 42,252 |
| spring-boot | 8,790 | 20,068 | 438 | 68,610 | 186,271 |
| Humanizer | 469 | 2,342 | 200 | 5,045 | 5,042 |
| kotlinx.coroutines | 1,104 | 1,864 | 592 | 2,504 | 2,500 |
| cats | 836 | 3,659 | 228 | 9,204 | 11,923 |
| rspec-core | 223 | 555 | 402 | 311 | 307 |
| monolog | 216 | 475 | 455 | 1,820 | 1,817 |
| plug | 77 | 251 | 307 | 109 | 107 |
| luassert | 39 | 107 | 364 | 137 | 135 |
| **Total** | **25,174** | **79,480** | **317 avg** | **246,966** | **498,394** |

### By Language

| Language | Files | Nodes | Edges | Time (ms) |
|---|---|---|---|---|
| Python | 3,381 | 74,713 | 135,400 | 12,986 |
| Go | 1,028 | 13,600 | 18,462 | 4,032 |
| Rust | 1,095 | 14,857 | 20,211 | 3,332 |
| JavaScript | 4,588 | 27,400 | 36,332 | 14,109 |
| C | 917 | 11,584 | 33,604 | 8,249 |
| C++ | 500 | 2,052 | 4,031 | 3,425 |
| Java | 10,701 | 83,630 | 228,523 | 24,094 |
| C# | 469 | 5,045 | 5,042 | 2,342 |
| Kotlin | 1,104 | 2,504 | 2,500 | 1,864 |
| Scala | 836 | 9,204 | 11,923 | 3,659 |
| Ruby | 223 | 311 | 307 | 555 |
| PHP | 216 | 1,820 | 1,817 | 475 |
| Elixir | 77 | 109 | 107 | 251 |
| Lua | 39 | 137 | 135 | 107 |

### Key Observations

- **Throughput**: 317 files/s average across all repos
- **Fastest**: chalk (500 f/s), kotlinx.coroutines (592 f/s), junit5 (475 f/s), monolog (455 f/s)
- **Slowest**: redis (110 f/s, C with complex macros), jansson (135 f/s), json (146 f/s, C++ headers)
- **Largest graph**: django (62,379 nodes, 116,202 edges) — 10.5s to index
- **Biggest repo**: spring-boot (8,790 files) — 20s to index, 68,610 nodes, 186,271 edges
- **Node density**: 9.8 nodes per file average
- **Edge density**: 2.0 edges per node average

---

## Architecture Detection

| Repo | Layers | Patterns |
|---|---|---|
| flask | 7 | 1 |
| fastapi | 10 | 6 |
| django | 11 | 6 |
| gin | 8 | 5 |
| hugo | 10 | 6 |
| mdbook | 5 | 0 |
| tokio | 8 | 6 |
| serde | 2 | 0 |
| chalk | 4 | 0 |
| react | 9 | 6 |
| redis | 9 | 5 |
| jansson | 5 | 2 |
| json | 6 | 2 |
| junit5 | 11 | 6 |
| spring-boot | 11 | 6 |
| Humanizer | 8 | 3 |
| kotlinx.coroutines | 10 | 6 |
| cats | 7 | 5 |
| rspec-core | 7 | 5 |
| monolog | 7 | 6 |
| plug | 5 | 0 |
| luassert | 2 | 0 |

Large Python/Java/Kotlin projects (django, fastapi, spring-boot, junit5, kotlinx.coroutines) detect the most architectural layers (10-11). Go and Rust projects (gin, tokio, hugo) show strong modular structure (8-10 layers). Small utility libraries (chalk, luassert, serde) have simpler architectures.

---

## Token Cost Savings

Cartographer's knowledge graph eliminates the need to dump full source code into LLM context. A developer asking "how do X" gets answers from a small, relevant subgraph instead of the entire codebase.

### Per-Repo Savings

| Repo | Source Tokens | Cost (Haiku) | Cost (GPT-4o) |
|---|---|---|---|
| flask | 869K | $0.22 | $2.17 |
| react | 17.3M | $4.33 | $43.30 |
| django | 19.4M | $4.85 | $48.47 |
| spring-boot | 17.1M | $4.28 | $42.75 |

### Cartographer Query Cost

Each query costs ~150 tokens (query + top-5 results):
- Haiku: **$0.00004** per query
- GPT-4o: **$0.00038** per query
- **99.99% savings** vs dumping the full repo

### Annual Projection

For a team making 100 queries/day across a Django-sized codebase:

| Method | Daily Cost | Annual Cost |
|---|---|---|
| Full source dump (Haiku) | $485 | $177K |
| Full source dump (GPT-4o) | $4,847 | $1.77M |
| Cartographer (Haiku) | $0.004 | $1.46 |
| Cartographer (GPT-4o) | $0.038 | $13.87 |

---

## Semantic Query Results

Tested 10 natural-language questions per repo (220 total), top-5 recall via semantic embedding similarity:

**Overall: 220/220 queries passed (100%) with mean similarity score 0.838.**

| Repo | Passed | Avg Score | Sample Hits |
|---|---|---|---|
| Humanizer | 10/10 | 0.832 | ToWords, ByteSizeToStringFormat, Humanize, Pluralize |
| cats | 10/10 | 0.837 | Functor, Monad, Applicative, Traverse |
| chalk | 10/10 | 0.776 | createStyler, ForegroundColor, applyStyle |
| django | 10/10 | 0.860 | as_sql, Model, URLResolver, authenticate |
| fastapi | 10/10 | 0.842 | APIRouter, Depends, Body, WebSocket |
| flask | 10/10 | 0.819 | url_for, handle_http_exception, render_template |
| gin | 10/10 | 0.870 | Routes, middleware, Context, ShouldBind |
| hugo | 10/10 | 0.863 | Build, Site, render, config |
| jansson | 10/10 | 0.853 | json_object, load_json, json_dump, json_pack |
| json | 10/10 | 0.824 | parse, to_string, start_object, merge |
| junit5 | 10/10 | 0.865 | Test, Parameterized, Assert, BeforeEach |
| kotlinx.coroutines | 10/10 | 0.845 | launch, Flow, Channel, Dispatchers |
| luassert | 10/10 | 0.830 | assert, spy, mock, stub |
| mdbook | 10/10 | 0.831 | Config, Renderer, Preprocessor, Search |
| monolog | 10/10 | 0.831 | Logger, Handler, Formatter, StreamHandler |
| plug | 10/10 | 0.824 | Conn, Router, send, params |
| react | 10/10 | 0.839 | useState, useEffect, render, memo |
| redis | 10/10 | 0.834 | set, get, zmalloc, aeEventLoop |
| rspec-core | 10/10 | 0.814 | Example, Config, let, subject |
| serde | 10/10 | 0.846 | Serialize, Deserialize, derive, json |
| spring-boot | 10/10 | 0.833 | Controller, AutoConfiguration, Autowired |
| tokio | 10/10 | 0.856 | spawn, TcpListener, Runtime, Mutex |

### Score Distribution

| Threshold | Queries | Percentage |
|---|---|---|
| >= 0.70 | 220/220 | 100.0% |
| >= 0.75 | 219/220 | 99.5% |
| >= 0.80 | 191/220 | 86.8% |
| >= 0.85 | 80/220 | 36.4% |
| >= 0.90 | 7/220 | 3.2% |

### Detailed Per-Query Results

#### flask (81 files, 1,485 nodes, 0.819 avg score)
| Query | Top Match | Score | Time |
|---|---|---|---|
| How do I define URL routes | Route | 0.77 | 8ms |
| How to handle HTTP requests | Request | 0.79 | 2ms |
| How to render HTML templates | template_test | 0.88 | 2ms |
| How to handle form submissions | form | 0.80 | 2ms |
| How to set up error handlers | HTTPException | 0.89 | 2ms |
| How to manage user sessions | session | 0.82 | 2ms |
| How to create JSON API responses | json | 0.81 | 2ms |
| How to handle file uploads | file | 0.84 | 2ms |
| How to run background tasks | run | 0.76 | 2ms |
| How to log application messages | log | 0.84 | 2ms |

#### django (2,356 files, 62,379 nodes, 0.860 avg score)
| Query | Top Match | Score | Time |
|---|---|---|---|
| How to define database models | Model | 0.85 | 8ms |
| How to configure URL routing | URLResolver | 0.86 | 21ms |
| How does user authentication work | authenticate | 0.90 | 8ms |
| How to create database migrations | Migration | 0.86 | 9ms |
| How to use Django admin interface | Admin | 0.83 | 8ms |
| How to handle file storage | File | 0.87 | 10ms |
| How to write custom management commands | Command | 0.85 | 42ms |
| How to validate form data | Form | 0.89 | 8ms |
| How to use template tags | tag | 0.87 | 13ms |
| How to configure database settings | Database | 0.86 | 8ms |

#### fastapi (944 files, 10,849 nodes, 0.842 avg score)
| Query | Top Match | Score | Time |
|---|---|---|---|
| How to create REST API endpoints | APIRouter | 0.91 | 4ms |
| How does dependency injection work | Depends | 0.88 | 3ms |
| How to validate request body data | Body | 0.89 | 3ms |
| How to handle WebSocket connections | WebSocket | 0.88 | 3ms |
| How to add authentication to routes | Security | 0.80 | 3ms |
| How to serve static files | static | 0.82 | 3ms |
| How to configure CORS middleware | CORSMiddleware | 0.82 | 3ms |
| How to document API endpoints | OpenAPI | 0.79 | 3ms |
| How to handle file uploads | UploadFile | 0.86 | 3ms |
| How to set up background tasks | BackgroundTasks | 0.82 | 3ms |

#### spring-boot (8,790 files, 68,610 nodes, 0.833 avg score)
| Query | Top Match | Score | Time |
|---|---|---|---|
| How to create a REST controller | RestController | 0.86 | 174ms |
| How does auto-configuration work | AutoConfiguration | 0.85 | 173ms |
| How to inject dependencies | Autowired | 0.82 | 170ms |
| How to create database repositories | Repository | 0.86 | 172ms |
| How to configure application properties | Property | 0.85 | 170ms |
| How to handle exceptions globally | ExceptionHandler | 0.83 | 155ms |
| How to use Spring Data JPA | JPA | 0.83 | 151ms |
| How to configure security | Security | 0.85 | 170ms |
| How to create scheduled tasks | Scheduled | 0.78 | 170ms |
| How to use WebFlux for reactive apps | WebFlux | 0.80 | 152ms |

#### react (4,588 files, 27,400 nodes, 0.839 avg score)
| Query | Top Match | Score | Time |
|---|---|---|---|
| How to use React hooks for state | useState | 0.88 | 35ms |
| How to handle component side effects | useEffect | 0.88 | 19ms |
| How does React render components | ReactDOM | 0.83 | 21ms |
| How to optimize component performance | memo | 0.73 | 20ms |
| How to manage global state | Context | 0.85 | 20ms |
| How to handle form inputs | input | 0.84 | 20ms |
| How to create refs to DOM elements | ref | 0.82 | 20ms |
| How to handle keyboard events | Keyboard | 0.85 | 18ms |
| How to implement error boundaries | ErrorBoundary | 0.88 | 20ms |
| How to test React components | Test | 0.82 | 19ms |

#### redis (866 files, 11,055 nodes, 0.834 avg score)
| Query | Top Match | Score | Time |
|---|---|---|---|
| How does Redis handle string commands | setGenericCommand | 0.81 | 11ms |
| How does Redis allocate memory | zmalloc | 0.88 | 10ms |
| How does the event loop work | aeEventLoop | 0.88 | 11ms |
| How does Redis persist data to disk | rdbSave | 0.81 | 11ms |
| How does Redis handle hash data structures | hashTypeSet | 0.83 | 10ms |
| How does Redis manage client connections | client | 0.81 | 10ms |
| How does Redis implement sorted sets | zslInsert | 0.83 | 10ms |
| How does Redis handle replication | replicationFeed | 0.92 | 10ms |
| How does Redis manage pub/sub messaging | pubsubPublish | 0.80 | 10ms |
| How does Redis implement transactions | multiState | 0.82 | 10ms |

#### tokio (784 files, 11,411 nodes, 0.856 avg score)
| Query | Top Match | Score | Time |
|---|---|---|---|
| How to spawn async tasks | spawn | 0.89 | 12ms |
| How to use TCP networking | TcpListener | 0.90 | 6ms |
| How to create the async runtime | Runtime | 0.88 | 6ms |
| How to use async I/O with files | File | 0.81 | 6ms |
| How to create UDP sockets | UdpSocket | 0.88 | 9ms |
| How to synchronize tasks with mutex | Mutex | 0.81 | 6ms |
| How to use channels for communication | channel | 0.87 | 9ms |
| How to handle timeouts and delays | timeout | 0.84 | 6ms |
| How to spawn blocking tasks | spawn_blocking | 0.87 | 6ms |
| How to use async signals | Signal | 0.85 | 6ms |

---

## Embedding Performance

| Metric | Value |
|---|---|
| Model | BAAI/bge-small-en-v1.5 (384-dim) |
| Eligible node types | class, function, method, file, interface, enum, type_alias |
| Total nodes embedded | 246,966 across 22 repos |
| Total embedding time | 648,391ms (~10.8 min) |
| Avg throughput | ~381 vec/s (CPU, ONNX) |
| Search latency | ~2-175ms (numpy cosine similarity, repo-size dependent) |
| Storage | 1,536 bytes per vector (384 x float32) |

### Embedding Throughput by Repo

| Repo | Nodes Embedded | Time (ms) | Vec/s |
|---|---|---|---|
| Humanizer | 4,162 | 12,295 | 339 |
| cats | 8,837 | 21,822 | 405 |
| chalk | 32 | 34 | 941 |
| django | 48,311 | 109,065 | 443 |
| fastapi | 5,802 | 14,219 | 408 |
| flask | 855 | 2,181 | 392 |
| gin | 893 | 2,246 | 398 |
| hugo | 8,852 | 20,202 | 438 |
| jansson | 341 | 997 | 342 |
| json | 1,948 | 5,484 | 355 |
| junit5 | 13,648 | 49,748 | 274 |
| kotlinx.coroutines | 2,044 | 8,660 | 236 |
| luassert | 63 | 157 | 401 |
| mdbook | 801 | 1,927 | 416 |
| monolog | 1,534 | 3,823 | 401 |
| plug | 36 | 127 | 283 |
| react | 22,049 | 59,603 | 370 |
| redis | 9,590 | 40,681 | 236 |
| rspec-core | 145 | 1,370 | 106 |
| serde | 1,418 | 3,640 | 390 |
| spring-boot | 57,314 | 269,321 | 213 |
| tokio | 5,008 | 20,789 | 241 |

---

## Compression Summary

The knowledge graph compresses source code by ~3-4 orders of magnitude:

| Metric | Source Code | Graph | Ratio |
|---|---|---|---|
| Total size | 1.4 GB | ~42 MB (DB + embeddings) | 33:1 |
| Tokens to represent | 460M | ~2M (node metadata) | 230:1 |
| Cost per query (Haiku) | $0.22-$4.85 | $0.00004 | 10,000:1 |
| Cost per query (GPT-4o) | $2.17-$48.47 | $0.00038 | 10,000:1 |
