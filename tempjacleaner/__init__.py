"""tempjacleaner
日本語文字列の簡易誤字脱字検出ライブラリ。

主な提供機能:
- 任意拡張子ファイルから文字列リテラルらしき部分/日本語部分のみ抽出
- 簡易ルールベースでの誤記(よくある打鍵ミス)検出
- CLI インターフェース

将来拡張(案):
- 形態素解析(MeCab, Sudachi等)による文節解析
- 統計的/言語モデルによる文脈的誤り検出
- カスタム辞書 (プロジェクト独自語彙) の組込み
"""
from .checker import check_text, check_file, check_paths

__all__ = [
    "check_text",
    "check_file",
    "check_paths",
]

__version__ = "0.1.0"
