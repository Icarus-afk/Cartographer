from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    KOTLIN = "kotlin"
    CSHARP = "csharp"
    PHP = "php"
    RUBY = "ruby"
    C = "c"
    CPP = "cpp"
    SWIFT = "swift"
    SCALA = "scala"
    ELIXIR = "elixir"
    LUA = "lua"
    JULIA = "julia"
    ZIG = "zig"
    GROOVY = "groovy"
    UNKNOWN = "unknown"


LANGUAGE_EXTENSIONS: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TSX,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".java": Language.JAVA,
    ".kt": Language.KOTLIN,
    ".kts": Language.KOTLIN,
    ".cs": Language.CSHARP,
    ".php": Language.PHP,
    ".phtml": Language.PHP,
    ".rb": Language.RUBY,
    ".c": Language.C,
    ".h": Language.C,
    ".cpp": Language.CPP,
    ".hpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".swift": Language.SWIFT,
    ".scala": Language.SCALA,
    ".sc": Language.SCALA,
    ".ex": Language.ELIXIR,
    ".exs": Language.ELIXIR,
    ".lua": Language.LUA,
    ".jl": Language.JULIA,
    ".zig": Language.ZIG,
    ".groovy": Language.GROOVY,
    ".gvy": Language.GROOVY,
    ".gsh": Language.GROOVY,
}


@dataclass
class FrameworkFingerprint:
    name: str
    confidence: float
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RepositoryManifest:
    languages: dict[Language, int]
    frameworks: list[FrameworkFingerprint]
    package_managers: list[str]
    build_systems: list[str]
    is_monorepo: bool
    monorepo_tool: str | None = None
    total_files: int = 0
    total_dirs: int = 0
    indexed_at: datetime | None = None
    total_references: int = 0


@dataclass
class CodeLocation:
    file_path: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


class EntityKind(str, Enum):
    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"
    MODULE = "module"
    PACKAGE = "package"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    ENUM = "enum"
    CONSTANT = "constant"
    VARIABLE = "variable"
    API_ENDPOINT = "api_endpoint"
    CONTROLLER = "controller"
    SERVICE = "service"
    REPOSITORY_LAYER = "repository_layer"
    MIDDLEWARE = "middleware"
    JOB = "job"
    WORKER = "worker"
    QUEUE = "queue"
    DATABASE = "database"
    TABLE = "table"
    INDEX = "index"
    CACHE = "cache"
    BUCKET = "bucket"
    TOPIC = "topic"
    CONTAINER = "container"
    DEPLOYMENT = "deployment"
    MARKDOWN = "markdown"
    ADR = "adr"
    DIAGRAM = "diagram"
    WIKI = "wiki"
    COMMENT_BLOCK = "comment_block"
    COMMIT = "commit"
    AUTHOR = "author"
    BRANCH = "branch"
    TAG = "tag"
    RELEASE = "release"


@dataclass
class ParsedEntity:
    kind: EntityKind
    name: str
    location: CodeLocation
    docstring: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list["ParsedEntity"] = field(default_factory=list)


@dataclass
class ParsedFile:
    path: str
    language: Language
    entities: list[ParsedEntity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class IngestionResult:
    path: str
    manifest: RepositoryManifest | None
    success: bool
    parsed_files: list[ParsedFile] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
