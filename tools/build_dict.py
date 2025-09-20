from __future__ import annotations
"""
日本語辞書のブートストラップ用スクリプト。
- リポジトリ内のテキストを走査し、日本語トークンを収集して頻度辞書を生成。
- 生成物は 1行1語 のプレーンテキスト(dict.txt)として出力。

使い方(例):
  python tools/build_dict.py . --out dict.txt --min-freq 3 --include-comments --morph

注意:
- janome が無い場合は簡易トークン分割になります。
- バイナリ/非対応エンコーディングは自動でスキップされます。
"""
import argparse
from collections import Counter
import re
from pathlib import Path
from typing import Iterable

# 自パッケージのユーティリティを利用
from tempjacleaner.file_scanner import iter_files, read_text
from tempjacleaner.japanese_extractor import extract_japanese_blocks

try:
    from tempjacleaner.morph import tokenize_with_spans, is_available as morph_available
except Exception:
    def tokenize_with_spans(text: str):
        return [(0, len(text), text)]
    def morph_available():
        return False

_WORD_RE = re.compile(r"[\u3040-\u30FF\u3400-\u9FFF\uF900-\uFAFFー]+")

def simple_tokens(text: str):
    for m in _WORD_RE.finditer(text):
        yield m.group(0)

def gather_tokens(paths: Iterable[str], include_comments: bool = True, morph: bool = False):
    cnt = Counter()
    for p in iter_files(paths):
        s = read_text(Path(p))
        if not s:
            continue
        # 日本語ブロックを取り出し
        for _s, _e, block in extract_japanese_blocks(s):
            if morph and morph_available():
                for _bs, _be, surf in tokenize_with_spans(block):
                    if len(surf) > 1:
                        cnt[surf] += 1
            else:
                for tok in simple_tokens(block):
                    if len(tok) > 1:
                        cnt[tok] += 1
    return cnt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+', help='走査するファイル/ディレクトリ')
    ap.add_argument('--out', default='dict.txt', help='出力ファイル(既定: dict.txt)')
    ap.add_argument('--min-freq', type=int, default=2, help='採用する最小出現回数(既定:2)')
    ap.add_argument('--morph', action='store_true', help='janomeがある場合、形態素トークンで分割')
    args = ap.parse_args()

    cnt = gather_tokens(args.paths, include_comments=True, morph=args.morph)
    words = [w for w, c in cnt.items() if c >= args.min_freq]
    words.sort()
    Path(args.out).write_text("\n".join(words), encoding='utf-8')
    print(f"Wrote {len(words)} words to {args.out}")

if __name__ == '__main__':
    main()
