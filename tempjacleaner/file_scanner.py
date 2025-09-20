"""任意拡張子ファイルの走査ユーティリティ。

- 拡張子フィルタは行わず、バイナリらしいものは除外(ヒューリスティック)。
- 将来的に .gitignore, 除外パターン対応を検討。
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Iterator, Iterable

BINARY_BYTES = set(range(0, 9)) | {11, 12} | set(range(14, 32))

def is_probably_text(data: bytes, threshold: float = 0.30) -> bool:
    if not data:
        return True
    non_text = sum(b in BINARY_BYTES for b in data)
    ratio = non_text / len(data)
    return ratio < threshold

def read_text(path: Path, encoding_candidates=("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp932", "shift_jis")) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not is_probably_text(raw):
        return None
    for enc in encoding_candidates:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None

def iter_files(paths: Iterable[str | os.PathLike[str]]) -> Iterator[Path]:
    for p in paths:
        path = Path(p)
        if path.is_file():
            yield path
        elif path.is_dir():
            for root, _dirs, files in os.walk(path):
                for f in files:
                    yield Path(root) / f

__all__ = ["iter_files", "read_text", "is_probably_text"]
