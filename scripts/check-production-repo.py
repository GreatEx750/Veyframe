from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = [
    ROOT / "apps",
    ROOT / "packages",
    ROOT / "services",
    ROOT / "scripts",
    ROOT / "docs",
]
ROOT_FILES = [
    ROOT / "README.md",
    ROOT / "LICENSE",
    ROOT / "package.json",
    ROOT / "requirements-dev.txt",
    ROOT / "pyproject.toml",
    ROOT / ".env.example",
]
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
IGNORED_PARTS = {
    ".next",
    "__pycache__",
    "node_modules",
}


def production_files() -> list[Path]:
    files = [path for path in ROOT_FILES if path.is_file()]
    for directory in PRODUCTION_ROOTS:
        if not directory.exists():
            continue
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and path.suffix.lower() in TEXT_SUFFIXES
            and not (set(path.parts) & IGNORED_PARTS)
            and path.name != Path(__file__).name
        )
    return sorted(set(files))


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def main() -> int:
    failures: list[str] = []
    files = production_files()
    content = {path: path.read_text(encoding="utf-8", errors="ignore") for path in files}

    blocked_branding = [
        "generated" + "-by",
        "coding" + " assistant",
        "development" + " assistant",
    ]
    for path, text in content.items():
        lowered = text.lower()
        for phrase in blocked_branding:
            if phrase in lowered:
                fail(f"{path.relative_to(ROOT)} contains prohibited branding: {phrase}", failures)

    prohibited_ai = ["anth" + "ropic", "lang" + "chain", "llama" + "index", "crew" + "ai"]
    manifest_paths = [
        ROOT / "package.json",
        ROOT / "package-lock.json",
        ROOT / "requirements-dev.txt",
        ROOT / "services" / "api" / "pyproject.toml",
        ROOT / "services" / "worker" / "pyproject.toml",
    ]
    for path in manifest_paths:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for dependency in prohibited_ai:
            if dependency in text:
                fail(f"{path.relative_to(ROOT)} contains prohibited AI dependency {dependency}", failures)

    secret_patterns = [
        re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
        re.compile(r"sk-[0-9A-Za-z_-]{20,}"),
        re.compile(r"(?im)^(?:GEMINI|PARALLEL)_API_KEY[ \t]*=[ \t]*[^\s#]{12,}$"),
    ]
    for path, text in content.items():
        for pattern in secret_patterns:
            if pattern.search(text):
                fail(f"{path.relative_to(ROOT)} appears to contain a credential", failures)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ["## Local setup", "## Development", "## Runtime architecture", "## Hosted demo"]:
        if heading not in readme:
            fail(f"README is missing {heading}", failures)
    if not (ROOT / "LICENSE").is_file():
        fail("LICENSE is missing", failures)
    all_content = "\n".join(content.values())
    if not re.search(r"from\s+parallel\s+import|import\s+parallel", all_content):
        fail("Parallel runtime integration was not found", failures)
    if not re.search(r"from\s+google(?:\.genai)?\s+import\s+(?:genai|types)", all_content):
        fail("Google Gen AI runtime integration was not found", failures)
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    if ".env" not in gitignore:
        fail(".env is not ignored", failures)

    if failures:
        print("Production readiness check FAILED")
        for item in failures:
            print(f"- {item}")
        return 1
    print(f"Production readiness check PASSED ({len(files)} files reviewed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
