from tempjacleaner import check_text

def test_ranuki_detection():
    text = 'print("見れる可能性がある")'  # ら抜きの例: 見れる
    issues = check_text(text, from_code=True, include_comments=False, morph=False, advanced=True)
    assert any('ら抜き' in i.message for i in issues)

def test_tautology_detection():
    text = 'print("まず最初に手順を説明します")'
    issues = check_text(text, from_code=True, advanced=True)
    assert any('重言' in i.message for i in issues)
