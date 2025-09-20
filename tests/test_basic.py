import json
from tempjacleaner import check_text


def test_detect_old_style_word():
    text = 'print("有り難う ございます")'
    issues = check_text(text, from_code=True)
    assert any('有り難う' in i.snippet for i in issues), issues


def test_no_issue_simple():
    text = 'print("ありがとう ございます")'
    issues = check_text(text, from_code=True)
    assert not any(i.snippet == 'ありがとう' for i in issues)
