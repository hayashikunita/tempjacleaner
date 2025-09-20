from __future__ import annotations
"""
日本語単語の誤字検出（簡易スペルチェック）
- rapidfuzz による類似度を用いて、辞書語彙に最も近い候補を提示
- janome があれば形態素トークンで、無ければ簡易な単語抽出で処理
- オプション機能: 依存が未導入なら静かにスキップ

辞書形式:
- プレーンテキスト: 1行1語（UTF-8）。コメント行は先頭#で無視。
- JSON: {"words": ["正しい", "語彙", ...]}
"""
from typing import Iterator, Dict, Any, Iterable, List, Optional
import json
import re
from pathlib import Path

try:
    from rapidfuzz import process, fuzz  # type: ignore
    _RF_AVAILABLE = True
except Exception:
    process = None  # type: ignore
    fuzz = None  # type: ignore
    _RF_AVAILABLE = False

try:
    from .morph import tokenize_with_spans, is_available as morph_available
except Exception:
    def tokenize_with_spans(text: str):
        return [(0, len(text), text)]
    def morph_available():
        return False


def is_available() -> bool:
    return _RF_AVAILABLE


def load_dict(paths: Iterable[str | Path]) -> List[str]:
    words: List[str] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        if path.suffix.lower() == '.json':
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                ws = data.get('words', []) if isinstance(data, dict) else []
                words.extend([str(w) for w in ws])
            except Exception:
                continue
        else:
            # プレーンテキスト
            for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                words.append(line)
    # 重複除去
    return sorted(set(words))


_WORD_RE = re.compile(r"[\u3040-\u30FF\u3400-\u9FFF\uF900-\uFAFFー]+")

def _simple_tokens(text: str) -> List[tuple[int,int,str]]:
    return [(m.start(), m.end(), m.group(0)) for m in _WORD_RE.finditer(text)]


def run_spellcheck(text: str, dict_words: List[str], threshold: int = 90) -> Iterator[Dict[str, Any]]:
    if not _RF_AVAILABLE or not dict_words:
        return iter(())
    # トークン化
    spans: List[tuple[int,int,str]] = []
    if morph_available():
        spans = [(s, e, surf) for s, e, surf in tokenize_with_spans(text)]
    else:
        spans = _simple_tokens(text)
    # 類似検索
    for s, e, token in spans:
        if len(token) <= 1:
            continue
        # 完全一致はスキップ
        if token in dict_words:
            continue
        try:
            cand = process.extractOne(token, dict_words, scorer=fuzz.WRatio)
        except Exception:
            cand = None
        if not cand:
            continue
        best, score, _ = cand
        if score >= threshold:
            yield {
                "start": s,
                "end": e,
                "match": token,
                "message": "単語の誤記の可能性",
                "suggestion": best,
                "severity": "INFO",
                "rule_id": "SPELL_FUZZY",
            }

__all__ = ["is_available", "load_dict", "run_spellcheck"]
