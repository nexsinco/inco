"""Filesystem awareness tools for INC0G."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

PROTECTED_FILES = {"credentials.txt"}


class FileSystemAwareness:
    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()

    def _resolve(self, relative: str | Path) -> Path:
        path = (self.root / relative).resolve()
        if self.root not in path.parents and path != self.root:
            raise PermissionError("Refusing to access paths outside the project root")
        return path

    def scan(self, patterns: Iterable[str] = ("*.py", "*.txt", "*.json")) -> list[str]:
        files: list[str] = []
        for pattern in patterns:
            files.extend(str(path.relative_to(self.root)) for path in self.root.rglob(pattern) if path.is_file())
        return sorted(set(files))

    def read(self, relative: str | Path, *, allow_credentials: bool = False) -> str:
        path = self._resolve(relative)
        if path.name in PROTECTED_FILES and not allow_credentials:
            return "[protected file: credentials are never revealed]"
        return path.read_text(encoding="utf-8")

    def write(self, relative: str | Path, content: str) -> None:
        path = self._resolve(relative)
        if path.name in PROTECTED_FILES:
            raise PermissionError("Refusing to overwrite credentials.txt through the generic file writer")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def search(self, needle: str) -> dict[str, list[int]]:
        hits: dict[str, list[int]] = {}
        for rel in self.scan():
            if Path(rel).name in PROTECTED_FILES:
                continue
            try:
                lines = self.read(rel).splitlines()
            except UnicodeDecodeError:
                continue
            matches = [idx for idx, line in enumerate(lines, 1) if needle.lower() in line.lower()]
            if matches:
                hits[rel] = matches
        return hits
