"""検出結果に基づく自動修正。

- デフォルトは安全志向: suggestion がある項目のみ置換。
- aggressive=True でヒューリスティック修正を広げ、suggestion が無い項目にも対処（句読点/記号の連続、口語簡易置換、長文の粗分割など）。
"""
from __future__ import annotations
from typing import List, Optional
import re
import unicodedata
from .checker import Issue

def _compress_run(s: str, prefer_fullwidth: Optional[str] = None) -> str:
    # 同一記号の連続を1文字に圧縮
    if not s:
        return s
    ch = s[0]
    if prefer_fullwidth and prefer_fullwidth in s:
        ch = prefer_fullwidth
    return ch

def _normalize_alnum_kana(s: str) -> str:
    # 全角英数字/半角カナをNFKCで正規化
    return unicodedata.normalize("NFKC", s)

def _fix_double_particles(s: str) -> str:
    # のの/がが/にに... -> 1文字に圧縮
    if len(s) == 2 and s[0] == s[1]:
        return s[0]
    return s

COLLOQ_MAP = {
    "とかさ": "など",
    "とか": "など",
    "っぽさ": "のような性質",
    "っぽい": "のような",
    "みたいな": "のような",
    "みたい": "のようだ",
}

def _fix_colloquial(s: str) -> str:
    return COLLOQ_MAP.get(s, s)

def _fix_double_adverb(s: str) -> str:
    pairs = [
        ("かなり", "とても"), ("かなり", "すごく"), ("とても", "すごく"), ("非常に", "とても"), ("非常に", "すごく")
    ]
    for a, b in pairs:
        if s.startswith(a) and s[len(a):].lstrip().startswith(b):
            return b
    # デフォルトは後段を残す
    parts = re.split(r"\s+", s, maxsplit=1)
    if len(parts) == 2:
        return parts[1]
    return s

def _fix_punct_mixed(s: str) -> str:
    # ．→。 ，→、
    return s.replace("．", "。").replace("，", "、")

def _fix_space_before_punct(s: str) -> str:
    # 句読点直前スペースは削除（ここではスニペット全体がスペースになる想定）
    return ""

def _fix_ellipsis_ascii(s: str) -> str:
    return re.sub(r"\.{2,}", "…", s)

def _fix_long_dash(s: str) -> str:
    return re.sub(r"ー{2,}", "ー", s)

def _fix_repeat_char(s: str) -> str:
    # 句読点/記号の連続を1つに
    if "、" in s:
        return "、"
    if "。" in s:
        return "。"
    if "！" in s or "!" in s:
        return _compress_run(s, prefer_fullwidth="！")
    if "？" in s or "?" in s:
        return _compress_run(s, prefer_fullwidth="？")
    return s[0] if s else s

def _fix_cjk_inner_space(s: str) -> str:
    # 日本語の間の半角スペースを削除
    return re.sub(r"(?<=[\u3040-\u30FF\u4E00-\u9FFF])[ ]+(?=[\u3040-\u30FF\u4E00-\u9FFF])", "", s)

def _fix_multi_spaces(s: str) -> str:
    return re.sub(r"\s{2,}", " ", s)

def _fix_punct_order(s: str) -> str:
    s = re.sub(r"[。．][、，]+", "。", s)
    s = re.sub(r"[、，][。．]+", "、", s)
    return s

def _fix_kango_to_hiragana(s: str) -> str:
    # 為に/為の -> ために/ための, 貰* -> もら*
    s = s.replace("為", "ため")
    s = s.replace("貰", "もら")
    return s

