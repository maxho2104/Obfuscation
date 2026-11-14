"""Чтение файла, определение кодировки и вычисление хеша."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Sequence

from internal_correspondence.text_import.errors import ReaderError
from internal_correspondence.text_import.models import FileInfo

try:  # charset-normalizer входит в requirements приложения
    from charset_normalizer import from_bytes as _detect_from_bytes
except ImportError:  # pragma: no cover - запасной путь для урезанных сборок
    _detect_from_bytes = None


_ENCODING_ALIASES = {
    "utf8": "utf-8",
    "utf-8": "utf-8",
    "utf8-sig": "utf-8-sig",
    "utf-8-sig": "utf-8-sig",
    "cp1251": "cp1251",
    "windows-1251": "cp1251",
    "win-1251": "cp1251",
    "cp866": "cp866",
    "koi8-r": "koi8-r",
    "utf-16": "utf-16",
    "utf-16-le": "utf-16-le",
    "utf-16-be": "utf-16-be",
}


def normalize_encoding(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    key = name.strip().lower()
    return _ENCODING_ALIASES.get(key, key)


def detect_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    # UTF-8 — самый частый формат; проверяем строго, чтобы charset-normalizer
    # не принял корректный UTF-8 за однобайтовую кодировку на коротком тексте.
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    if _detect_from_bytes is not None:
        match = _detect_from_bytes(raw).best()
        if match is not None and match.encoding:
            return normalize_encoding(match.encoding) or match.encoding
    return "cp1251"


def read_file(
    path: Path,
    allowed_extensions: Sequence[str],
    encoding: Optional[str] = None,
    max_line_length: int = 1_000_000,
) -> FileInfo:
    """Читает текстовый файл и возвращает строки без символов перевода строки."""
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise ReaderError("file_not_found", f"file not found: {path}", path=str(path))
    suffix = path.suffix.lower()
    if suffix not in {item.lower() for item in allowed_extensions}:
        raise ReaderError(
            "unsupported_extension",
            f"unsupported extension: {suffix}",
            suffix=suffix,
        )
    raw = path.read_bytes()
    if not raw:
        raise ReaderError("file_empty", f"file is empty: {path}", path=str(path))

    selected = normalize_encoding(encoding)
    if selected is None:
        selected = detect_encoding(raw)
    try:
        text = raw.decode(selected)
    except (UnicodeDecodeError, LookupError) as exc:
        if encoding is None:
            for fallback in ("utf-8-sig", "utf-8", "cp1251"):
                try:
                    text = raw.decode(fallback)
                    selected = fallback
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                raise ReaderError(
                    "encoding_failed",
                    f"cannot decode file: {exc}",
                    encoding=selected,
                ) from exc
        else:
            raise ReaderError(
                "encoding_failed",
                f"cannot decode file as {selected}: {exc}",
                encoding=selected,
            ) from exc

    lines = text.splitlines()
    if not lines:
        raise ReaderError("file_empty", f"file has no lines: {path}", path=str(path))
    for number, line in enumerate(lines, start=1):
        if len(line) > max_line_length:
            raise ReaderError(
                "line_too_long",
                f"line {number} exceeds {max_line_length} characters",
                row=number,
            )
    digest = hashlib.sha256(raw).hexdigest()
    return FileInfo(
        path=path,
        encoding=selected,
        text=text,
        lines=lines,
        file_hash=digest,
        size=len(raw),
    )
