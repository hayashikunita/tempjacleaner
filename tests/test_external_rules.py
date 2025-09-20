import json
import tempfile
from tempjacleaner.external_rules import load_rule_file
from tempjacleaner.typo_rules import add_patterns
from tempjacleaner import check_text

def test_external_rule_detects_in_code_string():
    data = [
        {"pattern": "テスト誤字", "message": "外部ルール検出", "suggestion": "テスト語", "severity": "INFO"}
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as f:
        json.dump(data, f, ensure_ascii=False)
        path = f.name
    pats = load_rule_file(path)
    add_patterns(pats)
    text = 'print("これはテスト誤字です")'
    issues = check_text(text, from_code=True)
    assert any(i.snippet == "テスト誤字" for i in issues), issues
