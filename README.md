# tempjacleaner

日本語文字列(特にソースコード内の文字列リテラル)に対して、簡易な誤字/旧字体/表記揺れなどを検出する Python ライブラリ & CLI ツールです。

> 目的: **軽量コア(依存ゼロ)** を基本に、必要に応じて形態素解析・文意解析などの拡張機能を“任意依存”として追加できる設計です。

> 状態: 本ツールは現在も開発途中です。検出精度や自動修正の安全性など、難易度が高い課題が残っており、未完成の部分があります。実運用時は `--min-severity` の活用や `--fix` の対象限定など、慎重な設定でご利用ください。

## 特徴

- 任意拡張子のファイルを再帰走査し、テキストと判断できれば対象化
- コード風ファイルからは文字列リテラル ("..." / '...') 内のみを抽出して日本語ブロックを検査
- シンプルな正規表現ベースのルールで旧字体や表記揺れ候補を検出
- CLI で JSON 出力 / 終了コード制御が可能 (CI 連携しやすい)
- 依存パッケージなし (標準ライブラリのみ)
	- 任意: 形態素解析(janome)、YAMLルール(PyYAML)

## インストール

PyPI 公開後は以下 (まだ公開前のためローカルインストール例)。

```bash
pip install tempjacleaner
```

開発版 (このリポジトリ直下で):

```bash
pip install .
```

## デフォルト挙動（morph/semantic の自動ON条件）

- 形態素解析（morph）
  - janome または fugashi+unidic-lite が環境に存在すれば、未指定でも自動で有効化されます。
  - 明示的に無効化したい場合は `--no-morph` を指定します（有効化は `--morph`）。

- 文意解析（semantic / spaCy+GiNZA）
  - `ja_ginza` モデルが導入済みなら、未指定でも自動で有効化されます。
  - 明示的に無効化したい場合は `--no-semantic` を指定します（有効化は `--semantic`）。
  - 未導入の環境では自動的に無効化され、他のチェックは継続します。

補足: CI などで安定動作が必要な場合は、明示フラグ（`--no-morph`, `--no-semantic`）で固定化することを推奨します。

## 使い方 (CLI)

```bash
tempjacleaner path/to/dir path/to/file.py
```

JSON で結果を受け取りたい場合:

```bash
tempjacleaner . --json > result.json
```

問題が 1 件でもあれば CI を失敗させたい場合:

```bash
tempjacleaner src --fail-on-issue
```

コメントも既定で検査します（無効化したい場合）:

```bash
tempjacleaner src --no-comments
```

外部ルール(YAML/JSON)を追加:

```bash
tempjacleaner src --rules rules.json --rules more.yaml
```

形態素解析（任意依存）:

```bash
pip install "tempjacleaner[morph]"          # janome
pip install "tempjacleaner[mecab]"          # fugashi + unidic-lite（推奨）
tempjacleaner src                            # 依存があれば既定でON
tempjacleaner src --no-morph                 # 明示的に無効化
```

文意解析（任意依存: spaCy + GiNZA）:

```bash
pip install "tempjacleaner[nlp]"             # spacy + ja-ginza
tempjacleaner src                             # 依存があれば既定でON
tempjacleaner src --no-semantic               # 明示的に無効化
```

自動修正(--fix):

```bash
tempjacleaner src --fix
```

重大度でのフィルタリング:

```bash
tempjacleaner src --min-severity WARN   # INFO|WARN|ERROR のいずれか
```
指定レベル未満の指摘を出力・失敗判定・自動修正対象から除外します。

並列/キャッシュ制御:

```bash
tempjacleaner src --jobs 4
tempjacleaner src --no-cache
```

サンプル出力 (プレーン):

```
example.py:10-13 有り難う -> 旧表記 '有り難う' -> 'ありがとう'
Total: 1 issue(s)
```

サンプル(JSON):

```json
[
	{
		"file": "example.py",
		"start": 10,
		"end": 13,
		"snippet": "有り難う",
		"message": "旧表記 '有り難う' -> 'ありがとう'",
		"suggestion": "ありがとう"
	}
]
```

## Python API

```python
from tempjacleaner import check_text

code = 'print("有り難う ございます")'
issues = check_text(code, from_code=True)
for i in issues:
		print(i.message, i.suggestion)
```

戻り値: `Issue` オブジェクトのリスト。

| 属性 | 説明 |
|------|------|
| file | ファイルパス (テキスト直接の場合 None) |
| start/end | 元テキスト内のバイトではなく Python 文字列インデックス |
| snippet | 問題となった文字列断片 |
| message | 説明メッセージ |
| suggestion | 推奨表記 (あれば) |

## 検出ルール

現状は `typo_rules.py` に静的に定義された正規表現群のみです。例:

