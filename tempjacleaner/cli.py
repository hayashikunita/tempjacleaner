from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore
from .checker import check_paths
from .morph import is_available as morph_available
from .external_rules import load_rule_file
from .typo_rules import add_patterns
from .lt_checker import is_available as lt_available
from .nlp_checker import is_available as nlp_available
from .spellcheck import is_available as spell_available
from .advanced_rules import run_advanced as _ra  # 型参照用
from .advanced_rules import configure_advanced
from typing import Dict, Tuple


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tempjacleaner",
        description="任意ファイルから日本語文字列を抽出し簡易誤字を検出します"
    )
    p.add_argument("paths", nargs="+", help="走査するファイル/ディレクトリ")
    p.add_argument("--json", action="store_true", help="JSONで出力")
    p.add_argument("--config", help="設定ファイル(TOML: pyproject.toml など)を読み込み、既定値を上書き")
    p.add_argument("--fail-on-issue", action="store_true", help="問題が1件でもあれば終了コード1")
    p.add_argument("--rules", action="append", metavar="FILE", help="追加のYAML/JSONルールファイル (複数指定は繰り返し)")
    # コメント: 既定を有効化し、無効化オプションを提供
    p.add_argument("--include-comments", action="store_true", help="[互換用] コメント領域の日本語も検査する (既定で有効)")
    p.add_argument("--no-comments", action="store_true", help="コメント領域の日本語を検査しない")
    # morph: 既定は環境が許せば有効。--no-morph で明示的に無効化。
    p.add_argument("--morph", dest="morph", action="store_true", default=None, help="形態素解析で日本語トークン単位に検査(要: janome/fugashi)")
    p.add_argument("--no-morph", dest="morph", action="store_false", help="形態素解析を無効化")
    p.add_argument("--fix", action="store_true", help="suggestionで自動修正して上書き保存")
    p.add_argument("--fix-aggressive", action="store_true", help="安全な提案がない項目にもヒューリスティックで自動修正を試みる")
    p.add_argument("--fix-context", action="store_true", help="URL/メール/コード片/英大文字識別子など文脈上の安全フィルタを適用してから修正する")
    p.add_argument("--fix-lt", action="store_true", help="LanguageToolの置換候補を安全基準に基づき自動適用")
    p.add_argument("--fix-nlp", action="store_true", help="NLP(ja_ginza)に基づく軽微な再構成を自動適用（主に --fix-aggressive と併用）")
    p.add_argument("--jobs", type=int, default=1, help="並列実行のワーカー数")
    p.add_argument("--no-cache", action="store_true", help="キャッシュを使わず毎回フルスキャン")
    p.add_argument("--advanced", action="store_true", help="高度校閲ルールを有効化(ら抜き/重言/文体混在など)")
    p.add_argument("--no-default-rules", action="store_true", help="同梱のbusiness.jsonを読み込まない")
    p.add_argument("--strict", action="store_true", help="厳格モード: 同梱のstrict.jsonを追加読込し、しきい値を厳しめに設定")
    p.add_argument("--adv-emph-threshold", type=int, default=2, help="強調副詞多用の閾値 (既定: 2)")
    p.add_argument("--adv-long-limit", type=int, default=100, help="長文判定の閾値(文字数) (既定: 100)")
    p.add_argument("--adv-style-mix-threshold", type=int, default=2, help="文体(です/ます・だ/である)混在の閾値(行数) (既定: 2)")
    p.add_argument("--lt", action="store_true", help="LanguageToolによる広範囲の一般ルールチェックを追加(任意依存)")
    p.add_argument("--lt-lang", default="ja-JP", help="LanguageToolの言語コード (既定: ja-JP)")
    p.add_argument("--nlp", action="store_true", help="spaCy/GiNZAによる構文解析ベースの高度チェック(任意依存)")
    p.add_argument("--nlp-model", default="ja_ginza", help="spaCyモデル名 (既定: ja_ginza)")
    p.add_argument("--spell", action="store_true", help="辞書に基づく日本語単語の簡易スペルチェック(任意依存)")
    p.add_argument("--dict", action="append", dest="dict_files", metavar="FILE", help="スペルチェック用辞書ファイル(複数可): txt(1行1語)/json({words:[...]})")
    p.add_argument("--min-severity", choices=["INFO", "WARN", "ERROR"], default="INFO", help="この重大度未満を非表示にします (既定: INFO)")
    # semantic: 既定は環境が許せば有効。--no-semantic で明示的に無効化。
    p.add_argument("--semantic", dest="semantic", action="store_true", default=None, help="spaCy/GiNZAによる文意解析・文法チェックを追加(任意依存)")
    p.add_argument("--no-semantic", dest="semantic", action="store_false", help="文意解析を無効化")
    return p


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    # 設定ファイル読込（TOMLのみ簡易対応）。CLI引数が最優先だが、未指定の項目は設定で補完。
    if args.config:
        cfg_path = Path(args.config)
        if cfg_path.is_file() and tomllib is not None and cfg_path.suffix.lower() in {".toml"}:
            try:
                with cfg_path.open("rb") as f:
                    cfg = tomllib.load(f)
                tool = cfg.get("tool", {}) if isinstance(cfg, dict) else {}
                tjc = tool.get("tempjacleaner", {}) if isinstance(tool, dict) else {}
                # ブール系
                for key, attr in [
                    ("defaultRules", "no_default_rules"),  # Falseで既定ルールOFF
                    ("advanced", "advanced"),
                    ("strict", "strict"),
                    ("morph", "morph"),
                    ("lt", "lt"),
                    ("nlp", "nlp"),
                    ("spell", "spell"),
                    ("includeComments", "include_comments"),
                    ("noComments", "no_comments"),
                    ("fix", "fix"),
                    ("fixAggressive", "fix_aggressive"),
                    ("fixContext", "fix_context"),
                    ("fixLT", "fix_lt"),
                    ("fixNLP", "fix_nlp"),
                    ("semantic", "semantic"),
                ]:
                    if key in tjc and getattr(args, attr, None) in (False, None):
                        setattr(args, attr, bool(tjc[key]))
                # 数値/文字列
                if "advEmphThreshold" in tjc and (not args.adv_emph_threshold):
                    args.adv_emph_threshold = int(tjc["advEmphThreshold"])  # type: ignore
                if "advLongLimit" in tjc and (not args.adv_long_limit):
                    args.adv_long_limit = int(tjc["advLongLimit"])  # type: ignore
                if "advStyleMixThreshold" in tjc and (not getattr(args, "adv_style_mix_threshold", None)):
                    args.adv_style_mix_threshold = int(tjc["advStyleMixThreshold"])  # type: ignore
                if "ltLang" in tjc and (args.lt_lang == parser.get_default("lt_lang")):
                    args.lt_lang = str(tjc["ltLang"])
                if "nlpModel" in tjc and (args.nlp_model == parser.get_default("nlp_model")):
                    args.nlp_model = str(tjc["nlpModel"])
                if "jobs" in tjc and (args.jobs == parser.get_default("jobs")):
                    args.jobs = int(tjc["jobs"])  # type: ignore
                if "dict" in tjc and not args.dict_files:
                    # dictは配列想定
                    val = tjc["dict"]
                    if isinstance(val, list):
                        args.dict_files = [str(x) for x in val]
                # カタカナ語ポリシー
                if "katakanaAllow" in tjc:
                    args._katakana_allow = list(map(str, tjc["katakanaAllow"]))  # type: ignore
                if "katakanaDeny" in tjc:
                    args._katakana_deny = list(map(str, tjc["katakanaDeny"]))  # type: ignore
                # 終助詞/句点の設定
                if "endParticleBan" in tjc:
                    args._end_particle_policy = str(tjc["endParticleBan"])  # type: ignore
                if "sentenceFinalPunctSeverity" in tjc:
                    args._sentence_final_punct_severity = str(tjc["sentenceFinalPunctSeverity"])  # type: ignore
            except Exception as e:  # pragma: no cover
                print(f"[warn] failed to load config {cfg_path}: {e}", file=sys.stderr)
    # コメント既定値の解決
    include_comments = True
    if args.no_comments:
        include_comments = False
    elif args.include_comments:
        include_comments = True
    # デフォルト business.json 読み込み → --no-default-rules で無効化
    default_rule_path = (__import__("pathlib").Path(__file__).parent / "rules" / "business.json")
    if default_rule_path.is_file() and not args.no_default_rules:
        try:
            patterns = load_rule_file(str(default_rule_path))
            add_patterns(patterns)
        except Exception as e:  # pragma: no cover
            print(f"[warn] failed to load default business rules: {e}", file=sys.stderr)
    # 外部ルール読み込み
    if args.rules:
        for rf in args.rules:
            try:
                patterns = load_rule_file(rf)
            except Exception as e:  # pragma: no cover (CLIエラーパス)
                print(f"Failed to load rules {rf}: {e}", file=sys.stderr)
                return 2
            add_patterns(patterns)
    # morph 既定値の解決（未指定なら自動判定）
    if args.morph is None:
        args.morph = morph_available()
    elif args.morph and not morph_available():
        print("[warn] --morph が有効ですが 形態素解析器(janome/fugashi) が見つかりません。通常モードで実行します。", file=sys.stderr)
        args.morph = False
    if args.lt and not lt_available():
        print("[warn] --lt が指定されましたが 'language_tool_python' が見つかりません。LTは無効化されます。", file=sys.stderr)
    if args.nlp and not nlp_available():
        print("[warn] --nlp が指定されましたが 'spacy/ja-ginza' が見つかりません。NLPは無効化されます。", file=sys.stderr)
    if args.spell and not spell_available():
        print("[warn] --spell が指定されましたが 'rapidfuzz' が見つかりません。スペルチェックは無効化されます。", file=sys.stderr)
    if args.spell and not args.dict_files:
        print("[warn] --spell には --dict で辞書ファイルを指定してください。スペルチェックはスキップします。", file=sys.stderr)
    # semantic の既定値を環境に応じて解決
    def _ginza_available() -> bool:
        try:
            import spacy  # type: ignore
            # モデルがインストール済みかを軽量チェック
            spacy.util.get_package_path("ja_ginza")  # type: ignore
            return True
        except Exception:
            return False

    if args.semantic is None:
        args.semantic = _ginza_available()
    elif args.semantic and not _ginza_available():
        print("[warn] --semantic が有効ですが 'ja_ginza' モデルが見つかりません。semanticは無効化されます。", file=sys.stderr)
        args.semantic = False

    use_cache = not args.no_cache
    if args.fix:
        use_cache = False  # 修正時は必ず最新内容で検査
    # しきい値の注入: 現状はadvanced_rules内部定数で運用しているため、環境変数で渡す等の方法もある。
    # シンプルにグローバルに設定する場合は advanced_rules の値を変更する実装が必要だが、ここでは一旦
    # 現行のしきい値で実行。将来: オプション値を advanced_rules に渡す拡張。

    # --strict でより厳しく
    if args.strict:
        # strict.json の読込（存在すれば）
        strict_path = (__import__("pathlib").Path(__file__).parent / "rules" / "strict.json")
        if strict_path.is_file():
            try:
                patterns = load_rule_file(str(strict_path))
                add_patterns(patterns)
            except Exception as e:
                print(f"[warn] failed to load strict rules: {e}", file=sys.stderr)
        # advanced を自動ON
        args.advanced = True
        # しきい値を厳しめに：強調副詞1回で警告、長文=80
        args.adv_emph_threshold = min(args.adv_emph_threshold or 2, 1)
        args.adv_long_limit = min(args.adv_long_limit or 100, 80)
        # 文体混在も厳しく
        if hasattr(args, "adv_style_mix_threshold"):
            args.adv_style_mix_threshold = min(args.adv_style_mix_threshold or 2, 1)

    # --advanced 時の閾値反映
    if args.advanced or args.strict:
        try:
            configure_advanced(
                emph_threshold=args.adv_emph_threshold,
                long_limit=args.adv_long_limit,
                style_mix_threshold=getattr(args, "adv_style_mix_threshold", None),
                katakana_allow=getattr(args, "_katakana_allow", None),
                katakana_deny=getattr(args, "_katakana_deny", None),
                end_particle_policy=getattr(args, "_end_particle_policy", None),
                sentence_final_punct_severity=getattr(args, "_sentence_final_punct_severity", None),
            )
        except Exception:
            pass

    issues = check_paths(
        args.paths,
        include_comments=include_comments,
        morph=args.morph,
        jobs=args.jobs,
        use_cache=use_cache,
        advanced=args.advanced,
        lt=args.lt,
        lt_lang=args.lt_lang,
        nlp=args.nlp,
        nlp_model=args.nlp_model,
        spell=args.spell,
        dict_files=args.dict_files,
    semantic=bool(getattr(args, "semantic", False)),
    )
    # 重大度フィルタ
    sev_order = {"INFO": 0, "WARN": 1, "ERROR": 2}
    minsev = sev_order.get(args.min_severity, 0)
    issues = [i for i in issues if sev_order.get(i.severity, 1) >= minsev]
    if args.json:
        data = [i.to_dict() for i in issues]
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if not issues:
            print("No issues found.")
        else:
            # VS Code でクリック可能なリンクにするため、file:line:col 形式で出力
            # 文字オフセット(start/end)から行・桁を算出する
            def _offset_to_linecol(text: str, idx: int) -> Tuple[int, int]:
                # 1-based line/col
                if idx <= 0:
                    return 1, 1
                # 行番号 = 先頭〜idxまでの改行数 + 1
                line = text.count("\n", 0, idx) + 1
                last_nl = text.rfind("\n", 0, idx)
                col = (idx - (last_nl + 1)) + 1 if last_nl != -1 else idx + 1
                return line, col

            file_text_cache: Dict[str, str] = {}
            for i in issues:
                fpath = i.file
                if fpath:
                    try:
                        # 絶対パスに正規化（クリック時の解決精度を上げる）
                        from pathlib import Path as _P
                        abs_path = str(_P(fpath).resolve())
                        if abs_path not in file_text_cache:
                            file_text_cache[abs_path] = _P(abs_path).read_text(encoding="utf-8", errors="ignore")
                        text = file_text_cache[abs_path]
                        line, col = _offset_to_linecol(text, i.start)
                        loc = f"{abs_path}:{line}:{col}"
                    except Exception:
                        # 失敗時は元のファイル表示にフォールバック
                        loc = str(fpath)
                else:
                    loc = "<memory>"
                # クリック可能な部分を先頭に配置
                base_msg = f"{loc}: [{i.severity}] {i.message}"
                extra = []
                if i.snippet:
                    extra.append(i.snippet)
                if i.suggestion:
                    extra.append(f"suggest: {i.suggestion}")
                if i.rule_id:
                    extra.append(f"rule: {i.rule_id}")
                if extra:
                    base_msg += " | " + " | ".join(extra)
                print(base_msg)
            print(f"Total: {len(issues)} issue(s)")
    # 自動修正
    if (args.fix or args.fix_aggressive) and issues:
        from .fixer import apply_fixes
        touched = set()
        by_file = {}
        for i in issues:
            if not i.file:
                continue
            by_file.setdefault(i.file, []).append(i)
        for fpath, items in by_file.items():
            p = Path(fpath)
            content = p.read_text(encoding="utf-8", errors="ignore")
            new_content = apply_fixes(
                content,
                items,
                aggressive=args.fix_aggressive,
                context=args.fix_context,
                use_lt=args.fix_lt,
                use_nlp=args.fix_nlp,
            )
            if new_content != content:
                p.write_text(new_content, encoding="utf-8")
                touched.add(fpath)
        if touched:
            print(f"Fixed {len(touched)} file(s)")
    if args.fail_on_issue and issues:
        return 1
    return 0

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
