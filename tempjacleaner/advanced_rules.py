from __future__ import annotations
import re
from typing import Iterator, Dict, Any, List, Optional
import unicodedata

# ら抜き言葉（ヒューリスティック）: 直前が「え段」かなで「れる」になっているものを検出
_E_ROW = set("えけげせぜてでねへべぺめれエケゲセゼテデネヘベペメレ")
# 単純な『れる』直前の文字を確認し、語幹がひらがな/漢字に限定
_RA_NUKI_RE = re.compile(r"([\u3040-\u30FF\u4E00-\u9FFF]+?)れる")

# 代表的なら抜き表現（誤用が頻出するものを個別に拾う）
_RANUKI_SPECIAL: List[tuple[str, str]] = [
    ("見れる", "見られる"),
    ("来れる", "来られる"),
    ("出れる", "出られる"),
    ("食べれる", "食べられる"),
    ("寝れる", "寝られる"),
    ("起きれる", "起きられる"),
    ("着れる", "着られる"),
]

_TAUTOLOGIES: List[tuple[str, str, str | None]] = [
    (r"一番最初", "重言の可能性: '一番最初'", "最初"),
    (r"一番最後", "重言の可能性: '一番最後'", "最後"),
    (r"過半数以上", "重言の可能性: '過半数以上'", "過半数"),
    (r"まず最初に", "重言の可能性: 'まず最初に'", "最初に"),
    (r"事前に予め", "重言の可能性: '事前に予め'", "事前に"),
    (r"違和感を感じる", "重言の可能性: '違和感を感じる'", "違和感がある"),
    (r"必須条件", "重言の可能性: '必須条件'", "必須"),
    (r"過半数の半分", "重言の可能性: '過半数の半分'", "過半数"),
    (r"新規に新たな", "重言の可能性: '新規に新たな'", "新たに"),
]

_TAUTOLOGY_RES = [(re.compile(p), msg, sug) for p, msg, sug in _TAUTOLOGIES]

# 連続助詞（簡易）: 「のの」「がが」「にに」「をを」「へへ」等
_DOUBLE_PARTICLES = ["のの", "がが", "にに", "をを", "へへ", "とと", "でで"]
_DOUBLE_PARTICLE_RES = [re.compile(re.escape(p)) for p in _DOUBLE_PARTICLES]

# 強調副詞の多用
_EMPHATIC_ADVS = ["非常に", "とても", "とっても", "すごく", "かなり", "大変", "めちゃくちゃ"]
_EMPHATIC_ADV_RE = re.compile("|".join(map(re.escape, _EMPHATIC_ADVS)))

# 閾値（ビジネス向け既定値）
EMPH_THRESHOLD: int = 2  # 強調副詞の多用: 出現回数のしきい値
LONG_SENTENCE_LIMIT: int = 100  # 1文の長さしきい値（文字数）
STYLE_MIX_THRESHOLD: int = 2    # 文体混在（行カウント）の閾値
KATAKANA_ALLOW: set[str] = set()
KATAKANA_DENY: set[str] = set()
SENTENCE_FINAL_PUNCT_SEVERITY: str = "INFO"  # INFO/WARN/ERROR
END_PARTICLE_POLICY: int = 0  # 0=none, 1=warn, 2=error

# 二重副詞（副詞×副詞の直列）: 例「かなりとても」「とてもすごく」
_DOUBLE_ADV_PAIRS = [
    ("かなり", "とても"), ("かなり", "すごく"), ("とても", "すごく"), ("非常に", "とても"), ("非常に", "すごく"),
]
_DOUBLE_ADV_RE = [re.compile(re.escape(a) + r"\s*" + re.escape(b)) for a, b in _DOUBLE_ADV_PAIRS]

# 口語・俗語（簡易）
_COLLOQUIAL_RE = re.compile(r"(とかさ|とか|っぽさ|っぽい|みたいな|みたい)")

# 句読点の混在（。と．、と，）
_MIXED_FULL_HALF_PUNCT_RE = re.compile(r"[。．].*[，、]|[，、].*[。．]")

# ASCII三点リーダ ... を検出（Unicodeの…に統一推奨）
_ASCII_ELLIPSIS_RE = re.compile(r"\.\.{2,}")

# 句読点直前のスペース（全角/半角）
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \u3000]+(?=[。．，、])")

