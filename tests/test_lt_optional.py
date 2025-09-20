import importlib

def test_lt_optional_importable():
    # language_tool_python が無くてもインポートできること
    mod = importlib.import_module('tempjacleaner.lt_checker')
    assert hasattr(mod, 'is_available')
    # is_available は False か True のいずれか
    assert isinstance(mod.is_available(), bool)
