"""誤字/脱字/表記ゆれを検出するための簡易ルール定義モジュール。

現状: シンプルな静的パターンマッチのみ。
将来: 辞書プラグイン化・頻度統計・機械学習モデル差し替え。

# TODO: pattern定義を外部YAML/JSON化しユーザー設定で追加可能にする。
# TODO: severity (INFO/WARN/ERROR) を TypoPattern に追加。
# TODO: 正規化( NFC/NFKC )前後比較による全角半角ゆれ検出。
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Iterable, List, Pattern
from pathlib import Path
import json

@dataclass
class TypoPattern:
    pattern: Pattern[str]
    message: str
    suggestion: str | None = None
    severity: str = "WARN"  # INFO/WARN/ERROR
    rule_id: str | None = None

    def finditer(self, text: str):
        for m in self.pattern.finditer(text):
            yield {
                "start": m.start(),
                "end": m.end(),
                "match": m.group(0),
                "message": self.message,
                "suggestion": self.suggestion,
                "severity": self.severity,
                "rule_id": self.rule_id,
            }

def _simple_patterns() -> List[TypoPattern]:
    # よくある日本語の打ち間違い/表記揺れ(サンプル+拡充)
    raw: list[tuple[str, str, str | None, str]] = [
        # 旧字体・硬い表記→現代表記（スタイル寄り: INFO）
        (r"勿論", "旧字体/硬い表記 '勿論' -> 'もちろん'", "もちろん", "INFO"),
        (r"有り難う", "旧表記 '有り難う' -> 'ありがとう'", "ありがとう", "INFO"),
        (r"有難う", "旧表記 '有難う' -> 'ありがとう'", "ありがとう", "INFO"),
        (r"御座い", "旧表記 '御座い' -> 'ござい'", "ござい", "INFO"),
        (r"御座います", "旧表記 '御座います' -> 'ございます'", "ございます", "INFO"),
        (r"御座いました", "旧表記 '御座いました' -> 'ございました'", "ございました", "INFO"),
        (r"(宜|可)し?しく", "'宜しく/可しく' -> 'よろしく' を推奨", "よろしく", "INFO"),
        (r"[遙遥]か", "'遙か/遥か' -> 'はるか' (ひらがな推薦)", "はるか", "INFO"),
        (r"御願い", "'御願い' -> 'お願い'", "お願い", "INFO"),
        (r"予め", "'予め' -> 'あらかじめ' を推奨", "あらかじめ", "INFO"),
        (r"於(い)?て", "'於いて/於て' -> 'おいて' を推奨", "おいて", "INFO"),
        (r"稀に", "'稀に' -> 'まれに' を推奨", "まれに", "INFO"),
        (r"因みに|因に", "'因みに/因に' -> 'ちなみに' を推奨", "ちなみに", "INFO"),
        (r"尚", "'尚' -> 'なお' を推奨", "なお", "INFO"),
        (r"但し", "'但し' -> 'ただし' を推奨", "ただし", "INFO"),
        (r"勿体無い", "'勿体無い' -> 'もったいない' を推奨", "もったいない", "INFO"),
        (r"或いは", "'或いは' -> 'あるいは' を推奨", "あるいは", "INFO"),
        (r"且つ", "'且つ' -> 'かつ' を推奨", "かつ", "INFO"),
        (r"様に", "'様に' -> 'ように' を推奨", "ように", "INFO"),
        (r"貴(方|女|男)", "'貴方/貴女/貴男' -> 'あなた' を推奨", "あなた", "INFO"),
        (r"只今", "'只今' -> 'ただいま' を推奨", "ただいま", "INFO"),
        (r"迄", "'迄' -> 'まで' を推奨", "まで", "INFO"),
        (r"様々", "'様々' -> 'さまざま' を推奨", "さまざま", "INFO"),
        (r"出来上が", "'出来上が' -> 'できあが' を推奨", "できあが", "INFO"),
        (r"出来ます", "'出来ます' -> 'できます' を推奨", "できます", "INFO"),
        (r"お早う", "'お早う' -> 'おはよう' を推奨", "おはよう", "INFO"),
        (r"お目出度(う|い)", "'お目出度い/お目出度う' -> 'おめでたい/おめでとう' を推奨", None, "INFO"),
        # 助詞・補助動詞のかな表記推奨（やや強め: WARN）
        (r"下さい", "補助動詞 '下さい' -> 'ください' を推奨", "ください", "WARN"),
        (r"下さいませ", "補助動詞 '下さいませ' -> 'くださいませ' を推奨", "くださいませ", "WARN"),
        (r"致します", "補助動詞 '致します' -> 'いたします' を推奨", "いたします", "WARN"),
        (r"致しました", "補助動詞 '致しました' -> 'いたしました' を推奨", "いたしました", "WARN"),
        (r"致しません", "補助動詞 '致しません' -> 'いたしません' を推奨", "いたしません", "WARN"),
        (r"頂きます", "補助動詞 '頂きます' -> 'いただきます' を推奨", "いただきます", "WARN"),
        (r"頂いた", "補助動詞 '頂いた' -> 'いただいた' を推奨", "いただいた", "WARN"),
        (r"頂けますか", "補助動詞 '頂けますか' -> 'いただけますか' を推奨", "いただけますか", "WARN"),
        # '出来' 活用（suggestionは文脈依存: WARN）
        (r"出来(る|た|て|ない|ません|ました|ませんでした|なかった|ませんか)", "'出来' -> 'でき' のひらがな表記を推奨", None, "WARN"),
        # 旧漢字/硬い '為'（文脈依存: INFO）
        (r"為(に|の)", "'為に/為の' -> 'ために/ための' を推奨", None, "INFO"),
        # 半角・全角のゆれ（実害寄り: 半角ｶﾅ=WARN, 全角英数=INFO, 半角長音=INFO, 全角スペース=ERROR）
        (r"[ｦ-ﾟ]+", "半角カナが含まれています (全角カタカナへの統一を検討)", None, "WARN"),
        (r"[Ａ-Ｚａ-ｚ０-９]+", "全角英数字が含まれています (半角英数字への統一を検討)", None, "INFO"),
        (r"ｰ+", "半角長音記号 'ｰ' が含まれます (全角 'ー' へ統一を検討)", "ー", "INFO"),
        (r"　+", "全角スペースが含まれています (半角スペースへの統一を検討)", " ", "ERROR"),
        # 句読点などの連続（可読性: WARN）
        (r"、、|。。", "句読点が連続しています", None, "WARN"),
        (r"[！!]{2,}", "感嘆符が連続しています", None, "INFO"),
        (r"[？?]{2,}", "疑問符が連続しています", None, "INFO"),
        # '御〜' の表記（安全な一部: INFO）
        (r"御連絡", "'御連絡' -> 'ご連絡' を推奨", "ご連絡", "INFO"),
        (r"御確認", "'御確認' -> 'ご確認' を推奨", "ご確認", "INFO"),
        (r"御案内", "'御案内' -> 'ご案内' を推奨", "ご案内", "INFO"),
        (r"御利用", "'御利用' -> 'ご利用' を推奨", "ご利用", "INFO"),
        (r"御問い合わせ", "'御問い合わせ' -> 'お問い合わせ' を推奨", "お問い合わせ", "INFO"),
        (r"御名前", "'御名前' -> 'お名前' を推奨", "お名前", "INFO"),
        (r"御住所", "'御住所' -> 'ご住所' を推奨", "ご住所", "INFO"),
        (r"御手数", "'御手数' -> 'お手数' を推奨", "お手数", "INFO"),
        (r"御覧", "'御覧' -> 'ご覧' を推奨", "ご覧", "INFO"),
        # ビジネス常用の用語の表記揺れ（保守的: INFO）
        (r"お問合せ", "'お問合せ' -> 'お問い合わせ' を推奨", "お問い合わせ", "INFO"),
        (r"取扱い", "'取扱い' -> '取り扱い' を推奨", "取り扱い", "INFO"),
        (r"見積り", "'見積り' -> '見積もり' を推奨", "見積もり", "INFO"),
        # スペース/句読点/編集ミス系
        (r"\s{2,}", "連続スペースを1つに", " ", "INFO"),
        (r"(?<=[\u3040-\u30FF\u4E00-\u9FFF])[ ]+(?=[\u3040-\u30FF\u4E00-\u9FFF])", "日本語の間のスペースを削除", "", "INFO"),
        (r"[。．][、，]+", "句点直後の読点を削除/統一", "。", "WARN"),
        (r"[、，][。．]+", "読点直後の句点を削除/統一", "、", "WARN"),
        (r"にりして", "編集ミスの可能性: 'にりして' -> 'にして'", "にして", "WARN"),
        # 文字化け検知（代表例: ERROR寄りの検出/WARN）
        (r"\uFFFD{2,}", "文字化けの可能性（置換文字が連続）", None, "ERROR"),
        (r"(?:Ã.|Â.){2,}", "文字化けの可能性（エンコーディング不一致）", None, "WARN"),
    ]
    patterns = [
        TypoPattern(pattern=re.compile(p), message=msg, suggestion=sug, severity=sev) for p, msg, sug, sev in raw
    ]

    # 内蔵の表記ゆれ辞書（variants.json）を読み込み（存在する場合）
    try:
        here = Path(__file__).parent
        builtin_variants = here / "rules" / "variants.json"
        if builtin_variants.exists():
            raw = builtin_variants.read_bytes()
            text = None
            for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp932"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text:
                if text.startswith('\ufeff'):
                    text = text.lstrip('\ufeff')
                data = json.loads(text)
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        pat = item.get("pattern")
                        msg = item.get("message") or ""
                        sug = item.get("suggestion")
                        sev = (item.get("severity") or "WARN").upper()
                        try:
                            r = re.compile(pat)
                        except Exception:
                            continue
                        patterns.append(TypoPattern(pattern=r, message=msg, suggestion=sug, severity=sev))
    except Exception:
        # 読み込み失敗時は無視（既存ルールのみで継続）
        pass
    return patterns

_PATTERNS: List[TypoPattern] | None = None

def add_patterns(patterns: List[TypoPattern]):
    """外部から読み込んだパターンを追加。"""
    global _PATTERNS
    if _PATTERNS is None:
        _PATTERNS = _simple_patterns()
    _PATTERNS.extend(patterns)

def get_patterns() -> List[TypoPattern]:
    global _PATTERNS
    if _PATTERNS is None:
        _PATTERNS = _simple_patterns()
    return _PATTERNS

def run_rules(text: str):
    for pat in get_patterns():
        yield from pat.finditer(text)

__all__ = ["run_rules", "get_patterns", "TypoPattern", "add_patterns"]
