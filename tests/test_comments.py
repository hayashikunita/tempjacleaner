from tempjacleaner import check_text

def test_detect_in_comment_when_enabled():
    text = "# 有り難う ございます\nprint('ok')"
    issues = check_text(text, from_code=True, include_comments=True)
    assert any('有り難う' in i.snippet for i in issues)


def test_not_detect_in_comment_when_disabled():
    text = "# 有り難う ございます\nprint('ok')"
    issues = check_text(text, from_code=True, include_comments=False)
    assert not any('有り難う' in i.snippet for i in issues)