# 伸ばし棒の多用（ーが3連以上）
_PROLONGED_SOUND_RE = re.compile(r"ー{3,}")

# 長文検出（1文=句点までの長さが閾値超過）
def _detect_long_sentences(text: str, limit: Optional[int] = None):
    if limit is None:
        limit = LONG_SENTENCE_LIMIT
    start = 0
    for m in re.finditer(r"。", text):
        end = m.end()
        if end - start > limit:
            yield start, end
        start = end
    # 最終文
    if len(text) - start > limit:
        yield start, len(text)

def run_advanced(text: str) -> Iterator[Dict[str, Any]]:
    # ら抜き（代表例の個別検出）
    for wrong, sug in _RANUKI_SPECIAL:
        for m in re.finditer(re.escape(wrong), text):
            yield {
                "start": m.start(),
                "end": m.end(),
                "match": wrong,
                "message": "ら抜き表現の可能性",
                "suggestion": sug,
                "severity": "WARN",
                "rule_id": "ADV_RANUKI",
            }

    # ら抜き（え段かな直前ヒューリスティック）
    # Markdownのコードフェンスやインラインコードの中はスキップ
    def _masked_ranges_md(t: str):
        ranges = []
        # フェンス ``` と ~~~
        fence_pat = re.compile(r"^\s*(```|~~~).*$", re.M)
        idxs = [m.start() for m in fence_pat.finditer(t)]
        for i in range(0, len(idxs), 2):
            if i + 1 < len(idxs):
                ranges.append((idxs[i], idxs[i+1]))
        # インラインコード `...`
        for m in re.finditer(r"`[^`\n]+`", t):
            ranges.append((m.start(), m.end()))
        return ranges

    masked = _masked_ranges_md(text)
    def _in_masked(pos: int) -> bool:
        for s, e in masked:
            if s <= pos < e:
                return True
        return False

    for m in _RA_NUKI_RE.finditer(text):
        head = m.group(1)
        # 直前の1文字が「え段」かなの場合のみ
        if not head:
            continue
        prev = head[-1]
        if prev in _E_ROW:
            start = m.start(0)
            end = m.end(0)
            if _in_masked(start):
                continue
            wrong = m.group(0)  # 例: 見れる
            suggestion = head + "られる"
            yield {
                "start": start,
                "end": end,
                "match": wrong,
                "message": "ら抜き表現の可能性",
                "suggestion": suggestion,
                # 誤検出低減のため基本は INFO とし、後述の個別代表例を WARN 維持
                "severity": "INFO",
                "rule_id": "ADV_RANUKI",
            }

    # 重言
    for pat, msg, sug in _TAUTOLOGY_RES:
        for m in pat.finditer(text):
            if _in_masked(m.start()):
                continue
            yield {
                "start": m.start(),
                "end": m.end(),
                "match": m.group(0),
                "message": msg,
                "suggestion": sug,
                # 重言は文脈で許容される場合もあるため WARN のまま
                "severity": "WARN",
                "rule_id": "ADV_TAUTOLOGY",
            }

    # 連続助詞
    for pat in _DOUBLE_PARTICLE_RES:
        for m in pat.finditer(text):
            yield {
                "start": m.start(),
                "end": m.end(),
                "match": m.group(0),
                "message": "連続する助詞の可能性",
                "suggestion": None,
                "severity": "WARN",
                "rule_id": "ADV_DOUBLE_PARTICLE",
            }

    # 強調副詞の多用（しきい値: EMPH_THRESHOLD 回以上）
    adv_hits = list(_EMPHATIC_ADV_RE.finditer(text))
    if len(adv_hits) >= EMPH_THRESHOLD:
        # 最初のヒット位置を基準に1件の集約結果を返す
        m0 = adv_hits[0]
        yield {
            "start": m0.start(),
            "end": m0.end(),
            "match": m0.group(0),
            "message": "強調副詞（非常に/とても/すごく など）の多用",
            "suggestion": None,
            "severity": "WARN",
            "rule_id": "ADV_EMPHATIC_ADVERB_MANY",
        }

    # 二重副詞の連続
    for pat in _DOUBLE_ADV_RE:
        for m in pat.finditer(text):
            yield {
                "start": m.start(),
                "end": m.end(),
                "match": m.group(0),
                "message": "二重副詞の可能性",
                "suggestion": None,
                "severity": "WARN",
                "rule_id": "ADV_DOUBLE_ADVERB",
            }

    # 口語・俗語（とか/っぽい/みたい）
    for m in _COLLOQUIAL_RE.finditer(text):
        yield {
            "start": m.start(),
            "end": m.end(),
            "match": m.group(0),
            "message": "口語的な表現（文体の統一を検討）",
            "suggestion": None,
            "severity": "INFO",
            "rule_id": "ADV_COLLOQUIAL",
        }

    # 句読点混在（全角/半角が混在）
    if _MIXED_FULL_HALF_PUNCT_RE.search(text):
        m = _MIXED_FULL_HALF_PUNCT_RE.search(text)
        assert m
        yield {
            "start": m.start(),
            "end": m.end(),
            "match": m.group(0)[:10],
            "message": "句読点の種類（全角/半角）が混在しています",
            "suggestion": "句読点を全角（、。）に統一",
            "severity": "WARN",
            "rule_id": "ADV_PUNCT_MIXED",
        }

    # ASCII三点リーダ
    for m in _ASCII_ELLIPSIS_RE.finditer(text):
        yield {
            "start": m.start(),
            "end": m.end(),
            "match": m.group(0),
            "message": "三点リーダはUnicodeの…に統一を推奨",
            "suggestion": "…",
            "severity": "INFO",
            "rule_id": "ADV_ELLIPSIS",
        }

    # 句読点直前スペース
    for m in _SPACE_BEFORE_PUNCT_RE.finditer(text):
        yield {
            "start": m.start(),
            "end": m.end(),
            "match": m.group(0),
            "message": "句読点直前のスペースを削除",
            "suggestion": "",
            "severity": "WARN",
            "rule_id": "ADV_SPACE_BEFORE_PUNCT",
        }

    # 伸ばし棒の多用
    for m in _PROLONGED_SOUND_RE.finditer(text):
        yield {
            "start": m.start(),
            "end": m.end(),
            "match": m.group(0),
            "message": "伸ばし棒（ー）の多用",
            "suggestion": None,
            "severity": "INFO",
            "rule_id": "ADV_PROLONGED_SOUND",
        }

    # 長文検出
    for s, e in _detect_long_sentences(text):
        yield {
            "start": s,
            "end": e,
            "match": text[s:e][:10],
            "message": "1文が長すぎます（可読性低下の可能性）",
            "suggestion": "文を分割するなどの検討",
            "severity": "INFO",
            "rule_id": "ADV_LONG_SENTENCE",
        }

    # 文末の句点必須（日本語を含む行が句点で終わらない場合）
    lines = text.splitlines(keepends=True)
    offset = 0
    in_code = False
    for ln in lines:
        stripped = ln.strip()
        # コードフェンスの開始/終了 ``` または ~~~
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            offset += len(ln)
            continue
        contains_jp = bool(re.search(r"[\u3040-\u30FF\u4E00-\u9FFF]", ln))
        if contains_jp and not in_code:
            # 記号や引用閉じを除いた末尾
            core = ln.rstrip()
            # 箇条書き・見出し・記号閉じ等は許容
            is_bullet = bool(re.match(r"^\s*(?:[-*・•●◆◇■□]|\d+[.)]|[（(]\d+[）)])\s+", ln))
            is_md_header = ln.lstrip().startswith(('#', '##', '###', '####', '#####', '######'))
            is_quote = bool(re.match(r"^\s{0,3}>\s*", ln))
            is_table = ln.lstrip().startswith("|")
            ends_with_bracket = bool(re.search(r"[\)\]\)）】》』」]$", core))
            ends_with_colon = core.endswith(":") or core.endswith("：")
            if core and core[-1] not in ("。", "！", "？") and not (is_bullet or is_md_header or is_quote or is_table or ends_with_bracket or ends_with_colon):
                yield {
                    "start": offset,
                    "end": offset + len(ln),
                    "match": ln.strip()[:10],
                    "message": "文末に句点（。）を付与してください（文末統一）",
                    "suggestion": None,
                    "severity": SENTENCE_FINAL_PUNCT_SEVERITY,
                    "rule_id": "ADV_SENTENCE_FINAL_PUNCT",
                }
        offset += len(ln)

    # カタカナ語の許容/非許容ポリシー
    if KATAKANA_DENY:
        for m in re.finditer(r"(?<![A-Za-z0-9_])[ァ-ヶー・]+(?![A-Za-z0-9_])", text):
            token = m.group(0)
            if len(token) < 2:
                continue
            norm = unicodedata.normalize("NFKC", token)
            if token in KATAKANA_ALLOW:
                continue
            if (token in KATAKANA_DENY) or (norm in KATAKANA_DENY):
                yield {
                    "start": m.start(),
                    "end": m.end(),
                    "match": token,
                    "message": "ドメイン方針によりカタカナ語の使用を抑制（許容リスト外）",
                    "suggestion": None,
                    "severity": "WARN",
                    "rule_id": "ADV_KATAKANA_DENY",
                }

    # 終助詞ポリシー（文末の ね/よ/かな など）
    if END_PARTICLE_POLICY > 0:
        sev = "ERROR" if END_PARTICLE_POLICY == 2 else "WARN"
        pat = re.compile(r"(ね|よ|かな)[。】》)]?$")
        pos = 0
        for ln in text.splitlines(keepends=True):
            if pat.search(ln):
                yield {
                    "start": pos,
                    "end": pos + len(ln),
                    "match": ln.strip()[-5:],
                    "message": "終助詞の使用を禁止/抑制（設定による）",
                    "suggestion": None,
                    "severity": sev,
                    "rule_id": "ADV_END_PARTICLE",
                }
            pos += len(ln)

