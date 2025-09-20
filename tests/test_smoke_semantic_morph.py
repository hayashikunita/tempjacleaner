import importlib
import subprocess
import sys
from pathlib import Path

PKG = 'tempjacleaner'
ROOT = Path(__file__).resolve().parents[1]


def _run_cli(args):
    exe = [sys.executable, '-m', PKG + '.cli']
    cp = subprocess.run(exe + args, cwd=str(ROOT), capture_output=True, text=True)
    return cp.returncode, cp.stdout, cp.stderr


def test_smoke_cli_defaults():
    # 依存の有無に関わらず、エラーにならずに実行できること
    # semantic/morph は環境により自動ON/OFFが変わるため、終了コード/出力のみを確認
    tmp = ROOT / 'sample.txt'
    tmp.write_text('これはテストです。', encoding='utf-8')
    code, out, err = _run_cli([str(tmp)])
    assert code in (0, 1)  # issueの有無で0/1
    assert 'Total:' in out or out.strip() == 'No issues found.'


def test_semantic_toggle_flags():
    tmp = ROOT / 'sample.txt'
    tmp.write_text('これ、それ、あれ。', encoding='utf-8')
    # 明示OFF
    code1, out1, err1 = _run_cli(['--no-semantic', str(tmp)])
    # 明示ON（未導入なら警告しつつスキップ）
    code2, out2, err2 = _run_cli(['--semantic', str(tmp)])
    assert code1 in (0, 1) and code2 in (0, 1)


def test_morph_toggle_flags():
    tmp = ROOT / 'sample.txt'
    tmp.write_text('有り難うございます', encoding='utf-8')
    code1, out1, err1 = _run_cli(['--no-morph', str(tmp)])
    code2, out2, err2 = _run_cli(['--morph', str(tmp)])
    assert code1 in (0, 1) and code2 in (0, 1)
