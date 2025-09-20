"""シンプルなコメント抽出ユーティリティ。

対応(簡易):
- Python/Shell風: 行頭/非リテラル判定なしに '#' 以降をコメントとみなす
- C/JS風: // 行コメント, /* ... */ ブロックコメント

注意: これはヒューリスティックです。文字列中の '//' や '#' を誤認する可能性があります。
"""
from __future__ import annotations
import re
from typing import Iterator, Tuple

_LINE_HASH = re.compile(r"#[^\n]*")
_LINE_SLASH = re.compile(r"//[^\n]*")
_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)

def extract_comments(text: str) -> Iterator[Tuple[int, int, str]]:
    for m in _LINE_HASH.finditer(text):
        yield m.start(), m.end(), m.group(0)
    for m in _LINE_SLASH.finditer(text):
        yield m.start(), m.end(), m.group(0)
    for m in _BLOCK.finditer(text):
        yield m.start(), m.end(), m.group(0)

__all__ = ["extract_comments"]
