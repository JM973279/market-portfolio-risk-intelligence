"""Content-addressed, append-only private evidence storage (not a public artifact)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = ROOT / 'data/operations/us-validation'


class IntegrityError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(',', ':')) + '\n').encode()


class EvidenceStore:
    """No mutable 'latest' pointer. Permissions deter accidents; SHA detects edits.

    This is not protection against a filesystem administrator. Public directories,
    frozen assets and arbitrary output paths are deliberately unsupported.
    """
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root).resolve()
        private = (ROOT / 'data/operations').resolve()
        temporary = Path('/tmp').resolve()
        if not (self.root.is_relative_to(private) or self.root.is_relative_to(temporary)):
            raise ValueError('Evidence must remain in data/operations or /tmp')
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, category: str, key: str) -> Path:
        if category not in {'blobs', 'snapshots', 'analyses', 'candidates'} or not re.fullmatch('[0-9a-f]{64}', key):
            raise IntegrityError('Invalid evidence identifier')
        path = self.root / category / key
        if not path.resolve().is_relative_to(self.root):
            raise IntegrityError('Evidence path escaped store')
        return path

    def put(self, data: bytes, category: str = 'blobs') -> str:
        key = sha256(data)
        path = self._path(category, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('xb') as stream:
                stream.write(data)
            path.chmod(0o444)
        except FileExistsError:
            if path.read_bytes() != data:
                raise IntegrityError('Existing immutable evidence was modified') from None
        return key

    def read(self, key: str, category: str = 'blobs') -> bytes:
        data = self._path(category, key).read_bytes()
        if sha256(data) != key:
            raise IntegrityError('Evidence hash mismatch')
        return data

    def document(self, data: dict, category: str) -> str:
        return self.put(canonical(data), category)

    def load(self, key: str, category: str) -> dict:
        return json.loads(self.read(key, category))
