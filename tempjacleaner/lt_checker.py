from __future__ import annotations
"""
LanguageTool 連携: language_tool_python を用いてテキストを校正し、
内部 Issue 形式に変換して返す。

注意:
- オフライン利用では Java が必要な場合があります。
- language_tool_python はデフォルトでオンラインの public API に接続する場合があります。
  ネットワークポリシーに従ってご利用ください。
"""
from typing import Iterator, Dict, Any, Optional

try:  # Optional dependency
    import language_tool_python as ltp
    _LT_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency may be missing
    ltp = None  # type: ignore
    _LT_AVAILABLE = False


def is_available() -> bool:
    return _LT_AVAILABLE


def run_languagetool(text: str, lang: str = "ja-JP") -> Iterator[Dict[str, Any]]:
    """LanguageTool で text をチェックし、Issue 互換の辞書を yield。

    Fields: start, end, match, message, suggestion (任意), severity, rule_id
    """
    if not _LT_AVAILABLE:
        return iter(())
    # 使い回し: 毎回作るとコスト高。Tool は軽くないため、簡易なキャッシュをモジュール変数で。
    tool = _get_tool(lang)
    try:
        matches = tool.check(text)
    except Exception:
        # ネットワーク/Java 周りの例外は握りつぶしてスキップ
        return iter(())
    for m in matches:
        start = getattr(m, 'offset', 0)
        length = getattr(m, 'errorLength', 0)
        end = start + length
        msg = getattr(m, 'message', 'LanguageTool指摘')
        rule_id = getattr(m, 'ruleId', 'LT')
        repls = getattr(m, 'replacements', [])
        suggestion: Optional[str] = None
        if repls:
            suggestion = str(repls[0])
        yield {
            "start": start,
            "end": end,
            "match": text[start:end],
            "message": msg,
            "suggestion": suggestion,
            "severity": "INFO",
            "rule_id": f"LT_{rule_id}",
        }


_tool_cache: dict[str, Any] = {}

def _get_tool(lang: str):
    tool = _tool_cache.get(lang)
    if tool is None:
        tool = ltp.LanguageToolPublicAPI(lang) if hasattr(ltp, 'LanguageToolPublicAPI') else ltp.LanguageTool(lang)
        _tool_cache[lang] = tool
    return tool


__all__ = ["is_available", "run_languagetool"]
