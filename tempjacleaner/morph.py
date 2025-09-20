"""形態素解析(オプション)サポート。

優先度:
- fugashi(MeCab) + unidic系 があればそれを利用
- なければ Janome にフォールバック
"""
from __future__ import annotations
from typing import List, Tuple

_tokenizer = None
_backend = None  # "fugashi" | "janome" | None

def is_available() -> bool:
    global _tokenizer, _backend
    if _tokenizer is not None:
        return True
    # Try fugashi first
    try:
        from fugashi import Tagger  # type: ignore
        _tokenizer = Tagger()
        _backend = "fugashi"
        return True
    except Exception:
        pass
    # Fallback to janome
    try:
        from janome.tokenizer import Tokenizer  # type: ignore
        _tokenizer = Tokenizer()
        _backend = "janome"
        return True
    except Exception:
        return False

def tokenize_with_spans(text: str) -> List[Tuple[int, int, str, str | None]]:
    """形態素ごとの (start, end, surface, 品詞) を返す。
    形態素器が無い場合はテキスト全体を一塊として返す。
    """
    if not is_available():
        return [(0, len(text), text, None)]
    global _tokenizer, _backend
    spans: List[Tuple[int, int, str, str | None]] = []
    idx = 0
    if _backend == "fugashi":
        for w in _tokenizer(text):
            surf = w.surface
            pos = text.find(surf, idx)
            if pos < 0:
                pos = idx
            end = pos + len(surf)
            pos_tag = w.feature.pos if hasattr(w, 'feature') and hasattr(w.feature, 'pos') else None
            spans.append((pos, end, surf, pos_tag))
            idx = end
    elif _backend == "janome":
        for tok in _tokenizer.tokenize(text):
            surf = tok.surface
            pos = text.find(surf, idx)
            if pos < 0:
                pos = idx
            end = pos + len(surf)
            pos_tag = tok.part_of_speech.split(',')[0] if hasattr(tok, 'part_of_speech') else None
            spans.append((pos, end, surf, pos_tag))
            idx = end
    else:
        return [(0, len(text), text, None)]
    return spans

__all__ = ["is_available", "tokenize_with_spans"]
