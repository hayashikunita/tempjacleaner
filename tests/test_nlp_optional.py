import importlib

def test_nlp_optional_importable():
    mod = importlib.import_module('tempjacleaner.nlp_checker')
    assert hasattr(mod, 'is_available')
    assert isinstance(mod.is_available(), bool)