_URL_RE = re.compile(r"https?://|ftp://|www\.", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CODE_HINT_RE = re.compile(r"`[^`]+`|\b[A-Za-z_][A-Za-z0-9_]*\(\)|::{1,2}|<[^>]+>")
_UPPER_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

def _context_allows(issue: Issue, full_text: str) -> bool:
    s = issue.start
    e = issue.end
    # 周辺100文字を見て、URL/メール/コード片/全大文字語が混じる場合は置換を避ける
    l = max(0, s - 100)
    r = min(len(full_text), e + 100)
    ctx = full_text[l:r]
    # スニペット自体がこれらに該当しても避ける
    snip = full_text[s:e]
    if _URL_RE.search(ctx) or _EMAIL_RE.search(ctx):
        return False
    if _CODE_HINT_RE.search(ctx):
        return False
    if _UPPER_TOKEN_RE.search(ctx):
        # 全大文字の識別子（API名など）はスキップ
        return False
    # 日本語以外が大半ならスキップ（簡易判定）
    jp = sum('一' <= ch <= '龥' or 'ぁ' <= ch <= 'ゖ' or 'ァ' <= ch <= 'ヺ' for ch in snip)
    if len(snip) > 0 and jp / len(snip) < 0.3:
        return False
    # Markdownコードフェンス ``` の内側なら避ける（簡易判定: 直前/直後のフェンス出現数が奇数）
    fence = "```"
    left = full_text[:s].count(fence)
    right = full_text[e:].count(fence)
    if (left % 2 == 1) and (right % 2 == 1):
        return False
    return True

def _is_japanese_char(ch: str) -> bool:
    return ('一' <= ch <= '龥') or ('ぁ' <= ch <= 'ゖ') or ('ァ' <= ch <= 'ヺ') or ('ー' == ch)

def _jp_ratio(s: str) -> float:
    if not s:
        return 0.0
    jp = sum(_is_japanese_char(ch) for ch in s)
    return jp / max(1, len(s))

def _lt_suggestion_is_safe(orig: str, sug: str) -> bool:
    # 長すぎる/短すぎる変更は避ける
    if abs(len(orig) - len(sug)) > 3:
        return False
    # ASCII英字の導入は避ける（記号は許容）
    if re.search(r"[A-Za-z]", sug):
        return False
    # 日本語率が極端に下がるなら避ける
    if _jp_ratio(orig) >= 0.5 and _jp_ratio(sug) < 0.3:
        return False
    # 制御文字など怪しい文字は避ける
    if any(ord(c) < 32 for c in sug):
        return False
    return True

def _compute_suggestion(issue: Issue, full_text: str, aggressive: bool, use_lt: bool, use_nlp: bool) -> Optional[str]:
    if issue.suggestion:
        return issue.suggestion
    msg = issue.message or ""
    snip = full_text[issue.start:issue.end]
    rid = issue.rule_id or ""
    # タイポ・スペース・誤字脱字・変換ミス・編集ミス・文字化けの自動修正さらに強化
    # 1. 文字化け・不可視スペース（連続もまとめて削除）
    if re.search(r"([\uFFFD�\u00A0\u200B\u200C\u200D\uFEFF])+", snip):
        return ""
    # 2. 二重語・編集ミス（ひらがな・カタカナ・漢字の2文字以上の繰り返し）
    if re.fullmatch(r"([ぁ-んァ-ヶ一-龥]{2,})\1+", snip):
        return snip[:len(snip)//(snip.count(snip[:len(snip)//2])+1)]
    # 3. ひらがな・カタカナ1文字の3回以上連続→1回に
    if re.fullmatch(r"([ぁ-んァ-ヶ])\1{2,}", snip):
        return snip[0]
    # 4. 句読点・感嘆符・疑問符の連続は2回まで許容
    if re.fullmatch(r"([、。！？])\1{2,}", snip):
        return snip[0]*2
    # 5. 全角スペース→半角、連続スペース→1つ
    if re.fullmatch(r"　+", snip):
        return " "
    if re.fullmatch(r"[ ]{2,}", snip):
        return " "
    # 6. 行頭・行末スペース
    if re.fullmatch(r"^[ \t　]+|[ \t　]+$", snip):
        return ""
    # 7. 半角カナ→全角カナ
    if re.fullmatch(r"[ｦ-ﾟ]+", snip):
        return unicodedata.normalize("NFKC", snip)
    # 8. 連続長音・中黒・スラッシュ・ハイフンの正規化
    if re.fullmatch(r"ー{2,}", snip):
        return "ー"
    if re.fullmatch(r"・{2,}", snip):
        return "・"
    if re.fullmatch(r"[／/]{2,}", snip):
        return "/"
    if re.fullmatch(r"[－-]{2,}", snip):
        return "-"
    # 9. 句読点直前・直後スペースの削除
    if re.fullmatch(r"\s+[、。]|[、。]\s+", snip):
        return snip.strip()
    # 10. ひらがな・カタカナ混在の正規化（カタカナ優先）
    if re.fullmatch(r"[ぁ-んァ-ヶ]{2,}", snip):
        hira = sum('ぁ' <= c <= 'ゖ' for c in snip)
        kata = sum('ァ' <= c <= 'ヺ' for c in snip)
        if kata > hira:
            return snip.translate(str.maketrans('ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをん','ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲン'))
    # 11. よくある誤用漢字・表現ゆれの辞書拡充
    typo_map = {
        "有り難う": "ありがとう", "有難う": "ありがとう", "有りがとう": "ありがとう",
        "御座いまし": "ございました", "御座います": "ございます", "御座いません": "ございません",
        "出来ます": "できます", "下さいます": "くださいます", "下さる": "くださる",
        "未だ": "まだ", "未だに": "まだに", "確立": "確率", "確率": "確率", "以外": "以外", "意外": "意外",
        "一応": "一応", "一様": "一様", "早急": "至急", "早急に": "至急に"
    }
    if snip in typo_map:
        return typo_map[snip]
    # 12. 句点・読点の混在パターンの正規化
    if re.fullmatch(r"[、，][。．]", snip):
        return "、。"
    if re.fullmatch(r"[。．][、，]", snip):
        return "。"
    # 13. 句点・読点の順序誤りの修正
    if re.fullmatch(r"[、。][、。]", snip):
        return snip[0]
    # 7. 以外/意外、確立/確率、一応/一様 など誤用注意（自動修正はしない）
    # 8. advanced_rules の rule_id ベース
    if rid == "ADV_DOUBLE_PARTICLE":
        return _fix_double_particles(snip)
    if rid == "ADV_DOUBLE_ADVERB":
        return _fix_double_adverb(snip)
    if rid == "ADV_COLLOQUIAL":
        return _fix_colloquial(snip) if aggressive else None
    if rid == "ADV_PUNCT_MIXED":
        return _fix_punct_mixed(snip)
    if rid == "ADV_SPACE_BEFORE_PUNCT":
        return _fix_space_before_punct(snip)
    if rid == "ADV_ELLIPSIS":
        return _fix_ellipsis_ascii(snip)
    if rid == "ADV_PROLONGED_SOUND":
        return _fix_long_dash(snip)
    if rid == "ADV_EMPHATIC_ADVERB_MANY":
        return "" if aggressive else None
    if rid == "ADV_LONG_SENTENCE" and aggressive:
        s = issue.start
        e = issue.end
        part = full_text[s:e]
        if not part:
            return None
        mid = len(part) // 2
        left = part.rfind("、", 0, mid)
        right = part.find("、", mid)
        idx = left if left != -1 else right
        if idx != -1:
            return part[:idx] + "。" + part[idx+1:]
        return None
    # typorules 系メッセージのヒューリスティック
    if "全角英数字が含まれています" in msg:
        return _normalize_alnum_kana(snip)
    if "半角カナが含まれています" in msg:
        return _normalize_alnum_kana(snip)
    if "句読点が連続しています" in msg:
        return _fix_repeat_char(snip)
    if "感嘆符が連続しています" in msg or "疑問符が連続しています" in msg:
        return _fix_repeat_char(snip)
    if "長音の連続" in msg:
        return _fix_long_dash(snip)
    if "為に" in msg or "為の" in msg or "'為" in msg:
        return _fix_kango_to_hiragana(snip)
    if "漢字 '貰'" in msg:
        return _fix_kango_to_hiragana(snip)
    if "全角スペースが含まれています" in msg:
        return " "
    if "連続スペースを1つに" in msg:
        return _fix_multi_spaces(snip)
    if "日本語の間のスペースを削除" in msg:
        return _fix_cjk_inner_space(snip)
    if "句点直後の読点" in msg or "読点直後の句点" in msg:
        return _fix_punct_order(snip)
    if "編集ミスの可能性" in msg and "にりして" in snip:
        return "にして"
    if "文字化けの可能性" in msg:
        return ""
    # LanguageTool の提案を安全採用
    if rid.startswith("LT_") and use_lt:
        sug = issue.suggestion
        if sug and _lt_suggestion_is_safe(snip, sug):
            return sug
        return None
    # NLP 由来のヒントは aggressive のときのみ軽微修正
    if rid == "NLP_NO_CHAIN" and use_nlp and aggressive:
        idxs = [m.start() for m in re.finditer("の", snip)]
        if len(idxs) >= 3:
            k = idxs[-2]
            return snip[:k] + "、" + snip[k:]
        return None
    if rid == "NLP_PARTICLE_RUN" and use_nlp and aggressive:
        return re.sub(r"([をにがへとでからより])\1", r"\1", snip)
    return None

def apply_fixes(text: str, issues: List[Issue], aggressive: bool = False, context: bool = False, use_lt: bool = False, use_nlp: bool = False) -> str:
    # ファイル内オフセットでソートし、重なりはスキップ
    issues2 = []
    for i in issues:
        if context and not _context_allows(i, text):
            continue
        # LT/NLP を未採用とする場合は、その種別の suggestion を無効化
        if i.rule_id and i.rule_id.startswith("LT_") and not use_lt:
            pass  # 採用しない
        elif i.rule_id and i.rule_id.startswith("NLP_") and not use_nlp:
            pass  # 採用しない
        sug = _compute_suggestion(i, text, aggressive, use_lt=use_lt, use_nlp=use_nlp)
        if sug is None:
            continue
        # 一時的に suggestion に格納（非破壊でもよいが簡便のため）
        i.suggestion = sug
        issues2.append(i)
    issues2.sort(key=lambda x: (x.start, x.end))
    out = []
    cur = 0
    for i in issues2:
        if i.start < cur:
            continue  # overlap skip
        out.append(text[cur:i.start])
        out.append(i.suggestion or text[i.start:i.end])
        cur = i.end
    out.append(text[cur:])
    return "".join(out)

__all__ = ["apply_fixes"]
