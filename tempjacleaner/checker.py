"""高レベル API: テキスト/ファイル/パス群に対する誤字検出

- 日本語抽出（コード/プレーン）
- コメント抽出（デフォルト有効）
- 形態素分析オプション
- 拡張ルール / LanguageTool / NLP / スペルチェック（任意）
- パス走査と簡易キャッシュ/並列
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Iterable, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .japanese_extractor import extract_japanese_from_code, extract_japanese_blocks
from .comments import extract_comments
from .file_scanner import iter_files, read_text
from .morph import tokenize_with_spans, is_available as morph_available
from .cache import load_cache, save_cache, file_fingerprint
from .advanced_rules import run_advanced, detect_style_mixed_lines
from . import typo_rules
from .lt_checker import run_languagetool, is_available as lt_available
from .nlp_checker import run_nlp, is_available as nlp_available
from .spellcheck import run_spellcheck, load_dict, is_available as spell_available


@dataclass
class Issue:
    file: str | None
    start: int
    end: int
    snippet: str
    message: str
    suggestion: str | None
    severity: str = "WARN"
    rule_id: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "start": self.start,
            "end": self.end,
            "snippet": self.snippet,
            "message": self.message,
            "suggestion": self.suggestion,
            "severity": self.severity,
            "rule_id": self.rule_id,
        }


def _gather_spans(text: str, from_code: bool, include_comments: bool) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    extractor = extract_japanese_from_code if from_code else extract_japanese_blocks
    spans.extend(extractor(text))
    if include_comments:
        for c_start, c_end, comment in extract_comments(text):
            for j_start, j_end, block in extract_japanese_blocks(comment):
                spans.append((c_start + j_start, c_start + j_end, block))
    return spans


def check_text(
    text: str,
    from_code: bool = True,
    file: str | None = None,
    include_comments: bool = True,
    morph: bool = False,
    advanced: bool = False,
    lt: bool = False,
    lt_lang: str = "ja-JP",
    nlp: bool = False,
    nlp_model: str = "ja_ginza",
    spell: bool = False,
    dict_words: List[str] | None = None,
    semantic: bool = False,
) -> List[Issue]:
    issues: List[Issue] = []
    spans = _gather_spans(text, from_code=from_code, include_comments=include_comments)

    for start, end, jp in spans:
        # 形態素オプション: サーフェス単位で細かく見る（位置をずらす）
        if morph and morph_available():
            token_spans = tokenize_with_spans(jp)  # (s,e,surf,...) あるいは (s,e,surf)
            subspans: List[Tuple[int, int, str]] = []
            for t in token_spans:
                if len(t) >= 3:
                    s, e, surf = t[0], t[1], t[2]
                else:
                    s, e = t[0], t[1]
                    surf = jp[s:e]
                subspans.append((start + s, start + e, surf))
        else:
            subspans = [(start, end, jp)]

        for s2, e2, jp2 in subspans:
            # 基本ルール
            for hit in typo_rules.run_rules(jp2):
                rel_start = s2 + hit["start"]
                rel_end = s2 + hit["end"]
                issues.append(Issue(
                    file=file,
                    start=rel_start,
                    end=rel_end,
                    snippet=text[rel_start:rel_end],
                    message=hit["message"],
                    suggestion=hit.get("suggestion"),
                    severity=hit.get("severity", "WARN"),
                    rule_id=hit.get("rule_id"),
                ))

            # 拡張ルール
            if advanced:
                for hit in run_advanced(jp2):
                    rel_start = s2 + hit["start"]
                    rel_end = s2 + hit["end"]
                    issues.append(Issue(
                        file=file,
                        start=rel_start,
                        end=rel_end,
                        snippet=text[rel_start:rel_end],
                        message=hit["message"],
                        suggestion=hit.get("suggestion"),
                        severity=hit.get("severity", "INFO"),
                        rule_id=hit.get("rule_id"),
                    ))

            # LanguageTool
            if lt and lt_available():
                for hit in run_languagetool(jp2, lang=lt_lang):
                    rel_start = s2 + hit["start"]
                    rel_end = s2 + hit["end"]
                    issues.append(Issue(
                        file=file,
                        start=rel_start,
                        end=rel_end,
                        snippet=text[rel_start:rel_end],
                        message=hit["message"],
                        suggestion=hit.get("suggestion"),
                        severity=hit.get("severity", "INFO"),
                        rule_id=hit.get("rule_id"),
                    ))

            # spaCy+GiNZA ベース（別モジュール）
            if (nlp or semantic) and nlp_available():
                for hit in run_nlp(jp2, model=nlp_model):
                    rel_start = s2 + hit["start"]
                    rel_end = s2 + hit["end"]
                    issues.append(Issue(
                        file=file,
                        start=rel_start,
                        end=rel_end,
                        snippet=text[rel_start:rel_end],
                        message=hit["message"],
                        suggestion=hit.get("suggestion"),
                        severity=hit.get("severity", "INFO"),
                        rule_id=hit.get("rule_id"),
                    ))

            # スペルチェック
            if spell and spell_available() and dict_words:
                for hit in run_spellcheck(jp2, dict_words=dict_words):
                    rel_start = s2 + hit["start"]
                    rel_end = s2 + hit["end"]
                    issues.append(Issue(
                        file=file,
                        start=rel_start,
                        end=rel_end,
                        snippet=text[rel_start:rel_end],
                        message=hit["message"],
                        suggestion=hit.get("suggestion"),
                        severity=hit.get("severity", "INFO"),
                        rule_id=hit.get("rule_id"),
                    ))

    # テキスト全体に対して文体混在の行単位チェック
    if advanced:
        hit = detect_style_mixed_lines(text)
        if hit:
            issues.append(Issue(
                file=file,
                start=hit["start"],
                end=hit["end"],
                snippet=text[hit["start"]:hit["end"]],
                message=hit["message"],
                suggestion=hit.get("suggestion"),
                severity=hit.get("severity", "WARN"),
                rule_id=hit.get("rule_id"),
            ))

    return issues


def check_file(
    path: str,
    include_comments: bool = True,
    morph: bool = False,
    advanced: bool = False,
    lt: bool = False,
    lt_lang: str = "ja-JP",
    nlp: bool = False,
    nlp_model: str = "ja_ginza",
    spell: bool = False,
    dict_words: List[str] | None = None,
    semantic: bool = False,
) -> List[Issue]:
    content = read_text(Path(path))
    if content is None:
        return []
    return check_text(
        content,
        from_code=True,
        file=path,
        include_comments=include_comments,
        morph=morph,
        advanced=advanced,
        lt=lt,
        lt_lang=lt_lang,
        nlp=nlp,
        nlp_model=nlp_model,
        spell=spell,
        dict_words=dict_words,
        semantic=semantic,
    )


def check_paths(
    paths: Iterable[str],
    include_comments: bool = True,
    morph: bool = False,
    jobs: int = 1,
    use_cache: bool = True,
    advanced: bool = False,
    lt: bool = False,
    lt_lang: str = "ja-JP",
    nlp: bool = False,
    nlp_model: str = "ja_ginza",
    spell: bool = False,
    dict_files: List[str] | None = None,
    semantic: bool = False,
) -> List[Issue]:
    files = list(iter_files(paths))

    # キャッシュ読み込み
    cache = load_cache(str(Path.cwd())) if use_cache else {}
    to_scan: List[Tuple[str, str]] = []  # (path, fingerprint)
    results: List[Issue] = []

    for f in files:
        fp = file_fingerprint(Path(f))
        key = str(f)
        if use_cache and cache.get(key) == fp:
            continue
        to_scan.append((key, fp))

    # 辞書ロード
    dict_words: List[str] | None = None
    if spell and dict_files:
        try:
            dict_words = load_dict(dict_files)
        except Exception:
            dict_words = None

    # 並列/直列実行
    if jobs and jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = {
                ex.submit(
                    check_file,
                    key,
                    include_comments,
                    morph,
                    advanced,
                    lt,
                    lt_lang,
                    nlp,
                    nlp_model,
                    spell,
                    dict_words,
                    semantic,
                ): (key, fp)
                for key, fp in to_scan
            }
            for fut in as_completed(futs):
                key, fp = futs[fut]
                try:
                    res = fut.result()
                except Exception:
                    res = []
                results.extend(res)
                if use_cache:
                    cache[key] = fp
    else:
        for key, fp in to_scan:
            results.extend(
                check_file(
                    key,
                    include_comments=include_comments,
                    morph=morph,
                    advanced=advanced,
                    lt=lt,
                    lt_lang=lt_lang,
                    nlp=nlp,
                    nlp_model=nlp_model,
                    spell=spell,
                    dict_words=dict_words,
                    semantic=semantic,
                )
            )
            if use_cache:
                cache[key] = fp

    # キャッシュ保存
    if use_cache:
        save_cache(str(Path.cwd()), cache)

    return results


__all__ = ["check_text", "check_file", "check_paths", "Issue"]