def configure_advanced(emph_threshold: Optional[int] = None, long_limit: Optional[int] = None, style_mix_threshold: Optional[int] = None, katakana_allow: Optional[List[str]] = None, katakana_deny: Optional[List[str]] = None, end_particle_policy: Optional[str] = None, sentence_final_punct_severity: Optional[str] = None):
    """CLIなどから閾値を設定可能にするための簡易設定関数。"""
    global EMPH_THRESHOLD, LONG_SENTENCE_LIMIT, STYLE_MIX_THRESHOLD, KATAKANA_ALLOW, KATAKANA_DENY, END_PARTICLE_POLICY, SENTENCE_FINAL_PUNCT_SEVERITY
    if emph_threshold is not None and emph_threshold > 0:
        EMPH_THRESHOLD = emph_threshold
    if long_limit is not None and long_limit > 0:
        LONG_SENTENCE_LIMIT = long_limit
    if style_mix_threshold is not None and style_mix_threshold > 0:
        STYLE_MIX_THRESHOLD = style_mix_threshold
    if katakana_allow is not None:
        KATAKANA_ALLOW = set(katakana_allow)
    if katakana_deny is not None:
        KATAKANA_DENY = set(katakana_deny)
    if end_particle_policy is not None:
        m = str(end_particle_policy).lower()
        if m in ("none", "off", "0"):
            END_PARTICLE_POLICY = 0
        elif m in ("warn", "1"):
            END_PARTICLE_POLICY = 1
        elif m in ("error", "2"):
            END_PARTICLE_POLICY = 2
    if sentence_final_punct_severity is not None:
        s = str(sentence_final_punct_severity).upper()
        if s in ("INFO", "WARN", "ERROR"):
            SENTENCE_FINAL_PUNCT_SEVERITY = s

