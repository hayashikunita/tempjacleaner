from __future__ import annotations
"""
spaCy + GiNZA による日本語構文解析ベースのチェック
- 依存が重いので optional。
- 未導入/ロード失敗時は安全にスキップ。

提供関数:
- is_available() -> bool
- run_nlp(text: str, model: str = 'ja_ginza') -> Iterator[Dict[str, Any]]
  Issue互換辞書: start, end, match, message, suggestion?, severity, rule_id
"""
from typing import Iterator, Dict, Any, Optional

try:  # optional heavy deps
    import spacy  # type: ignore
    _SPACY_AVAILABLE = True
except Exception:
    spacy = None  # type: ignore
    _SPACY_AVAILABLE = False

_nlp_cache: dict[str, Any] = {}


def is_available() -> bool:
    return _SPACY_AVAILABLE


def _get_nlp(model: str):
    if not _SPACY_AVAILABLE:
        return None
    nlp = _nlp_cache.get(model)
    if nlp is None:
        try:
            nlp = spacy.load(model)
        except Exception:
            return None
        _nlp_cache[model] = nlp
    return nlp


def run_nlp(text: str, model: str = 'ja_ginza') -> Iterator[Dict[str, Any]]:
    nlp = _get_nlp(model)
    if nlp is None:
        return iter(())
    try:
        doc = nlp(text)
    except Exception:
        return iter(())

    # ルール1: 「の」の連鎖(3つ以上) -> 冗長
    # 例: AのBのCのD
    s = text
    import re
    for m in re.finditer(r"の{1}(?:[^の]{0,10}の){2,}", s):
        yield {
            "start": m.start(),
            "end": m.end(),
            "match": s[m.start():m.end()],
            "message": "助詞『の』の連鎖（冗長の可能性）",
            "suggestion": None,
            "severity": "INFO",
            "rule_id": "NLP_NO_CHAIN",
        }

    # ルール2: 助詞の不自然な連続（を/に/が などが2つ以上近接）
    # 簡易: 形態素レベルで助詞(POS=ADP)の連続を検出
    for sent in doc.sents:
        prev_is_adp = False
        start_idx: Optional[int] = None
        for token in sent:
            is_adp = token.pos_ == 'ADP'
            if is_adp and prev_is_adp:
                if start_idx is None:
                    start_idx = token.idx
                end_idx = token.idx + len(token.text)
                yield {
                    "start": start_idx,
                    "end": end_idx,
                    "match": text[start_idx:end_idx],
                    "message": "助詞が連続しています（不自然の可能性）",
                    "suggestion": None,
                    "severity": "INFO",
                    "rule_id": "NLP_PARTICLE_RUN",
                }
            prev_is_adp = is_adp
            if not is_adp:
                start_idx = None

    # ルール3: 主述の距離が極端に長い（読みにくさの目安）
    # ヘッド(動詞/形容詞)とその主語(nsubj類)が50文字以上離れていたら通知（ヒューリスティック）
    for sent in doc.sents:
        for token in sent:
            if token.pos_ in ("VERB", "AUX", "ADJ"):
                head = token
                # 子や祖先から主語的ラベルを探索
                subj: Optional[Any] = None
                for child in head.children:
                    if child.dep_ in ("nsubj", "nsubj:pass", "csubj"):
                        subj = child
                        break
                if subj is None:
                    for anc in head.ancestors:
                        for child in anc.children:
                            if child.dep_ in ("nsubj", "nsubj:pass", "csubj"):
                                subj = child
                                break
                        if subj is not None:
                            break
                if subj is not None:
                    dist = abs((head.idx + len(head.text)) - subj.idx)
                    if dist >= 50:
                        start = min(subj.idx, head.idx)
                        end = max(subj.idx + len(subj.text), head.idx + len(head.text))
                        yield {
                            "start": start,
                            "end": end,
                            "match": text[start:end],
                            "message": "主語と述語が離れすぎています（読みにくさの可能性）",
                            "suggestion": None,
                            "severity": "INFO",
                            "rule_id": "NLP_SUBJ_VERB_DIST",
                        }

__all__ = ["is_available", "run_nlp"]