- 勿論 → もちろん
- 有り難う → ありがとう
- 御座い → ござい
- 遙か/遥か → はるか (ひらがな推奨)
- 長音の連続 (ーー) 縮約提案

拡張したい場合: `get_patterns()` に独自 `TypoPattern` を追加する、あるいは将来予定のプラグイン仕組みにフック。

## 制限事項 / 注意

- 文字列リテラル抽出は簡易 (エスケープや三連クォート、テンプレート文字列等は完全対応していません)
- コメント内日本語も既定で解析します（従来の `--include-comments` は互換用。無効化は `--no-comments`）
- 辞書的正しさではなく、ヒューリスティック(正規表現)のみ
- 語境界や文脈判定なし: 誤検出/検出漏れが起こり得ます
- マルチバイト境界 index は Python の文字インデックス (UTF-16 ではなくコードポイント) で返却
- 自動修正 `--fix` は安全策として Markdown のコードフェンス (``` ... ```) 内はスキップします（誤置換防止のための簡易判定）

## 開発 (ローカル)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
pytest -q
```

## ロードマップ (アイデア)

- [ ] コメント領域の抽出 (各言語ごとのパーサ差し替え)
- [ ] 形態素解析による文節・品詞フィルタリング
- [ ] 辞書(外部API/ローカル)による候補生成
- [ ] JSON Schema ベースの出力拡張 (severity / rule id)
- [ ] ルールのオン/オフ設定 (pyproject.toml, YAML)
- [ ] --fix オプションで自動修正 (安全な置換のみ)

## LanguageTool 連携 (オプション)

広範囲の一般的な校正ルールをカバーするため、LanguageTool 連携を追加しました。

- インストール: 追加のオプション依存を利用します。
  - pip: `pip install "tempjacleaner[lt]"`
- 使い方:
  - CLI: `tempjacleaner . --lt --lt-lang ja-JP`
- 注意点:
  - 環境により Java が必要になる場合があります。
  - `language_tool_python` はデフォルトでオンラインの public API を利用する実装を含みます。ネットワークポリシーに沿ってご利用ください。
  - 自動修正 `--fix` は LanguageTool の指摘には適用しません（誤修正を避けるため）。

## 構文解析ベースの高度チェック (オプション → 依存があれば既定ON)

spaCy + GiNZA を用いた構文解析ベースのチェックを追加しました（依存重め）。

- インストール（オプション依存）
  - pip: `pip install "tempjacleaner[nlp]"`
  - 初回は `ja_ginza` モデルのダウンロードが必要です（pipが自動で取得するか、環境により手動導入）。
- 使い方
  - 依存導入済みなら未指定でも自動ON
  - 明示フラグ: `--semantic`（有効化）/ `--no-semantic`（無効化）
  - モデル指定: `--nlp-model ja_ginza`
- 現在の代表ルール
  - 助詞『の』の連鎖（冗長の可能性）
  - 助詞連続（不自然の可能性）
  - 主語と述語が離れすぎ（読みにくさの可能性）
- 注意点
  - 未導入環境では自動でスキップし、他のチェックは継続します。
  - 実行時間/メモリ消費が増えます。CIでは必要な箇所だけに限定するなど工夫してください。

## 日本語単語のスペルチェック (オプション)

辞書に基づく日本語単語の簡易スペルチェックを追加しました（rapidfuzz利用）。

- インストール（オプション依存）
  - pip: `pip install "tempjacleaner[spell]"`
- 辞書形式
  - txt: 1行1語（UTF-8）。行頭 `#` はコメント扱い
  - json: `{ "words": ["正しい", "語彙", ...] }`
- 使い方
  - CLI: `tempjacleaner . --spell --dict dict.txt` もしくは `--dict dict.json`（複数指定可）
  - API: `check_paths(..., spell=True, dict_files=[...])`
- 注意
  - janome があるとトークン分割がやや精密になります。無くても動作します。
  - 類似度しきい値は内部で 90 に設定しています。誤検知が多い/少ない場合は要調整（将来的に公開オプション化可能）。

## 形態素解析（MeCab/fugashi or Janome）

- 推奨: MeCab系（fugashi + unidic-lite）
  - インストール: `pip install "tempjacleaner[mecab]"`
  - Windowsでも `unidic-lite` で手軽に動作します
- 代替: Janome
  - インストール: `pip install "tempjacleaner[morph]"`
- 使い方
  - 依存導入済みなら未指定でも自動ON
  - CLI: `tempjacleaner . --morph`（有効化）/ `--no-morph`（無効化）
  - API: `check_text(..., morph=True)`
- 備考
  - 両方導入されている場合は fugashi を優先します
  - 形態素解析が無い場合は一塊として扱います（機能は継続）

## ライセンス

MIT License

---

バグ報告・改善提案歓迎します。