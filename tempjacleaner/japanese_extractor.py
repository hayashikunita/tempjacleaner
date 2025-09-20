"""ファイル/テキストから日本語領域を抽出するユーティリティ。

現状: 
- Unicodeのひらがな/カタカナ/漢字範囲を包含する正規表現で抽出。
- コードファイルでの文字列リテラル抽出は簡易(ダブル/シングルクォート、Python/JS風)。

制限:
- エスケープシーケンス・raw文字列等の完全対応ではない。
- コメント内日本語も拾いたい場合は拡張が必要。
"""
from __future__ import annotations
import re
from typing import Iterable, Iterator, Tuple

# 日本語らしい文字(漢字,ひらがな,カタカナ,全角記号の一部)を含むテキスト塊を検出
_JP_BLOCK_RE = re.compile(r"[\u3040-\u30FF\u3400-\u9FFF\uF900-\uFAFF\u3000-\u303F]+(?:[A-Za-z0-9\u3040-\u30FF\u3400-\u9FFF\uF900-\uFAFF\u3000-\u303F]+)*")

# 簡易文字列リテラル抽出 ("..." or '...') - ネスト/エスケープは最小限
_STRING_RE = re.compile(r'(["\'])(?:(?=\\)\\.|(?!\1).)*?\1')

def extract_string_literals(code: str) -> Iterator[Tuple[int, int, str]]:
    for m in _STRING_RE.finditer(code):
        yield m.start(), m.end(), m.group(0)

def extract_japanese_blocks(text: str) -> Iterator[Tuple[int, int, str]]:
    for m in _JP_BLOCK_RE.finditer(text):
        yield m.start(), m.end(), m.group(0)

def extract_japanese_from_code(code: str) -> Iterator[Tuple[int, int, str]]:
    # まず文字列リテラル候補を抽出し、その内部から日本語ブロックを再抽出
    for s_start, s_end, literal in extract_string_literals(code):
        # 両端のクォートを除去して中身のみ再検索 (大雑把)
        inner = literal[1:-1]
        for j_start, j_end, block in extract_japanese_blocks(inner):
            abs_start = s_start + 1 + j_start
            abs_end = s_start + 1 + j_end
            yield abs_start, abs_end, block

__all__ = [
    "extract_string_literals",
    "extract_japanese_blocks",
    "extract_japanese_from_code",
]
