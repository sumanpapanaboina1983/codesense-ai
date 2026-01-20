"""
Filesystem MCP Server - REST API for source code file access.
Provides endpoints for reading, searching, and navigating source files.
"""

import os
import re
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# Configuration from environment
CODEBASE_ROOT = os.getenv("CODEBASE_ROOT", "/codebase")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "3001"))


app = FastAPI(
    title="Filesystem MCP Server",
    description="MCP server for filesystem access and source code reading",
    version="1.0.0",
)


# Request/Response models
class ReadRequest(BaseModel):
    path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class ReadResponse(BaseModel):
    content: str
    total_lines: int
    truncated: bool


class ListRequest(BaseModel):
    path: str


class FileEntry(BaseModel):
    path: str
    name: str
    type: str
    size_bytes: int
    modified_time: Optional[str] = None


class ListResponse(BaseModel):
    entries: list[FileEntry]


class FindRequest(BaseModel):
    pattern: str
    root: str
    max_results: int = 100


class FindResponse(BaseModel):
    files: list[str]


class ExistsRequest(BaseModel):
    path: str


class ExistsResponse(BaseModel):
    exists: bool


class MetadataRequest(BaseModel):
    path: str


class MetadataResponse(BaseModel):
    path: str
    size_bytes: int
    language: str
    loc: int
    encoding: str


class SearchRequest(BaseModel):
    path: str
    pattern: str
    case_sensitive: bool = True


class SearchMatch(BaseModel):
    line_number: int
    content: str
    match: str


class SearchResponse(BaseModel):
    matches: list[SearchMatch]


class SearchDirectoryRequest(BaseModel):
    pattern: str
    root: str
    file_pattern: str = "*"
    max_results: int = 100


class DirectorySearchMatch(BaseModel):
    file: str
    line_number: int
    content: str


class SearchDirectoryResponse(BaseModel):
    matches: list[DirectorySearchMatch]


class HealthResponse(BaseModel):
    status: str
    codebase_accessible: bool


# Language detection by extension
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".md": "markdown",
    ".sh": "shell",
    ".bash": "shell",
}


def get_language(path: str) -> str:
    """Detect language from file extension."""
    ext = Path(path).suffix.lower()
    return LANGUAGE_MAP.get(ext, "unknown")


def validate_path(path: str) -> Path:
    """Validate and resolve path within codebase root."""
    resolved = Path(path).resolve()
    codebase = Path(CODEBASE_ROOT).resolve()

    # Ensure path is within codebase root (prevent directory traversal)
    try:
        resolved.relative_to(codebase)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: path must be within {CODEBASE_ROOT}",
        )

    return resolved


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server health and codebase accessibility."""
    codebase_path = Path(CODEBASE_ROOT)
    accessible = codebase_path.exists() and codebase_path.is_dir()
    return HealthResponse(
        status="healthy" if accessible else "degraded",
        codebase_accessible=accessible,
    )


@app.post("/read", response_model=ReadResponse)
async def read_file(request: ReadRequest):
    """Read file content, optionally with line range."""
    path = validate_path(request.path)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")

    # Check file size
    if path.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_FILE_SIZE_MB}MB)",
        )

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = path.read_text(encoding="latin-1")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cannot read file: {str(e)}")

    lines = content.split("\n")
    total_lines = len(lines)
    truncated = False

    # Apply line range if specified
    if request.start_line is not None or request.end_line is not None:
        start = (request.start_line or 1) - 1  # Convert to 0-based
        end = request.end_line or total_lines
        lines = lines[start:end]
        content = "\n".join(lines)

    return ReadResponse(
        content=content,
        total_lines=total_lines,
        truncated=truncated,
    )


@app.post("/list", response_model=ListResponse)
async def list_directory(request: ListRequest):
    """List directory contents."""
    path = validate_path(request.path)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.path}")

    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {request.path}")

    entries = []
    for item in sorted(path.iterdir()):
        # Skip hidden files and common ignore patterns
        if item.name.startswith(".") or item.name in ["__pycache__", "node_modules", ".git"]:
            continue

        stat = item.stat()
        entries.append(
            FileEntry(
                path=str(item),
                name=item.name,
                type="directory" if item.is_dir() else "file",
                size_bytes=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            )
        )

    return ListResponse(entries=entries)


@app.post("/find", response_model=FindResponse)
async def find_files(request: FindRequest):
    """Find files matching a glob pattern."""
    root = validate_path(request.root)

    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.root}")

    files = []
    for path in root.rglob("*"):
        if path.is_file() and fnmatch(path.name, request.pattern.split("/")[-1]):
            # Check full pattern match
            relative = str(path.relative_to(root))
            if fnmatch(relative, request.pattern) or fnmatch(path.name, request.pattern):
                files.append(str(path))
                if len(files) >= request.max_results:
                    break

    return FindResponse(files=files)


@app.post("/exists", response_model=ExistsResponse)
async def check_exists(request: ExistsRequest):
    """Check if a file or directory exists."""
    try:
        path = validate_path(request.path)
        return ExistsResponse(exists=path.exists())
    except HTTPException:
        return ExistsResponse(exists=False)


@app.post("/metadata", response_model=MetadataResponse)
async def get_metadata(request: MetadataRequest):
    """Get file metadata."""
    path = validate_path(request.path)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {request.path}")

    stat = path.stat()

    # Count lines of code
    try:
        content = path.read_text(encoding="utf-8")
        loc = len([line for line in content.split("\n") if line.strip()])
    except Exception:
        loc = 0

    return MetadataResponse(
        path=str(path),
        size_bytes=stat.st_size,
        language=get_language(str(path)),
        loc=loc,
        encoding="utf-8",
    )


@app.post("/search", response_model=SearchResponse)
async def search_in_file(request: SearchRequest):
    """Search for pattern in a file."""
    path = validate_path(request.path)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {str(e)}")

    flags = 0 if request.case_sensitive else re.IGNORECASE
    matches = []

    try:
        pattern = re.compile(request.pattern, flags)
        for i, line in enumerate(content.split("\n"), 1):
            match = pattern.search(line)
            if match:
                matches.append(
                    SearchMatch(
                        line_number=i,
                        content=line.strip(),
                        match=match.group(),
                    )
                )
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")

    return SearchResponse(matches=matches)


@app.post("/search_directory", response_model=SearchDirectoryResponse)
async def search_in_directory(request: SearchDirectoryRequest):
    """Search for pattern across files in directory."""
    root = validate_path(request.root)

    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {request.root}")

    matches = []

    try:
        pattern = re.compile(request.pattern, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")

    for path in root.rglob("*"):
        if len(matches) >= request.max_results:
            break

        if not path.is_file():
            continue

        # Skip binary and large files
        if path.stat().st_size > MAX_FILE_SIZE:
            continue

        # Match file pattern
        if not fnmatch(path.name, request.file_pattern):
            continue

        try:
            content = path.read_text(encoding="utf-8")
            for i, line in enumerate(content.split("\n"), 1):
                if pattern.search(line):
                    matches.append(
                        DirectorySearchMatch(
                            file=str(path),
                            line_number=i,
                            content=line.strip()[:200],  # Truncate long lines
                        )
                    )
                    if len(matches) >= request.max_results:
                        break
        except (UnicodeDecodeError, PermissionError):
            continue

    return SearchDirectoryResponse(matches=matches)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Filesystem MCP Server",
        "version": "1.0.0",
        "status": "running",
        "codebase_root": CODEBASE_ROOT,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
