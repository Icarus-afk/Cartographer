from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from cartographer.core.models import FrameworkFingerprint

logger = logging.getLogger(__name__)

_FILE_READ_CACHE: dict[str, str | None] = {}


def _read_cached(path: Path) -> str | None:
    key = str(path.resolve())
    if key in _FILE_READ_CACHE:
        return _FILE_READ_CACHE[key]
    try:
        content = path.read_text(errors="replace")
        _FILE_READ_CACHE[key] = content
        return content
    except Exception as e:
        logger.debug("Failed to cache read %s: %s", path, e)
        _FILE_READ_CACHE[key] = None
        return None

FRAMEWORK_RULES: list[dict[str, Any]] = [
    {
        "name": "Django",
        "indicators": [
            {"file": "manage.py", "weight": 0.6},
            {"file": "django-admin", "weight": 0.4},
            {"pattern": r"^django", "target": "requirements.txt", "weight": 0.3},
        ],
    },
    {
        "name": "FastAPI",
        "indicators": [
            {"pattern": r"^fastapi", "target": "requirements.txt", "weight": 0.5},
            {"file": "main.py", "content": r"from\s+fastapi", "weight": 0.6},
        ],
    },
    {
        "name": "Flask",
        "indicators": [
            {"pattern": r"^flask", "target": "requirements.txt", "weight": 0.5},
        ],
    },
    {
        "name": "Spring Boot",
        "indicators": [
            {"file": "pom.xml", "content": r"spring-boot", "weight": 0.7},
            {"file": "build.gradle", "content": r"spring-boot", "weight": 0.7},
            {"file": "application.yml", "weight": 0.3},
            {"file": "application.properties", "weight": 0.3},
        ],
    },
    {
        "name": "Express",
        "indicators": [
            {"file": "package.json", "content": r'"express"', "weight": 0.7},
        ],
    },
    {
        "name": "Next.js",
        "indicators": [
            {"file": "package.json", "content": r'"next"', "weight": 0.7},
            {"file": "next.config.js", "weight": 0.4},
            {"file": "next.config.ts", "weight": 0.4},
        ],
    },
    {
        "name": "NestJS",
        "indicators": [
            {"file": "package.json", "content": r'"@nestjs/core"', "weight": 0.7},
            {"file": "nest-cli.json", "weight": 0.4},
        ],
    },
    {
        "name": "Laravel",
        "indicators": [
            {"file": "artisan", "weight": 0.6},
            {"file": "composer.json", "content": r'"laravel/framework"', "weight": 0.7},
        ],
    },
    {
        "name": "Actix Web",
        "indicators": [
            {"file": "Cargo.toml", "content": r"actix-web", "weight": 0.7},
        ],
    },
    {
        "name": "Axum",
        "indicators": [
            {"file": "Cargo.toml", "content": r"axum", "weight": 0.7},
        ],
    },
    {
        "name": "React",
        "indicators": [
            {"file": "package.json", "content": r'"react"', "weight": 0.5},
        ],
    },
    {
        "name": "Vue",
        "indicators": [
            {"file": "package.json", "content": r'"vue"', "weight": 0.5},
        ],
    },
    {
        "name": "Ruby on Rails",
        "indicators": [
            {"file": "Gemfile", "content": r"rails", "weight": 0.7},
            {"file": "bin/rails", "weight": 0.5},
        ],
    },
]


def _check_indicator(root: Path, indicator: dict[str, Any]) -> bool:
    if "file" in indicator and "content" in indicator:
        target = root / indicator["file"]
        if target.exists():
            content = _read_cached(target)
            if content is not None:
                return bool(re.search(indicator["content"], content))
        return False

    if "file" in indicator:
        return (root / indicator["file"]).exists()

    if "pattern" in indicator and "target" in indicator:
        target = root / indicator["target"]
        if target.exists():
            content = _read_cached(target)
            if content is not None:
                for line in content.splitlines():
                    if re.search(indicator["pattern"], line):
                        return True
        return False

    return False


def fingerprint_frameworks(root: Path) -> list[FrameworkFingerprint]:
    detected: list[FrameworkFingerprint] = []
    for rule in FRAMEWORK_RULES:
        score = 0.0
        for indicator in rule["indicators"]:
            if _check_indicator(root, indicator):
                score += indicator.get("weight", 0.5)
        if score > 0:
            confidence = min(score, 1.0)
            detected.append(FrameworkFingerprint(name=rule["name"], confidence=confidence))
    detected.sort(key=lambda f: f.confidence, reverse=True)
    return detected
