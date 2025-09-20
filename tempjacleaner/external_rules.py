"""YAML / JSON から TypoPattern をロードするユーティリティ。
フォーマット例:

YAML:
---
- pattern: "誤表記"
  message: "説明"
  suggestion: "正しい表記"
  severity: WARN
- pattern: "危険な語"
  message: "使用を避ける"
  severity: ERROR

JSON: 上記と同じ構造の配列。
"""
from __future__ import annotations
from pathlib import Path
import json
from .typo_rules import TypoPattern
import re

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # YAML未インストール時はJSONのみ


def load_rule_file(path: str):
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    # いくつかのエンコーディング候補を試す (PowerShell Set-Content デフォルト UTF-16 対応)
    raw = p.read_bytes()
    text: str | None = None
    for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp932"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise UnicodeDecodeError("unknown", b"", 0, 1, "Unable to decode rule file with tried encodings")
    data = None
    if text.startswith('\ufeff'):
        text = text.lstrip('\ufeff')
    if p.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAMLがインストールされていないためYAMLは読み込めません。'pip install PyYAML' を実行してください")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("ルールファイルは配列である必要があります")
    patterns: list[TypoPattern] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        pat = item.get("pattern")
        msg = item.get("message") or ""
        sug = item.get("suggestion")
        sev = (item.get("severity") or "WARN").upper()
        try:
            r = re.compile(pat)
        except Exception as e:
            raise ValueError(f"Invalid regex: {pat}: {e}")
        patterns.append(TypoPattern(pattern=r, message=msg, suggestion=sug, severity=sev))
    return patterns

__all__ = ["load_rule_file"]