def detect_style_mixed_lines(text: str, threshold: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """文末統一（です/ます vs だ/である）の混在を行単位でカウントし、
    それぞれの出現行数が threshold を超えて両立する場合にWARN相当を返す。
    """
    lines = text.splitlines()
    polite = 0
    plain = 0
    thr = threshold if threshold is not None else STYLE_MIX_THRESHOLD
    for ln in lines:
        if re.search(r"(です。|ます。)$", ln):
            polite += 1
        if re.search(r"(だ。|である。)$", ln):
            plain += 1
    if polite >= thr and plain >= thr:
        pos = text.find("です。")
        if pos < 0:
            pos = text.find("だ。")
        return {
            "start": max(0, pos),
            "end": max(0, pos + 3),
            "match": text[max(0, pos):max(0, pos + 3)],
            "message": "文体(ですます/だ・である)が混在しています（行単位集計）",
            "suggestion": "文書内で文末表現をどちらかに統一",
            "severity": "WARN",
            "rule_id": "ADV_STYLE_MIXED_LINES",
        }
    return None
__all__ = ["run_advanced", "detect_style_mixed_lines", "configure_advanced", "EMPH_THRESHOLD", "LONG_SENTENCE_LIMIT", "STYLE_MIX_THRESHOLD", "KATAKANA_ALLOW", "KATAKANA_DENY"]
